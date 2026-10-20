#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-orchestrator 会话状态：按对话框隔离的轮次计数、提前提醒、最近 checkpoint。

只记录：项目名/对话框标识/轮数/token 用量/提醒标记/时间戳/agent 归属。绝不记录对话正文。

token 触发（可选）：bump 时传 token_count=；轮数与 token 两个阈值互补，哪个先到先触发。
TURN_THRESHOLD/TURN_WARN_AT（默认 8/7）；TOKEN_THRESHOLD/TOKEN_WARN_AT（默认 150000/130000）。
本文件不发起任何网络调用。

不可写降级：主路径 $CODEX_HOME/memory/state.json 不可写时自动落到
$TMPDIR/memory-orchestrator/state.json（可用 CODEX_MEMORY_STATE_FALLBACK 覆盖），
并在输出 JSON 的 storage 字段标明 primary/fallback。
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl  # POSIX
except ImportError:
    fcntl = None
try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None

STATE = Path(os.environ.get("CODEX_MEMORY_STATE", Path.home() / ".codex" / "memory" / "state.json"))
DEFAULTS = {"active_project": "", "turn_count": 0, "last_checkpoint": "", "last_action": "", "updated_at": ""}
THRESHOLD = int(os.environ.get("TURN_THRESHOLD", "8"))
WARN_AT = int(os.environ.get("TURN_WARN_AT", "7"))
TOKEN_THRESHOLD = int(os.environ.get("TOKEN_THRESHOLD", "150000"))
TOKEN_WARN_AT = int(os.environ.get("TOKEN_WARN_AT", "130000"))
AGENT_DEFAULT = os.environ.get("MEMORY_AGENT") or "codex"

STORAGE = {"path": str(STATE), "mode": "primary"}


def _state_fallback():
    p = os.environ.get("CODEX_MEMORY_STATE_FALLBACK")
    if p:
        return Path(p)
    return Path(tempfile.gettempdir()) / "memory-orchestrator" / "state.json"


def storage_path():
    """优先可用路径：已存在的主路径，或父目录可写的主路径；否则回退临时路径。"""
    candidates = [STATE, _state_fallback()]
    for p in candidates:
        try:
            if p.exists() or os.access(str(p.parent), os.W_OK):
                return p
        except OSError:
            continue
    return _state_fallback()


def _write_json(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=str(os.path.dirname(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _dialog_key(active_project, thread_id, agent=None):
    """对话框唯一键：agent==codex 保持历史格式；其他 agent 加 @ 命名空间防碰撞。"""
    proj = active_project or "default"
    tid = thread_id or proj
    if agent and agent != "codex":
        return f"{proj}||{tid}||@{agent}"
    return f"{proj}||{tid}"


def _resolve_agent(kv, args=None):
    if isinstance(kv, dict) and kv.get("agent"):
        return kv["agent"]
    if getattr(args, "agent", None):
        return args.agent
    return os.environ.get("MEMORY_AGENT") or AGENT_DEFAULT


def load():
    d = dict(DEFAULTS)
    for p in [storage_path(), STATE, _state_fallback()]:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        d[k] = v
                break
            except Exception:
                continue
    d.setdefault("dialogs", {})
    d.setdefault("agents", {})
    if not isinstance(d["dialogs"], dict):
        d["dialogs"] = {}
    if not isinstance(d["agents"], dict):
        d["agents"] = {}
    return d


def save(d):
    global STORAGE
    target = storage_path()
    fallback = _state_fallback()
    try:
        _write_json(target, d)
        STORAGE = {"path": str(target), "mode": ("primary" if str(target) == str(STATE) else "fallback")}
    except (PermissionError, OSError):
        if str(target) == str(fallback):
            raise
        try:
            _write_json(fallback, d)
            STORAGE = {"path": str(fallback), "mode": "fallback"}
        except Exception as exc:
            raise OSError(f"状态文件不可写且降级路径写入失败: {exc}") from exc


class _StateLock:
    def __enter__(self):
        self.f = None
        lock_base = storage_path()
        lock_path = str(lock_base) + ".lock"
        if fcntl:
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            self.f = open(lock_path, "a+")
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
        elif msvcrt:
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            self.f = open(lock_path, "a+b")
            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)
        return self

    def __exit__(self, *exc):
        if self.f:
            try:
                if fcntl:
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
                elif msvcrt:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            try:
                self.f.close()
            except Exception:
                pass
        return False


def mark_alive(d, agent):
    agents = d.setdefault("agents", {})
    agents[agent] = {
        "agent_alive": True,
        "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return d


def cross_check(d, current_agent=None, threshold=THRESHOLD, warn_at=WARN_AT,
                token_threshold=TOKEN_THRESHOLD, token_warn_at=TOKEN_WARN_AT):
    """读共享注册表，列出其他 Agent 的超阈值/接近阈值对话框，以及未见存活标记的 Agent。

    只读他人的行；绝不改写 owner != 当前 agent 的记录。
    """
    current_agent = current_agent or AGENT_DEFAULT
    dialogs = d.get("dialogs") or {}
    others = []
    for key, s in dialogs.items():
        if not isinstance(s, dict):
            continue
        owner = s.get("owner") or s.get("agent") or "codex"
        if owner == current_agent:
            continue
        count = int(s.get("turn_count") or 0)
        toks = int(s.get("token_count") or s.get("tokens") or 0)
        if count < warn_at and toks < token_warn_at:
            continue
        parts = key.split("||", 2)
        metric = []
        if count >= threshold:
            metric.append("over_turns")
        elif count >= warn_at:
            metric.append("warn_turns")
        if toks >= token_warn_at:
            metric.append("over_tokens" if toks >= token_threshold else "warn_tokens")
        others.append({
            "agent": owner,
            "active_project": s.get("active_project") or parts[0],
            "thread_id": s.get("thread_id") or (parts[1] if len(parts) > 1 else key),
            "turn_count": count,
            "token_count": toks,
            "metric": "+".join(metric) or ("over" if count >= threshold else "warn"),
            "status": "over" if (count >= threshold or toks >= token_threshold) else "warn",
        })
    others.sort(key=lambda r: (r["agent"], r["status"] != "over", r["metric"]))

    known = d.get("agents") or {}
    suggest = [
        {"agent": name, "suggest_install": not bool(m.get("agent_alive"))}
        for name, m in known.items()
        if name != current_agent and isinstance(m, dict)
    ]
    suggest.sort(key=lambda s: s["agent"])
    return others, suggest


def _fmt_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _attach_storage(out):
    out["storage"] = STORAGE.copy()
    return out


def main():
    ap = argparse.ArgumentParser(description="memory-orchestrator 状态：get/set/bump/touch/cross-check（只记轮数，不记内容）")
    ap.add_argument("action", choices=["get", "set", "bump", "touch", "cross-check"])
    ap.add_argument("kv", nargs="*", help="键值对，如 active_project=示例项目 agent=codex。bump 支持 thread_id=xxx 标识对话框")
    ap.add_argument("--threshold", type=int, default=THRESHOLD, help="硬阈值（轮）")
    ap.add_argument("--warn-at", type=int, default=None, help="提前提醒线（轮），默认 threshold-1")
    ap.add_argument("--token-threshold", type=int, default=TOKEN_THRESHOLD, help="硬阈值（token）")
    ap.add_argument("--token-warn-at", type=int, default=None, help="提前提醒线（token），默认 token_threshold-20000")
    ap.add_argument("--thread-id", default=None, help="对话框标识（同一活跃项目下隔离不同对话框）")
    ap.add_argument("--agent", default=None, help="Agent 名（默认 $MEMORY_AGENT 或 codex）")
    ap.add_argument("--json", action="store_true", help="cross-check 也输出 JSON（其他动作始终输出 JSON）")
    args = ap.parse_args()
    warn_at = args.warn_at if args.warn_at is not None else max(1, args.threshold - 1)
    tok_warn_at = args.token_warn_at if args.token_warn_at is not None else max(1, args.token_threshold - 20000)

    kv = {}
    for s in args.kv:
        if "=" in s:
            k, v = s.split("=", 1)
            kv[k] = v

    project = kv.get("active_project", "")
    thread_id = kv.get("thread_id", args.thread_id or "")
    agent = _resolve_agent(kv, args)

    with _StateLock():
        d = load()
        if args.action == "get":
            print(json.dumps(d, ensure_ascii=False))
            return
        if args.action == "touch":
            d = mark_alive(d, agent)
            save(d)
            out = _attach_storage({"agent": agent, "agent_alive": True,
                                   "message": f"{agent} 已在本机登记本 Skill 存活标记"})
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return
        if args.action == "cross-check":
            others, suggest = cross_check(d, current_agent=agent, threshold=args.threshold, warn_at=warn_at,
                                          token_threshold=args.token_threshold, token_warn_at=tok_warn_at)
            out = _attach_storage({"agent": agent, "others": others, "suggest_install": suggest})
            if args.json or True:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            else:
                print(f"agent={agent} 交叉检查：")
                if not others and not suggest:
                    print("✅ 其他 Agent 无超阈值/接近阈值对话框，也无不带存活标记的注册 Agent")
                for r in others:
                    tag = "🔴 已超阈值" if r["status"] == "over" else "⚠️ 接近阈值"
                    print(f"  {tag} {r['agent']} 项目={r['active_project']} 对话框={r['thread_id']} {r['turn_count']} 轮")
                for s in suggest:
                    print(f"  🟡 建议在《{s['agent']}》安装本 Skill，才能在该 Agent 这边实时提醒")
            return

        if args.action == "set":
            for k, v in kv.items():
                if k in ("active_project", "last_checkpoint", "last_action"):
                    d[k] = v
                elif k == "turn_count":
                    d["turn_count"] = int(v or 0)
                elif k == "token_count":
                    d["token_count"] = int(v or 0)
            if "turn_count" in kv or "token_count" in kv:
                skey = _dialog_key(d.get("active_project", project), thread_id, agent)
                dialogs = d.setdefault("dialogs", {})
                sc = dialogs.get(skey, {})
                sc.update({
                    "thread_id": thread_id or d.get("active_project") or project,
                    "active_project": d.get("active_project", project),
                    "agent": agent,
                    "owner": agent,
                    "turn_count": int(kv.get("turn_count") or sc.get("turn_count") or 0),
                    "token_count": int(kv.get("token_count") or sc.get("token_count") or 0),
                    "warned": bool(sc.get("warned")),
                    "forced": bool(sc.get("forced")),
                    "checked_at": _fmt_ts(),
                })
                dialogs[skey] = sc
            d = mark_alive(d, agent)
            save(d)
            out = _attach_storage({"agent": agent, "active_project": d.get("active_project", project), "ok": True})
            print(json.dumps(out, ensure_ascii=False))
            return

        # bump
        for k, v in kv.items():
            if k == "active_project":
                d["active_project"] = v
            elif k == "last_checkpoint":
                d["last_checkpoint"] = v
            elif k == "last_action":
                d["last_action"] = v
        project = d.get("active_project", "") or project
        key = _dialog_key(project, thread_id, agent)
        dialogs = d.setdefault("dialogs", {})
        cur = dialogs.get(key, {})
        count = int(cur.get("turn_count") or 0) + 1
        token_count = int(kv.get("token_count") or cur.get("token_count") or 0)
        tok_warn = tok_warn_at
        tok_over = args.token_threshold
        cur = {
            "thread_id": thread_id or project,
            "active_project": project,
            "agent": agent,
            "owner": agent,
            "turn_count": count,
            "token_count": token_count,
            "warned": bool(cur.get("warned")),
            "forced": bool(cur.get("forced")),
            "checked_at": _fmt_ts(),
        }
        dialogs[key] = cur
        d["active_project"] = project
        d["turn_count"] = count  # 兼容旧单对话字段
        d = mark_alive(d, agent)
        out = {"agent": agent, "thread_id": cur["thread_id"], "active_project": project,
               "turn_count": count, "token_count": token_count, "warned": False, "forced": False,
               "message": "", "cross_check": {"others": [], "suggest_install": []}}
        metric = ("over" if count >= args.threshold else "warn_turns") if count >= warn_at else ""
        if token_count:
            metric = ("over_tokens" if token_count >= tok_over else "warn_tokens") if token_count >= tok_warn else metric
        over_now = count >= args.threshold or token_count >= tok_over
        warn_now = (not over_now) and (count >= warn_at or (token_count and token_count >= tok_warn))
        if over_now and not cur["forced"]:
            cur["forced"] = True
            cur["warned"] = True
            out["warned"] = True
            out["forced"] = True
            if count >= args.threshold and token_count >= tok_over:
                out["message"] = f"⚠️ 对话同时达到阈值：{args.threshold} 轮 / {tok_over} token，请生成恢复包后开新对话。"
            elif token_count >= tok_over:
                out["message"] = f"⚠️ 对话已达 token 阈值 {tok_over}，请先生成恢复包，再开新对话。（轮数 {count} < {args.threshold}）"
            else:
                out["message"] = f"⚠️ 对话已达阈值 {args.threshold} 轮，请先生成恢复包，再开新对话。"
        elif (not cur["forced"]) and (not cur["warned"]) and warn_now:
            cur["warned"] = True
            out["warned"] = True
            if count >= warn_at and token_count and token_count >= tok_warn:
                out["message"] = f"⚠️ 接近阈值：{args.threshold - count} 轮 或 {max(0, tok_over - token_count)} token，请准备开新对话（只提醒一次）。"
            elif token_count and token_count >= tok_warn:
                out["message"] = f"⚠️ 接近 token 阈值：再用约 {max(0, tok_over - token_count)} token 达 {tok_over}，请准备开新对话（只提醒一次）。"
            else:
                rem = max(1, args.threshold - count)
                out["message"] = f"⚠️ 再 {rem} 轮将达到阈值 {args.threshold} 轮，请准备开新对话（本提醒只出一次）。"
        dialogs[key] = cur
        save(d)
        if out["warned"] or out["forced"]:
            others, suggest = cross_check(d, current_agent=agent, threshold=args.threshold, warn_at=warn_at,
                                          token_threshold=args.token_threshold, token_warn_at=tok_warn_at)
            out["cross_check"] = {"others": others, "suggest_install": suggest}
        out["metric"] = metric or None
        out = _attach_storage(out)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

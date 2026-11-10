#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-orchestrator 会话状态：按对话框隔离的轮次、上下文压力与提醒标记。

只记录：项目名/对话框标识/轮数/当前上下文 token/累计花费 token/有效窗口/提醒标记/时间戳/agent。
绝不记录对话正文。

判定口径（policy.json 单一来源）：
- 轮数：默认 8 轮强制、7 轮预警；
- 上下文：当前请求 input_tokens / 当前模型有效窗口，默认 80% 强制、65% 预警；
- 累计 token：只展示成本，不触发换对话。

本文件不发起任何网络调用。不可写时降级到 $TMPDIR/memory-orchestrator/state.json。
"""
try:
    import os as _boot_os, sys as _boot_sys
    _boot_sys.path.insert(0, _boot_os.path.dirname(_boot_os.path.abspath(__file__)))
    import pyboot as _boot_pyboot
    _boot_pyboot.ensure_utf8_io()
except Exception:
    pass

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import i18n
import thread_usage

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

POLICY = thread_usage.load_policy()
STATE = Path(os.environ.get("CODEX_MEMORY_STATE", Path.home() / ".codex" / "memory" / "state.json"))
DEFAULTS = {"active_project": "", "turn_count": 0, "last_checkpoint": "", "last_action": "", "updated_at": ""}
THRESHOLD = int(POLICY.get("turn_threshold", 8))
WARN_AT = int(POLICY.get("turn_warn_at", 7))
CONTEXT_WARN_RATIO = float(POLICY.get("context_warn_ratio", 0.65))
CONTEXT_OVER_RATIO = float(POLICY.get("context_over_ratio", 0.80))
TOKEN_THRESHOLD = int(POLICY.get("absolute_token_threshold", 0) or 0)
TOKEN_WARN_AT = int(POLICY.get("absolute_token_warn_at", 0) or 0)
PEAK_THRESHOLD = int(POLICY.get("request_input_peak_threshold", 0) or 0)
PEAK_WARN_AT = int(POLICY.get("request_input_peak_warn_at", 0) or 0)
AGENT_DEFAULT = os.environ.get("MEMORY_AGENT") or "codex"
STORAGE = {"path": str(STATE), "mode": "primary"}


def _state_fallback():
    p = os.environ.get("CODEX_MEMORY_STATE_FALLBACK")
    if p:
        return Path(p)
    return Path(tempfile.gettempdir()) / "memory-orchestrator" / "state.json"


def storage_path():
    for p in [STATE, _state_fallback()]:
        try:
            if p.exists() or os.access(str(p.parent), os.W_OK):
                return p
        except OSError:
            continue
    return _state_fallback()


def _write_json(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if os.environ.get("CODEX_MEMORY_DIRECT_WRITE") == "1":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        return
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
    """同一 thread_id 永远同一键，不因每轮项目名变化而拆成多条。"""
    if thread_id:
        return thread_id if (not agent or agent == "codex") else f"{thread_id}||@{agent}"
    return active_project or "default"


def _resolve_agent(kv, args=None):
    if isinstance(kv, dict) and kv.get("agent"):
        return kv["agent"]
    if getattr(args, "agent", None):
        return args.agent
    return os.environ.get("MEMORY_AGENT") or AGENT_DEFAULT


def load():
    """只读当前生效的状态文件，避免主文件损坏/为空时把降级文件的旧计数混进来。"""
    d = dict(DEFAULTS)
    p = storage_path()
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    d[k] = v
        except Exception:
            pass
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
        lock_path = str(storage_path()) + ".lock"
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
    d.setdefault("agents", {})[agent] = {
        "agent_alive": True,
        "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return d


def _metric_for(count, ctx, ratio, spent=0, threshold=THRESHOLD, warn_at=WARN_AT,
                token_threshold=TOKEN_THRESHOLD, token_warn_at=TOKEN_WARN_AT,
                ctx_over=CONTEXT_OVER_RATIO, ctx_warn=CONTEXT_WARN_RATIO,
                peak_threshold=PEAK_THRESHOLD, peak_warn_at=PEAK_WARN_AT):
    metric = []
    if count >= threshold:
        metric.append("over_turns")
    elif count >= warn_at:
        metric.append("warn_turns")
    if ratio and ratio >= ctx_over:
        metric.append("over_context")
    elif ratio and ratio >= ctx_warn:
        metric.append("warn_context")
    if token_threshold and spent >= token_threshold:
        metric.append("over_tokens")
    elif token_warn_at and spent >= token_warn_at:
        metric.append("warn_tokens")
    if peak_threshold and ctx >= peak_threshold:
        metric.append("over_input_peak")
    elif peak_warn_at and ctx >= peak_warn_at:
        metric.append("warn_input_peak")
    return "+".join(metric)


def cross_check(d, current_agent=None, threshold=THRESHOLD, warn_at=WARN_AT,
                token_threshold=TOKEN_THRESHOLD, token_warn_at=TOKEN_WARN_AT,
                ctx_over=CONTEXT_OVER_RATIO, ctx_warn=CONTEXT_WARN_RATIO):
    current_agent = current_agent or AGENT_DEFAULT
    others = []
    for key, s in (d.get("dialogs") or {}).items():
        if not isinstance(s, dict):
            continue
        owner = s.get("owner") or s.get("agent") or "codex"
        if owner == current_agent:
            continue
        count = int(s.get("turn_count") or 0)
        ctx = int(s.get("context_tokens") or s.get("token_count") or 0)
        ratio = float(s.get("context_ratio") or (ctx / int(s.get("window_tokens") or 0) if s.get("window_tokens") else 0))
        spent = int(s.get("spent_tokens") or 0)
        metric = _metric_for(count, ctx, ratio, spent, threshold, warn_at, token_threshold,
                             token_warn_at, ctx_over, ctx_warn)
        if not metric:
            continue
        is_over = any(x.startswith("over_") for x in metric.split("+"))
        parts = key.split("||", 2)
        others.append({
            "agent": owner,
            "active_project": s.get("active_project") or parts[0],
            "thread_id": s.get("thread_id") or (parts[0] if len(parts) == 1 else parts[1]),
            "turn_count": count,
            "context_tokens": ctx,
            "context_ratio": round(ratio, 4),
            "spent_tokens": int(s.get("spent_tokens") or 0),
            "metric": metric,
            "status": "over" if is_over else "warn",
        })
    others.sort(key=lambda r: (r["agent"], r["status"] != "over", r["metric"]))
    suggest = [
        {"agent": name, "suggest_install": not bool(m.get("agent_alive"))}
        for name, m in (d.get("agents") or {}).items()
        if name != current_agent and isinstance(m, dict)
    ]
    suggest.sort(key=lambda s: s["agent"])
    return others, suggest


def _attach_storage(out):
    out["storage"] = STORAGE.copy()
    return out


def _merge_legacy(dialogs, new_key, thread_id, agent):
    if not thread_id:
        return {}
    merged = {}
    for k, v in list(dialogs.items()):
        if k == new_key or not isinstance(v, dict):
            continue
        owner = v.get("owner") or v.get("agent") or "codex"
        if (v.get("thread_id") == thread_id) and owner == agent:
            for field in ("turn_count", "context_tokens", "token_count", "spent_tokens", "context_peak"):
                merged[field] = max(int(merged.get(field) or 0), int(v.get(field) or 0))
            merged["warned"] = bool(merged.get("warned")) or bool(v.get("warned"))
            merged["forced"] = bool(merged.get("forced")) or bool(v.get("forced"))
            dialogs.pop(k, None)
    return merged


def _fmt_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    raw = sys.argv[1:]
    lang = i18n.argv_lang(raw)
    desc = ("memory-orchestrator state: get/set/bump/touch/cross-check (no message content)."
            if lang == "en" else "memory-orchestrator 状态：get/set/bump/touch/cross-check（不记对话正文）")
    ap = argparse.ArgumentParser(description=desc)
    i18n.add_lang_arg(ap, default=lang)
    ap.add_argument("action", choices=["get", "set", "bump", "touch", "cross-check"])
    ap.add_argument("kv", nargs="*", help="key=value pairs; bump accepts thread_id=xxx" if lang == "en" else "键值对；bump 支持 thread_id=xxx")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    ap.add_argument("--warn-at", type=int, default=None)
    ap.add_argument("--token-threshold", type=int, default=TOKEN_THRESHOLD)
    ap.add_argument("--token-warn-at", type=int, default=TOKEN_WARN_AT)
    ap.add_argument("--context-over-ratio", type=float, default=CONTEXT_OVER_RATIO)
    ap.add_argument("--context-warn-ratio", type=float, default=CONTEXT_WARN_RATIO)
    ap.add_argument("--thread-id", default=None)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(raw)
    warn_at = args.warn_at if args.warn_at is not None else max(1, args.threshold - 1)

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
            out = _attach_storage({"agent": agent, "agent_alive": True, "status": "ok",
                                   "message": f"{agent} 已登记本机存活标记"})
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return

        if args.action == "cross-check":
            others, suggest = cross_check(d, agent, args.threshold, warn_at,
                                          args.token_threshold, args.token_warn_at,
                                          args.context_over_ratio, args.context_warn_ratio)
            print(json.dumps(_attach_storage({"agent": agent, "others": others,
                                               "suggest_install": suggest}),
                             ensure_ascii=False, indent=2))
            return

        if args.action == "set":
            dialogs = d.setdefault("dialogs", {})
            key = _dialog_key(project or d.get("active_project", ""), thread_id, agent)
            sc = dialogs.get(key, {})
            legacy = _merge_legacy(dialogs, key, thread_id, agent)
            for k, v in kv.items():
                if k in ("active_project", "last_checkpoint", "last_action"):
                    d[k] = v
                elif k == "turn_count":
                    sc["turn_count"] = int(v or 0)
                elif k == "token_count":
                    sc["context_tokens"] = int(v or 0)
                elif k == "context_tokens":
                    sc["context_tokens"] = int(v or 0)
                elif k == "spent_tokens":
                    sc["spent_tokens"] = int(v or 0)
            sc.update({k: v for k, v in legacy.items() if k not in sc})
            if thread_id or "turn_count" in kv or "token_count" in kv:
                sc.update({"thread_id": thread_id or key, "active_project": project or d.get("active_project", ""),
                           "agent": agent, "owner": agent, "checked_at": _fmt_ts()})
                dialogs[key] = sc
            d["active_project"] = d.get("active_project", project)
            d = mark_alive(d, agent)
            save(d)
            print(json.dumps(_attach_storage({"status": "ok", "key": key, "dialog": sc}),
                             ensure_ascii=False, indent=2))
            return

        # bump
        usage = thread_usage.summarize_thread(thread_id) if thread_id else None
        key = _dialog_key(project or d.get("active_project", ""), thread_id, agent)
        dialogs = d.setdefault("dialogs", {})
        cur = dialogs.get(key, {})
        legacy = _merge_legacy(dialogs, key, thread_id, agent)
        cur.update({k: v for k, v in legacy.items() if k not in cur})

        rollout_turns = int((usage or {}).get("turns") or 0)
        prev_count = max(int(cur.get("turn_count") or 0), int(legacy.get("turn_count") or 0))
        count = max(prev_count, rollout_turns) if rollout_turns else prev_count + 1
        ctx = int(kv.get("token_count") or kv.get("context_tokens") or (usage or {}).get("context_tokens") or 0)
        spent = int((usage or {}).get("spent_tokens") or kv.get("spent_tokens") or cur.get("spent_tokens") or 0)
        window = int((usage or {}).get("window_tokens") or cur.get("window_tokens") or POLICY.get("window_fallback") or 0)
        ratio = round(ctx / window, 4) if window else 0.0
        peak = int((usage or {}).get("context_peak") or cur.get("context_peak") or 0)
        model = (usage or {}).get("model") or cur.get("model") or ""

        cur = {
            "thread_id": thread_id or cur.get("thread_id") or key,
            "active_project": project or cur.get("active_project") or d.get("active_project", ""),
            "agent": agent, "owner": agent,
            "turn_count": count,
            "context_tokens": ctx,
            "context_peak": peak,
            "context_ratio": ratio,
            "window_tokens": window,
            "spent_tokens": spent,
            "model": model,
            "warned": bool(cur.get("warned") or legacy.get("warned")),
            "forced": bool(cur.get("forced") or legacy.get("forced")),
            "checked_at": _fmt_ts(),
        }
        dialogs[key] = cur
        d["active_project"] = cur["active_project"] or project
        d["turn_count"] = count
        d = mark_alive(d, agent)

        metric = _metric_for(count, ctx, ratio, spent, args.threshold, warn_at,
                             args.token_threshold, args.token_warn_at,
                             args.context_over_ratio, args.context_warn_ratio)
        over_now = any(x.startswith("over_") for x in metric.split("+")) if metric else False
        warn_now = bool(metric) and not over_now

        out = {"agent": agent, "thread_id": cur["thread_id"], "active_project": cur["active_project"],
               "turn_count": count, "context_tokens": ctx, "context_ratio": ratio,
               "window_tokens": window, "spent_tokens": spent, "context_peak": peak,
               "warned": False, "forced": False, "status": "ok", "action": "continue",
               "message": "", "metric": metric or None,
               "policy": {"turn_threshold": args.threshold, "turn_warn_at": warn_at,
                          "context_over_ratio": args.context_over_ratio,
                          "context_warn_ratio": args.context_warn_ratio,
                          "absolute_token_threshold": args.token_threshold,
                          "request_input_peak_threshold": PEAK_THRESHOLD}}

        if over_now and not cur["forced"]:
            cur["forced"] = True
            cur["warned"] = True
            out.update({"warned": True, "forced": True, "action": "split_now"})
            reasons = []
            if count >= args.threshold:
                reasons.append(f"{count} 轮 ≥ {args.threshold} 轮")
            if ratio >= args.context_over_ratio:
                reasons.append(f"上下文 {ctx}/{window} token（{ratio:.0%}）≥ {args.context_over_ratio:.0%}")
            if args.token_threshold and spent >= args.token_threshold:
                reasons.append(f"累计 token {spent} ≥ {args.token_threshold}")
            if PEAK_THRESHOLD and ctx >= PEAK_THRESHOLD:
                reasons.append(f"单请求 input {ctx} ≥ {PEAK_THRESHOLD}")
            out["message"] = "⚠️ 已达换对话阈值：" + "；".join(reasons) + "。先生成恢复包，再开新对话；本对话不再续接。"
        elif (not cur["forced"]) and (not cur["warned"]) and warn_now:
            cur["warned"] = True
            out.update({"warned": True, "action": "prepare_split"})
            reasons = []
            if count >= warn_at:
                reasons.append(f"已 {count} 轮（{args.threshold} 轮强制）")
            if ratio >= args.context_warn_ratio:
                reasons.append(f"上下文已用 {ratio:.0%}（{ctx}/{window}）")
            if args.token_warn_at and spent >= args.token_warn_at:
                reasons.append(f"累计 token {spent} 接近 {args.token_warn_at}")
            if PEAK_WARN_AT and ctx >= PEAK_WARN_AT:
                reasons.append(f"单请求 input {ctx} 接近 {PEAK_WARN_AT}")
            out["message"] = "⚠️ 接近换对话阈值：" + "；".join(reasons) + "。请准备恢复包，达到阈值后换新对话（只提醒一次）。"
        elif cur["forced"]:
            out["action"] = "split_now"

        dialogs[key] = cur
        save(d)

        if out["warned"]:
            others, suggest = cross_check(d, agent, args.threshold, warn_at,
                                          args.token_threshold, args.token_warn_at,
                                          args.context_over_ratio, args.context_warn_ratio)
            out["cross_check"] = {"others": others, "suggest_install": suggest}
        print(json.dumps(_attach_storage(out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

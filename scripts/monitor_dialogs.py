#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨对话框监测：轮数 + 当前上下文压力 + 累计花费。

关键口径：
- 轮数来自 rollout 的 UserMessage 计数；
- 上下文 = 最近一次模型请求的 input_tokens，和当前模型有效窗口比；
- 累计花费 = thread_token_usage.total_tokens，只展示，不触发换对话；
- 默认只监测正在执行任务的对话框（thread_turns.status='inProgress'）。

只读会话元数据/usage，不读取消息正文；--write-state 才写 state.json。
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
import sqlite3
import tempfile
import time
from pathlib import Path

import thread_usage

CODEX_HOME = thread_usage.codex_home()
SESSIONS_DEFAULT = CODEX_HOME / "sessions"
DB_DEFAULT = CODEX_HOME / "sqlite" / "codex-dev.db"
STATE = Path(os.environ.get("CODEX_MEMORY_STATE", CODEX_HOME / "memory" / "state.json"))
POLICY = thread_usage.load_policy()
DEFAULTS = {"active_project": "", "turn_count": 0, "last_checkpoint": "", "last_action": ""}
THRESHOLD = int(POLICY.get("turn_threshold", 8))
WARN_AT = int(POLICY.get("turn_warn_at", 7))
CONTEXT_WARN_RATIO = float(POLICY.get("context_warn_ratio", 0.65))
CONTEXT_OVER_RATIO = float(POLICY.get("context_over_ratio", 0.80))
TOKEN_THRESHOLD = int(POLICY.get("absolute_token_threshold", 0) or 0)
TOKEN_WARN_AT = int(POLICY.get("absolute_token_warn_at", 0) or 0)


def load_catalog(db_path=None):
    d = {}
    db = db_path or DB_DEFAULT
    if not Path(db).exists():
        return d
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception:
        return d
    try:
        cur = con.execute(
            "SELECT thread_id, display_title, cwd, project_id, source_recency_at FROM local_thread_catalog"
        )
        for tid, title, cwd, pid, rec in cur.fetchall():
            d[tid] = {"title": title or tid, "cwd": cwd or "", "project_id": pid or "", "recency": rec or 0}
    except Exception:
        pass
    finally:
        con.close()
    return d


def load_active_threads(thread_history_db=None, state_db=None):
    """只返回真正 inProgress 的线程；查询成功但为空时返回空集，不再退化成全部未归档。"""
    th = thread_history_db or (CODEX_HOME / "thread_history_1.sqlite")
    if Path(th).exists():
        try:
            con = sqlite3.connect(f"file:{th}?mode=ro", uri=True)
            try:
                return {tid for (tid,) in con.execute(
                    "SELECT DISTINCT thread_id FROM thread_turns WHERE status='inProgress'")}
            finally:
                con.close()
        except Exception:
            pass
    sd = state_db or (CODEX_HOME / "state_5.sqlite")
    if Path(sd).exists():
        try:
            con = sqlite3.connect(f"file:{sd}?mode=ro", uri=True)
            try:
                return {tid for (tid,) in con.execute(
                    "SELECT id FROM threads WHERE archived=0 AND status='inProgress'")}
            finally:
                con.close()
        except Exception:
            pass
    return set()


def load_state():
    d = dict(DEFAULTS)
    if STATE.exists():
        try:
            d.update(json.loads(STATE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return d


def save_state(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    d["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
    fd, tmp = tempfile.mkstemp(prefix=".monitor-state-", suffix=".json", dir=str(STATE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE)
    except BaseException:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _prev_overwarned(st):
    return set((st.get("index") or {}).get("over_warned_ids") or [])


def _write_index(st, rows, over, warn, threshold, warn_at, ctx_over, ctx_warn,
                 token_th, token_wa, full_scan, overwarned_ids):
    idx = dict(st.get("index") or {})
    now = time.strftime("%Y-%m-%d %H:%M")
    idx.update({
        "scanned_files": len(rows), "generated_at": now,
        "threshold": threshold, "warn_at": warn_at,
        "context_over_ratio": ctx_over, "context_warn_ratio": ctx_warn,
        "token_threshold": token_th, "token_warn_at": token_wa,
        "over_warned_ids": sorted(overwarned_ids),
        "sessions": [{
            "id": r["thread_id"], "title": r["title"], "cwd": r["cwd"],
            "turns": r["turns"], "context_tokens": r["context_tokens"],
            "context_ratio": r["context_ratio"], "window_tokens": r["window_tokens"],
            "spent_tokens": r["spent_tokens"],
            "over_warned": r["thread_id"] in overwarned_ids,
        } for r in rows],
    })
    if full_scan:
        idx["last_full_scan"] = now
    st["index"] = idx

    # 同步每个 thread 的状态到 dialogs 表，保证实时钩子与定时兜底共用同一份计数
    dialogs = dict(st.get("dialogs") or {})
    for r in rows:
        tid = r["thread_id"]
        if not tid:
            continue
        ent = dict(dialogs.get(tid) or {})
        ent.update({
            "thread_id": tid,
            "active_project": ent.get("active_project") or r.get("cwd"),
            "turns": r["turns"],
            "context_tokens": r["context_tokens"],
            "context_ratio": r["context_ratio"],
            "window_tokens": r["window_tokens"],
            "spent_tokens": r["spent_tokens"],
            "updated_at": now,
            "source": "monitor",
        })
        ent.setdefault("agent", "codex")
        dialogs[tid] = ent
    st["dialogs"] = dialogs


def _reason(r, args):
    out = []
    if r["turns"] >= args.threshold:
        out.append("over_turns")
    elif r["turns"] >= args.warn_at:
        out.append("warn_turns")
    if r["context_ratio"] >= args.context_over_ratio > 0:
        out.append("over_context")
    elif r["context_ratio"] >= args.context_warn_ratio > 0:
        out.append("warn_context")
    if args.token_threshold and r["context_tokens"] >= args.token_threshold:
        out.append("over_tokens")
    elif args.token_warn_at and r["context_tokens"] >= args.token_warn_at:
        out.append("warn_tokens")
    return "+".join(out)


def _is_over(r, args):
    return (r["turns"] >= args.threshold or
            (args.context_over_ratio > 0 and r["context_ratio"] >= args.context_over_ratio) or
            (args.token_threshold and r["context_tokens"] >= args.token_threshold))


def _is_warn(r, args):
    return (not _is_over(r, args)) and (
        r["turns"] >= args.warn_at or
        (args.context_warn_ratio > 0 and r["context_ratio"] >= args.context_warn_ratio) or
        (args.token_warn_at and r["context_tokens"] >= args.token_warn_at))


def _row_json(r):
    return {
        "thread_id": r["thread_id"], "title": r["title"], "turns": r["turns"],
        "context_tokens": r["context_tokens"], "context_ratio": r["context_ratio"],
        "window_tokens": r["window_tokens"], "spent_tokens": r["spent_tokens"],
        "context_peak": r["context_peak"], "metric": r.get("metric", ""),
        "file": r.get("file", ""),
    }


def _fmt(r):
    proj = (r["cwd"] or r["thread_id"]).split("/")[-1]
    return (f"{r['title']}（{proj}）[{r['thread_id'][:12]}] {r['turns']} 轮，"
            f"上下文 {r['context_tokens']}/{r['window_tokens']}（{r['context_ratio']:.0%}），"
            f"累计 {r['spent_tokens']} token")


def main():
    ap = argparse.ArgumentParser(description="跨对话框轮数/上下文监测")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    ap.add_argument("--warn-at", type=int, default=WARN_AT)
    ap.add_argument("--context-over-ratio", type=float, default=CONTEXT_OVER_RATIO)
    ap.add_argument("--context-warn-ratio", type=float, default=CONTEXT_WARN_RATIO)
    ap.add_argument("--token-threshold", type=int, default=TOKEN_THRESHOLD,
                    help="绝对上下文阈值（默认 0=关闭，仅作特殊场景覆盖）")
    ap.add_argument("--token-warn-at", type=int, default=TOKEN_WARN_AT)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=14)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--sessions-dir", default=str(SESSIONS_DEFAULT))
    ap.add_argument("--catalog-db", default=str(DB_DEFAULT))
    ap.add_argument("--write-state", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--active-only", dest="active_only", action="store_true")
    ap.add_argument("--no-active-only", dest="active_only", action="store_false")
    ap.set_defaults(active_only=True)
    args = ap.parse_args()

    full_scan = bool(args.all)
    sessions_dir = Path(args.sessions_dir)
    files = list(sessions_dir.rglob("rollout-*.jsonl")) if sessions_dir.exists() else []
    cutoff = None if full_scan else time.time() - args.days * 86400
    st = load_state()
    prev_overwarned = _prev_overwarned(st)
    catalog = load_catalog(Path(args.catalog_db))
    active_ids = load_active_threads() if args.active_only else None

    rows = []
    for f in files:
        try:
            if cutoff is not None and f.stat().st_mtime < cutoff:
                continue
            u = thread_usage.read_rollout(f)
        except Exception:
            continue
        if active_ids is not None and u["thread_id"] not in active_ids:
            continue
        meta = catalog.get(u["thread_id"], {})
        rows.append({
            "file": str(f), "thread_id": u["thread_id"],
            "title": meta.get("title", u["thread_id"]), "cwd": meta.get("cwd", ""),
            "project_id": meta.get("project_id", ""),
            "turns": u["turns"], "context_tokens": u["context_tokens"],
            "context_peak": u["context_peak"], "context_ratio": u["context_ratio"],
            "window_tokens": u["window_tokens"], "spent_tokens": u["spent_tokens"],
            "model": u["model"], "mtime": f.stat().st_mtime,
        })
    rows.sort(key=lambda r: r["mtime"], reverse=True)

    over = [r for r in rows if _is_over(r, args)]
    warn = [r for r in rows if _is_warn(r, args)]
    for r in over + warn:
        r["metric"] = _reason(r, args)
    new_over = [r for r in over if r["thread_id"] not in prev_overwarned]
    new_warn = [r for r in warn if r["thread_id"] not in prev_overwarned]

    if args.write_state:
        overwarned_ids = prev_overwarned | {r["thread_id"] for r in new_over} | {r["thread_id"] for r in new_warn}
        _write_index(st, rows, over, warn, args.threshold, args.warn_at,
                     args.context_over_ratio, args.context_warn_ratio,
                     args.token_threshold, args.token_warn_at, full_scan, overwarned_ids)
        save_state(st)

    if args.json:
        print(json.dumps({
            "scanned": len(rows), "threshold": args.threshold, "warn_at": args.warn_at,
            "context_over_ratio": args.context_over_ratio,
            "context_warn_ratio": args.context_warn_ratio,
            "token_threshold": args.token_threshold, "token_warn_at": args.token_warn_at,
            "full_scan": full_scan, "new_reminders": len(new_over) + len(new_warn),
            "warn_sessions": [_row_json(r) for r in warn],
            "over_sessions": [_row_json(r) for r in over],
            "reported_warn_sessions": [_row_json(r) for r in new_warn],
            "reported_over_sessions": [_row_json(r) for r in new_over],
            "total_user_turns": sum(r["turns"] for r in rows),
        }, ensure_ascii=False, indent=2))
        return

    scope = "全量历史" if full_scan else f"最近 {args.days} 天"
    print(f"扫描会话文件: {len(rows)}（{scope}）；轮数 {args.threshold}/{args.warn_at}，"
          f"上下文 {args.context_over_ratio:.0%}/{args.context_warn_ratio:.0%}")
    if new_warn:
        print("⚠️ 接近阈值：")
        for r in new_warn:
            print(f"  - {_fmt(r)}")
    if new_over:
        print("🔴 已超阈值：")
        for r in new_over:
            print(f"  - {_fmt(r)}")
    if not new_over and not new_warn and not over and not warn:
        print("✅ 未发现超阈值或接近阈值的对话")
    elif not new_over and not new_warn:
        print("（已在本机 state.json 标记过的超阈值/接近阈值对话框不再重复提醒）")


if __name__ == "__main__":
    main()

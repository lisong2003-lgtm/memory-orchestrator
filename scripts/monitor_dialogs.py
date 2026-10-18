#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨对话框轮数监测：扫描 .codex/sessions rollouts + app sqlite 目录，统计真实用户轮次。

数据来源（2026-10-18 实测）：
- rollout jsonl 的 event_msg item_completed 中 item.type == "UserMessage" 代表一次用户提问；
- local_thread_catalog 提供 thread_id -> display_title/cwd（用于区分项目）。
只读，不写会话日志；--write-state 才把统计快照写回 .codex/memory/state.json。
纯 stdlib（Python 3.9 可用）。
"""
import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path

def _codex_home():
    # 跨平台：shell 用 ~，Windows 用 %USERPROFILE%/.codex；CODE*: 环境变量可覆盖
    c = os.environ.get("CODEX_HOME") or os.environ.get("OPENAI_CODEX_HOME")
    if c:
        return Path(c)
    return Path.home() / ".codex"


CODEX_HOME = _codex_home()
# 会话目录兼容两层契约：1) CLI/桌面统一 .codex/sessions；2) Windows %USERPROFILE%\.codex\sessions
SESSIONS_DEFAULT = CODEX_HOME / "sessions"
DB_DEFAULT = CODEX_HOME / "sqlite" / "codex-dev.db"
STATE = Path(os.environ.get("CODEX_MEMORY_STATE", CODEX_HOME / "memory" / "state.json"))

DEFAULTS = {"active_project": "", "turn_count": 0, "last_checkpoint": "", "last_action": ""}
THRESHOLD = 8
WARN_AT = 7
_META_RE = re.compile(r"rollout-\d{4}-\d{2}-\d{2}T[\d-]+_?((?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:_(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))*)$")


def _resolve_thread_id(path, fallback):
    m = _META_RE.search(path.stem)
    if not m:
        return fallback
    head = m.group(1).split("_")[0]
    return head


def read_rollout(path):
    """返回 (thread_id, user_turns)。同一 rollout 内按 turn_id 去重。"""
    sid = None
    seen = set()
    turns = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "session_meta":
                p = obj.get("payload") or {}
                sid = p.get("session_id") or p.get("id")
                if sid:
                    seen.clear()  # sid 此时才可信；此前可能的计数仅在无 meta 时受影响
                continue
            p = obj.get("payload")
            if not isinstance(p, dict):
                continue
            if p.get("type") == "item_completed":
                it = p.get("item") or {}
                if it.get("type") != "UserMessage":
                    continue
                tid = p.get("turn_id") or it.get("id")
                key = (sid, tid)
                if tid and key in seen:
                    continue
                seen.add(key)
                turns += 1
    return (_resolve_thread_id(path, sid or path.stem), turns)


def load_catalog(db_path=None):
    d = {}
    db = db_path or (CODEX_HOME / "sqlite" / "codex-dev.db")
    if not Path(db).exists():
        return d
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception:
        return d
    try:
        cur = con.execute(
            "SELECT thread_id, display_title, cwd, project_id, source_recency_at "
            "FROM local_thread_catalog"
        )
        for tid, title, cwd, pid, rec in cur.fetchall():
            d[tid] = {"title": title or tid, "cwd": cwd or "", "project_id": pid or "",
                      "recency": rec or 0}
    finally:
        con.close()
    return d


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
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _fmt(r):
    proj = (r["cwd"] or r["thread_id"]).split("/")[-1]
    return f"{r['title']}（{proj}）[{r['thread_id'][:12]}] {r['turns']} 轮"


def main():
    ap = argparse.ArgumentParser(description="跨对话框轮数监测")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    ap.add_argument("--warn-at", type=int, default=WARN_AT)
    ap.add_argument("--days", type=int, default=14, help="只统计最近 N 天的会话文件")
    ap.add_argument("--sessions-dir", default=str(SESSIONS_DEFAULT), help="Codex 会话目录（跨平台可覆盖）")
    ap.add_argument("--catalog-db", default=str(DB_DEFAULT), help="local_thread_catalog 数据库（找不到时降级用文件元数据）")
    ap.add_argument("--write-state", action="store_true", help="把统计快照写回 state.json")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    sessions_dir = Path(args.sessions_dir)
    files = list(sessions_dir.rglob("rollout-*.jsonl")) if sessions_dir.exists() else []
    cutoff = time.time() - args.days * 86400
    catalog = load_catalog(Path(args.catalog_db))
    rows = []
    for f in files:
        try:
            if f.stat().st_mtime < cutoff:
                continue
            thread_id, turns = read_rollout(f)
        except Exception:
            continue
        meta = catalog.get(thread_id, {})
        rows.append({
            "file": str(f), "thread_id": thread_id,
            "title": meta.get("title", thread_id), "cwd": meta.get("cwd", ""),
            "project_id": meta.get("project_id", ""), "turns": turns,
            "mtime": f.stat().st_mtime,
        })
    rows.sort(key=lambda r: r["mtime"], reverse=True)

    over = [r for r in rows if r["turns"] >= args.threshold]
    warn = [r for r in rows if args.warn_at <= r["turns"] < args.threshold]

    if args.write_state:
        st = load_state()
        st["index"] = {
            "scanned_files": len(rows),
            "generated_at": time.strftime("%Y-%m-%d %H:%M"),
            "threshold": args.threshold, "warn_at": args.warn_at,
            "sessions": [
                {"id": r["thread_id"], "title": r["title"], "cwd": r["cwd"],
                 "turns": r["turns"]} for r in rows
            ],
        }
        save_state(st)

    if args.json:
        print(json.dumps({
            "scanned": len(rows), "threshold": args.threshold, "warn_at": args.warn_at,
            "warn_sessions": [{"thread_id": r["thread_id"], "title": r["title"], "turns": r["turns"]} for r in warn],
            "over_sessions": [{"thread_id": r["thread_id"], "title": r["title"], "turns": r["turns"]} for r in over],
            "total_user_turns": sum(r["turns"] for r in rows),
        }, ensure_ascii=False, indent=2))
        return

    print(f"扫描会话文件: {len(rows)}（最近 {args.days} 天）；阈值 {args.threshold}，提醒线 {args.warn_at}")
    if warn:
        print("⚠️ 接近阈值：")
        for r in warn:
            print(f"  - {_fmt(r)}")
    if over:
        print("🔴 已超阈值：")
        for r in over:
            print(f"  - {_fmt(r)}")
    if not warn and not over:
        print("✅ 未发现超阈值或接近阈值的对话")


if __name__ == "__main__":
    main()

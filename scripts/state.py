#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-orchestrator 会话状态：轮次计数、最近 checkpoint、活跃项目。"""
import argparse
import json
import os
import sys
from pathlib import Path
import time

STATE = Path(os.environ.get("CODEX_MEMORY_STATE", Path.home() / ".codex" / "memory" / "state.json"))
DEFAULTS = {"active_project": "", "turn_count": 0, "last_checkpoint": "", "last_action": ""}

def load():
    d = dict(DEFAULTS)
    if os.path.exists(STATE):
        try:
            d.update(json.load(open(STATE, encoding="utf-8")))
        except Exception:
            pass
    return d

def save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    d["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(d, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["get", "set", "bump"], help="get=读取, set k=v, bump=轮次+1")
    ap.add_argument("kv", nargs="*")
    args = ap.parse_args()
    d = load()
    if args.action == "get":
        print(json.dumps(d, ensure_ascii=False))
    elif args.action == "set":
        for kv in args.kv:
            if "=" in kv:
                k, v = kv.split("=", 1)
                if k in ("active_project", "last_checkpoint", "last_action"):
                    d[k] = v
                elif k == "turn_count":
                    d[k] = int(v)
        save(d)
    elif args.action == "bump":
        for kv in args.kv:
            if "=" in kv:
                k, v = kv.split("=", 1)
                d[k] = v
        d["turn_count"] = int(d.get("turn_count") or 0) + 1
        save(d)
        print(json.dumps({"turn_count": d["turn_count"], "active_project": d.get("active_project")}))

if __name__ == "__main__":
    main()

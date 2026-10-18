#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复包索引登记：.codex/memory/recovery-index.md 追加一行（按路径去重）。"""
import argparse
import os
import time
from pathlib import Path

INDEX = Path(os.environ.get("RECOVERY_INDEX", Path.home() / ".codex" / "memory" / "recovery-index.md"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=2, metavar=("PROJECT", "PATH"), help="project 与恢复包路径")
    args = ap.parse_args()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    if not INDEX.exists():
        INDEX.write_text("# 恢复包索引\n\n| 项目 | 恢复包路径 | 登记时间 |\n|---|---|---|\n", encoding="utf-8")
    if args.add:
        project, path = args.add
        lines = INDEX.read_text(encoding="utf-8").splitlines()
        if path not in "".join(lines[2:]):
            ts = time.strftime("%Y-%m-%d %H:%M")
            line = f"| {project} | {path} | {ts} |"
            INDEX.write_text("\n".join(lines + [line]) + "\n", encoding="utf-8")
            print(f"added: {project} -> {path}")
        else:
            print("already indexed")
    else:
        print(INDEX.read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()

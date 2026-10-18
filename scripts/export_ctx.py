#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Codex rollout jsonl 转成 ctxcompress 可消费的 messages 数组。"""
import argparse
import glob
import json
import sys
from pathlib import Path

def _text(item):
    c = item.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict):
                t = p.get("type", "")
                if t in ("text", "input_text", "output_text"):
                    parts.append(p.get("text", "") or "")
                else:
                    parts.append(p.get("text") or p.get("content") or "")
            elif p:
                parts.append(str(p))
        return "".join(parts)
    return ""

def extract(path, limit):
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("response_item"), dict):
                it = obj["response_item"]
                if it.get("type") == "message":
                    txt = _text(it)
                    if txt.strip():
                        msgs.append({"role": it.get("role", "assistant"), "content": txt})
                if limit and len(msgs) >= limit:
                    break
                continue
            if isinstance(obj, dict) and isinstance(obj.get("message"), dict):
                m = obj["message"]
                txt = _text(m)
                if txt.strip():
                    msgs.append({"role": m.get("role", "assistant"), "content": txt})
            elif isinstance(obj, dict) and obj.get("role") in ("user", "assistant"):
                txt = _text(obj)
                if txt.strip():
                    msgs.append({"role": obj["role"], "content": txt})
            if limit and len(msgs) >= limit:
                break
    return msgs

def main():
    ap = argparse.ArgumentParser(description="将 Codex rollout jsonl 转成 messages 数组")
    ap.add_argument("--input", "-i", required=True, help="rollout jsonl 文件或 glob")
    ap.add_argument("--output", "-o", default="-")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--project", "-p", default="", help="必填项目/会话标识，用于限定读取范围")
    ap.add_argument("--allow-all-sessions", action="store_true",
                    help="仅在用户明确确认读取全部会话时使用；否则拒绝全目录通配")
    args = ap.parse_args()
    files = [Path(f) for f in (glob.glob(args.input) or [args.input])]
    if "**" in args.input and not args.allow_all_sessions:
        sys.stderr.write("拒绝全目录通配：请使用 --project/-p 指定项目并用项目限定路径；确需全量读取时加 --allow-all-sessions 且已获用户明确确认。\n")
        sys.exit(2)
    project = args.project.strip()
    keep = []
    for f in files:
        if not f.exists():
            continue
        fp = str(f)
        if project:
            if project in fp or (f.parent.name and project in f.parent.name):
                keep.append(f)
        else:
            keep.append(f)
    files = keep
    if project and not files:
        sys.stderr.write("未找到与项目标识匹配的 rollout 文件。请核对 --project 与 --input 范围。\n")
        sys.exit(2)
    msgs = []
    for fp in files:
        msgs.extend(extract(str(fp), 0 if args.limit == 0 else args.limit - len(msgs)))
        if args.limit and len(msgs) >= args.limit:
            break
    text = json.dumps(msgs, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(text + "\n")
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    print(f"# exported {len(msgs)} messages", file=sys.stderr)

if __name__ == "__main__":
    main()

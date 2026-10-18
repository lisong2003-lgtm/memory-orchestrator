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
    args = ap.parse_args()
    files = glob.glob(args.input) or [args.input]
    msgs = []
    for fp in files:
        msgs.extend(extract(fp, 0 if args.limit == 0 else args.limit - len(msgs)))
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

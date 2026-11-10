#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_gate.py — 五项记忆闸门统一判定（单一策略源 policy.json）。

输入 JSON 字段（未知字段忽略，缺失按 0 计）：
  turns               对话轮数
  total_tokens        累计 token（input+output）
  request_input_peak  单请求 input 峰值
  request_count       模型请求次数
  session_input       单会话累计 input

用法：
  python3 memory_gate.py --stats stats.json
  cat stats.json | python3 memory_gate.py --stdin
  python3 memory_gate.py --dry-run     # 5 个固定样例，每个只触发一项，期望 5/5

输出：JSON（--dry-run 为逐样例文本 + 汇总）。
任一闸门先到 → action=handoff（先生成恢复包，再开新对话）。
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE.parent / "policy.json"

DEFAULT_POLICY = {
    "turn_threshold": 8,
    "absolute_token_threshold": 150000,
    "request_input_peak_threshold": 100000,
    "request_count_threshold": 120,
    "session_input_threshold": 8000000,
}

GATES = [
    ("turns", "turn_threshold", "轮数"),
    ("total_tokens", "absolute_token_threshold", "累计 token"),
    ("request_input_peak", "request_input_peak_threshold", "单请求 input 峰值"),
    ("request_count", "request_count_threshold", "请求次数"),
    ("session_input", "session_input_threshold", "单会话累计 input"),
]

SAMPLES = [
    ("turns", {"turns": 8, "total_tokens": 149999, "request_input_peak": 99999,
               "request_count": 119, "session_input": 7999999}),
    ("total_tokens", {"turns": 7, "total_tokens": 150000, "request_input_peak": 99999,
                      "request_count": 119, "session_input": 7999999}),
    ("request_input_peak", {"turns": 7, "total_tokens": 149999, "request_input_peak": 100000,
                            "request_count": 119, "session_input": 7999999}),
    ("request_count", {"turns": 7, "total_tokens": 149999, "request_input_peak": 99999,
                       "request_count": 120, "session_input": 7999999}),
    ("session_input", {"turns": 7, "total_tokens": 149999, "request_input_peak": 99999,
                       "request_count": 119, "session_input": 8000000}),
]


def load_policy():
    p = dict(DEFAULT_POLICY)
    try:
        loaded = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            p.update(loaded)
    except Exception as e:
        print(f"WARN policy.json 读取失败，用内置默认: {e}", file=sys.stderr)
    return p


def evaluate(stats, policy):
    out = []
    for field, key, label in GATES:
        value = int(stats.get(field) or 0)
        threshold = int(policy.get(key) or 0)
        hit = bool(threshold) and value >= threshold
        out.append({"gate": field, "label": label, "value": value,
                    "threshold": threshold, "triggered": hit})
    triggered = [g["gate"] for g in out if g["triggered"]]
    return {
        "action": "handoff" if triggered else "continue",
        "triggered_by": triggered,
        "gates": out,
        "policy_version": policy.get("version"),
    }


def dry_run(policy):
    ok = 0
    for expected, stats in SAMPLES:
        r = evaluate(stats, policy)
        good = r["action"] == "handoff" and r["triggered_by"] == [expected]
        print(f"{'PASS' if good else 'FAIL'}  {expected}: action={r['action']} "
              f"triggered_by={','.join(r['triggered_by']) or '-'}")
        ok += 1 if good else 0
    print(f"GATES {ok}/{len(SAMPLES)}")
    return 0 if ok == len(SAMPLES) else 1


def main():
    ap = argparse.ArgumentParser(description="五项记忆闸门判定")
    ap.add_argument("--stats", help="统计 JSON 文件")
    ap.add_argument("--stdin", action="store_true", help="从标准输入读 JSON")
    ap.add_argument("--dry-run", action="store_true", help="跑 5 个固定样例")
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认也是 JSON）")
    args = ap.parse_args()

    policy = load_policy()
    if args.dry_run:
        return dry_run(policy)
    if args.stdin or not args.stats:
        raw = sys.stdin.read()
        stats = json.loads(raw) if raw.strip() else {}
    else:
        stats = json.loads(Path(args.stats).read_text(encoding="utf-8"))
    result = evaluate(stats, policy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

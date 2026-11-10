#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read Codex rollout usage without reading conversation content.

Contract:
- turns: number of completed UserMessage items in the rollout.
- context_tokens: input tokens of the latest model request (current context pressure).
- context_peak: largest input-token count seen in this rollout (diagnostic only).
- spent_tokens: cumulative thread_token_usage.total_tokens (billing/cost display only).
- window_tokens: runtime model_context_window reported by Codex, else policy fallback.

This module never prints or stores message text.
"""
import json
import os
import re
from pathlib import Path

try:
    import fcntl  # noqa: F401
except Exception:
    pass

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
POLICY_PATH = SKILL_DIR / "policy.json"
DEFAULT_POLICY = {
    "turn_threshold": 8,
    "turn_warn_at": 7,
    "context_warn_ratio": 0.65,
    "context_over_ratio": 0.80,
    "window_fallback": 128000,
    "absolute_token_threshold": 0,
    "absolute_token_warn_at": 0,
}
_META_RE = re.compile(
    r"rollout-\d{4}-\d{2}-\d{2}T[\d-]+_?("
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:_(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))*"
    r")$"
)


def codex_home():
    c = os.environ.get("CODEX_HOME") or os.environ.get("OPENAI_CODEX_HOME")
    return Path(c) if c else Path.home() / ".codex"


def load_policy():
    d = dict(DEFAULT_POLICY)
    try:
        loaded = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            d.update(loaded)
    except Exception:
        pass
    env_map = {
        "TURN_THRESHOLD": ("turn_threshold", int),
        "TURN_WARN_AT": ("turn_warn_at", int),
        "CONTEXT_WARN_RATIO": ("context_warn_ratio", float),
        "CONTEXT_OVER_RATIO": ("context_over_ratio", float),
        "TOKEN_THRESHOLD": ("absolute_token_threshold", int),
        "TOKEN_WARN_AT": ("absolute_token_warn_at", int),
        "MEMORY_WINDOW_FALLBACK": ("window_fallback", int),
    }
    for env, (key, cast) in env_map.items():
        raw = os.environ.get(env)
        if raw is None or raw == "":
            continue
        try:
            d[key] = cast(raw)
        except Exception:
            pass
    return d


def resolve_thread_id(path, fallback=None):
    m = _META_RE.search(path.stem)
    if not m:
        return fallback or path.stem
    return m.group(1).split("_")[0]


def _num(d, key):
    if not isinstance(d, dict):
        return 0
    try:
        return int(d.get(key) or 0)
    except Exception:
        return 0


def read_rollout(path):
    path = Path(path)
    sid = None
    seen = set()
    turns = 0
    context_tokens = 0
    context_peak = 0
    spent_tokens = 0
    window_tokens = 0
    model = ""

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
                sid = p.get("session_id") or p.get("id") or sid
                model = p.get("model") or model
                seen.clear()
                continue
            p = obj.get("payload")
            if not isinstance(p, dict):
                continue
            otype = obj.get("type")

            if otype == "token_usage_record":
                usage = p.get("usage") or {}
                ctx = _num(usage, "input_tokens") or _num(usage, "total_tokens")
                if ctx:
                    context_tokens = ctx
                    context_peak = max(context_peak, ctx)
                spent = _num(p.get("thread_token_usage"), "total_tokens")
                if spent:
                    spent_tokens = max(spent_tokens, spent)
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
                continue

            if otype == "event_msg":
                info = p.get("info") or {}
                last = info.get("last_token_usage") or {}
                ctx = _num(last, "input_tokens") or _num(last, "total_tokens")
                if ctx:
                    context_tokens = ctx
                    context_peak = max(context_peak, ctx)
                spent = _num(info.get("total_token_usage"), "total_tokens")
                if spent:
                    spent_tokens = max(spent_tokens, spent)
                w = _num(info, "model_context_window")
                if w:
                    window_tokens = w

    policy = load_policy()
    if not window_tokens:
        window_tokens = int(policy.get("window_fallback") or 128000)
    return {
        "thread_id": resolve_thread_id(path, sid or path.stem),
        "turns": turns,
        "context_tokens": context_tokens,
        "context_peak": context_peak,
        "spent_tokens": spent_tokens,
        "window_tokens": window_tokens,
        "context_ratio": round(context_tokens / window_tokens, 4) if window_tokens else 0,
        "model": model,
        "file": str(path),
    }


def find_rollout(thread_id, sessions_dir=None):
    if not thread_id:
        return None
    root = Path(sessions_dir) if sessions_dir else codex_home() / "sessions"
    if not root.exists():
        return None
    matches = list(root.rglob("rollout-*%s.jsonl" % thread_id))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def summarize_thread(thread_id, sessions_dir=None):
    path = find_rollout(thread_id, sessions_dir)
    if not path:
        return None
    try:
        return read_rollout(path)
    except Exception:
        return None

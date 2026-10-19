#!/usr/bin/env bash
# memory-orchestrator：任意 Agent 每轮结束时调用的实时自检钩子。
# 只统计轮数（bump），不读取/不记录对话正文；纯本地，不上传网络。
# 用法（在 Agent 规则中固化，每轮用户提问结束时执行一次）：
#   MEMORY_AGENT=claude bash <skill>/scripts/agent_hook.sh active_project=项目名 thread_id=对话框ID
#   bash <skill>/scripts/agent_hook.sh agent=claude active_project=项目名 thread_id=对话框ID
# 可用环境变量覆盖阈值：TURN_THRESHOLD / TURN_WARN_AT（默认 8 / 7）。
set -u
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
exec env \
  ${CODEX_MEMORY_STATE:+CODEX_MEMORY_STATE="$CODEX_MEMORY_STATE"} \
  ${MEMORY_AGENT:+MEMORY_AGENT="$MEMORY_AGENT"} \
  ${TURN_THRESHOLD:+TURN_THRESHOLD="$TURN_THRESHOLD"} \
  ${TURN_WARN_AT:+TURN_WARN_AT="$TURN_WARN_AT"} \
  "$PYTHON" "$SKILL_DIR/scripts/state.py" bump "$@"

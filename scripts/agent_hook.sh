#!/usr/bin/env bash
# memory-orchestrator：每轮用户提问结束时调用的本地自检钩子。
# 自动从当前 thread 的 rollout usage 读取轮数/上下文/累计花费，不读取消息正文、不联网。
# 用法：
#   bash <skill>/scripts/agent_hook.sh agent=codex active_project=项目名 thread_id=对话框ID
# 阈值只在 <skill>/policy.json 维护；环境变量仅作临时覆盖。
set -u
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
exec env \
  ${CODEX_MEMORY_STATE:+CODEX_MEMORY_STATE="$CODEX_MEMORY_STATE"} \
  ${CODEX_MEMORY_STATE_FALLBACK:+CODEX_MEMORY_STATE_FALLBACK="$CODEX_MEMORY_STATE_FALLBACK"} \
  ${MEMORY_AGENT:+MEMORY_AGENT="$MEMORY_AGENT"} \
  ${TURN_THRESHOLD:+TURN_THRESHOLD="$TURN_THRESHOLD"} \
  ${TURN_WARN_AT:+TURN_WARN_AT="$TURN_WARN_AT"} \
  ${CONTEXT_WARN_RATIO:+CONTEXT_WARN_RATIO="$CONTEXT_WARN_RATIO"} \
  ${CONTEXT_OVER_RATIO:+CONTEXT_OVER_RATIO="$CONTEXT_OVER_RATIO"} \
  ${TOKEN_THRESHOLD:+TOKEN_THRESHOLD="$TOKEN_THRESHOLD"} \
  ${TOKEN_WARN_AT:+TOKEN_WARN_AT="$TOKEN_WARN_AT"} \
  "$PYTHON" "$SKILL_DIR/scripts/state.py" bump "$@"

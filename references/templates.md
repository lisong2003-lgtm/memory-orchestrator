# 恢复包模板

## 模板说明

当用户说“总结 / 压缩 / 恢复 / 交接 / 开新对话”，或对话超过 12 轮时，按下面模板生成恢复包。目标：新对话只读此文件即可 5 行以内接续。

## recovery-package.md

```markdown
# 恢复包：<主题>

- 会话日期：YYYY-MM-DD
- 最近一次更新：YYYY-MM-DD HH:mm
- 状态：进行中 / 待核对 / 已完成

## 1 目标
一句话说明本次任务目标。

## 2 已完成
- 关键成果 1（含文件路径）
- 关键成果 2

## 3 关键决策与依据
| 决策 | 依据 | 状态 |
|---|---|---|
| xxx | 用户要求/规范/经验 | 已定/待确认 |

## 4 下一步（可执行）
- [ ] 具体动作 1（命令或文件路径）
- [ ] 具体动作 2

## 5 未决 / 风险
- 需用户确认事项
- 环境或数据风险

## 6 交接
- 交接对象：新对话 / 用户
- 验证方式：读恢复包后向用户复述 5 行摘要
```

## ctxcompress 使用

```sh
# 1) 把 Codex rollout jsonl 转成 messages 数组
python3 ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/export_ctx.py -i "$HOME/.codex/sessions/**/*.jsonl" -o /tmp/chat.json
# 2) 压缩
${CODEX_HOME:-$HOME/.codex}/tools/agent-ctx-compress/bin/ctxcompress --input /tmp/chat.json --ratio 0.3 --format compact --output /tmp/compact.txt
```

ctxcompress 不可用时，手写 5-8 行摘要，包含：目标、已完成、关键决策、下一步、未决。

## hot.md 最低降级格式

```markdown
# 最近进行中任务

- 主题：
- 目标：
- 已完成（最近）：
- 下一步：
- 未决：
- 时间：
```

新对话优先读 cp-memory；读不到再读 hot.md。

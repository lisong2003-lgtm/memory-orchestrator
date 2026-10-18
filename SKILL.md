---
name: memory-orchestrator
description: 长对话记忆编排技能。负责会话开始时的记忆检索、对话超过12轮/上下文变模糊时的开新对话提醒与恢复包生成、checkpoint、历史压缩（ctxcompress）、会话结束归档。触发词：“总结/压缩/恢复/交接/开新对话/checkpoint”。
version: 1.1.1
---

# memory-orchestrator

长对话记忆管理的中枢。目标是：上下文不失控、新对话 5 行内接续、关键决定不丢失。

## 会话状态（每次会话开始/结束）

- 状态文件：`${CODEX_HOME:-$HOME/.codex}/memory/state.json`
- 更新命令：
  ```sh
  ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/state.py set active_project=<项目名>
  ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/state.py bump active_project=<项目名>   # 每轮+1
  ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/state.py get
  ```
- 判断“超 12 轮”：`turn_count >= 12` 或同一轮次连续 2 次工具报上下文混淆时，触发提醒开新对话（先生成恢复包）。
- 每次 checkpoint 后把 `last_checkpoint` 和 `last_action` 写回 state.json。

## cp-memory 工具调用清单（真实签名，2026-10-18 实测）

- 会话开始检索：`memory_recall(query=项目名或主题, intent=resume, limit=5)`；也可 `memory_search(query=..., limit=5)` / `memory_probe(entity=<项目名>)`。
- 写 checkpoint/归档：`memory_add(entity=<项目名>, property=next_step|decision|checkpoint, value=一句话, tags="checkpoint|archive", content=长文本可选)`。
- 记决策：`memory_decision_add(title, context, decision, rationale)`。
- 记当前任务：`memory_task_set(task_name=...)`；完成：`memory_task_done(result=...)`。
- 恢复上下文：`memory_restore_context(prompt=最近问题, max_chars=...)`。
- 状态核对：`memory_health()` / `memory_stats()`。
- 多项目隔离：`entity` 一律用项目名；tags 带项目名，避免串记。
- 以上工具名均来自本机 `cp-memory-mcp`（v1.30.0）`tools/list` 实测结果。

## Checkpoint（每 10-12 轮或里程碑）

1. 导出可压缩源（仅当前项目/会话，禁止默认扫全部日志）：先用 `state.py get` 确认 active_project，再用 `scripts/export_ctx.py` 指定该项目 rollout 文件转成 messages 数组；压缩前向用户说明将读取的范围与用途。

   ```sh
   python3 ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/export_ctx.py -i "$HOME/.codex/sessions/**/rollout-*<项目>*.jsonl" -o /tmp/chat-<项目>.json
   ${CODEX_HOME:-$HOME/.codex}/tools/agent-ctx-compress/bin/ctxcompress --input /tmp/chat-<项目>.json --stats-only
   ```
   仅当前 active_project；range/作用域不明确时先向用户确认。压缩产出是摘要，不把原文写进长期记忆。
2. 无法获得对话转储时，按规则手写压缩摘要（5-8 行，见 `references/templates.md`）。
3. 把 checkpoint 通过 `memory_add(...tags="checkpoint")` 写入 cp-memory，并同步更新 hot.md 与 state.json。

## 压缩（ctxcompress）

- ctxcompress 是 **CLI**，只能经 shell 调用，绝不注册为 MCP 工具。
- 命令形态：

  ```sh
  python3 ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/export_ctx.py -i "<rollout路径/glob>" -o /tmp/chat.json
  ${CODEX_HOME:-$HOME/.codex}/tools/agent-ctx-compress/bin/ctxcompress --input /tmp/chat.json --ratio 0.3 --format compact --output /tmp/compact.txt
  ```

- 常用参数：`--stats-only` 看占比；`--ratio 0.3-0.5` 保守压缩；`--no-summarize` 只去重。
- 工具不可用或异常时，降级为 5-8 行手动摘要，降级原因写进交接包，不静默假装压缩。

## 恢复包

- 命名固定：`恢复包-<项目名>-<YYYYMMDD>.md`。
- 生成后登记索引：
  ```sh
  python3 ${CODEX_HOME:-$HOME/.codex}/skills/memory-orchestrator/scripts/recovery.py --add <项目名> <恢复包路径>
  ```
- 索引文件：`${CODEX_HOME:-$HOME/.codex}/memory/recovery-index.md`，新对话先读它定位最近恢复包。
- 模板见 `references/templates.md`；字段：会话信息、目标与已完成、关键决策与依据、下一步、未决/风险、交接对象与验证方式。

## 归档（会话结束或“总结/交接”）

1. 汇总本次目标、决定、下一步 → cp-memory（`memory_add(entity=项目名, tags="archive")` 或 `memory_decision_add`）。
2. 更新 `${CODEX_HOME:-$HOME/.codex}/memory/hot.md` 顶部（只保留最近 1 个项目的最新状态；切换项目前先把旧项目状态写入 cp-memory 防覆盖丢失）。
3. 若需要人类可读交接文档，同时生成恢复包并登记进 `recovery-index.md`。
4. 结束前把 `turn_count`、`last_checkpoint` 写回 state.json。

## 记忆规则

- 只记结论与决策，不抄过程日志。
- 每条记忆带：主题、时间、状态（进行中/完成/归档）、下一步、责任人（默认用户）。
- 同主题用增量更新（幂等），不重复追加相似条目。
- 多项目并存：cp-memory 按 `entity`+`tags` 隔离；`hot.md` 只做“最近一个任务”的最低保底。
- 公司数据红线不变：本机与公司介质外发仍需遵守项目 AGENTS.md；本技能只做本地记忆，不把内容传云端。

## 禁忌

- 不得把 ctxcompress 当 MCP 服务器注册。
- 不得在 cp-memory 不可用时停摆：至少落到 `${CODEX_HOME:-$HOME/.codex}/memory/hot.md`。
- 不得用“换新对话”替代真实交接：必须先生成恢复包/记忆摘要再提醒开新对话。
- 不得在压缩时丢弃未决问题、下一步、关键数字。
- 不得在未切换项目时整份覆盖 hot.md（先归档旧项目）。
- 不读取或替代施工日志/会议纪要等既有项目技能的作用域。

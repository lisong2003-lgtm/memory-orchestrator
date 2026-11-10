# memory-orchestrator · 会话状态（state.py） / cp-memory 工具调用清单（含 Checkpoint） / 定时兜底监测

- 来源：`$CODEX_HOME/skills/memory-orchestrator/SKILL.md`（M6 P2 外移，2026-11-08，原文逐字保留）
- 用法：需要该细节时整篇读取；主文件只保留触发、流程、红线、契约与关键命令。

## 会话状态（state.py）

```sh
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/state.py get
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/state.py bump active_project=<项目> thread_id=<对话框ID>
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/state.py touch agent=codex
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/state.py cross-check agent=codex --json
```

- 状态文件 `$CODEX_HOME/memory/state.json`；每个 `thread_id` 一条记录，项目名变化不拆键。
- 记录字段只有：项目名、thread_id、agent、轮数、`context_tokens`、`context_peak`、`context_ratio`、`window_tokens`、`spent_tokens`、提醒标记、时间戳；不含正文。
- `bump` 输出 `action`（continue / prepare_split / split_now）和 `metric`（warn_turns / over_turns / warn_context / over_context / warn_tokens / over_tokens / warn_input_peak / over_input_peak）；累计 token 与单请求峰值参与判定。
- 文件锁 + 临时文件原子写；主路径不可写时降级 `$TMPDIR/memory-orchestrator/state.json`，输出 `storage.mode=fallback`。

## cp-memory 工具调用清单（含 Checkpoint）

- 会话开始检索：`memory_recall(query=项目名或主题, intent=resume, limit=5)`；也可 `memory_search(query=..., limit=5)` / `memory_probe(entity=<项目名>)`。
- 写 checkpoint/归档：`memory_add(entity=<项目名>, property=next_step|decision|checkpoint, value=一句话, tags="checkpoint|archive", content=长文本可选)`。
- 记决策：`memory_decision_add(title, context, decision, rationale)`。
- 任务状态：`memory_task_set(task_name=...)`；完成：`memory_task_done(result=...)`。
- 恢复上下文：`memory_restore_context(prompt=最近问题, max_chars=...)`；核对：`memory_health()` / `memory_stats()`。
- 多项目隔离：`entity` 一律用项目名，tags 带项目名，避免串记。
- checkpoint 触发：8 轮、里程碑（如单轮图纸批次 >10 张）、或 `prepare_split` 预警后；先 `export_ctx.py --project <项目>` 导出当前项目，再用 ctxcompress 压缩；无法导出时写 5-8 行手动摘要。
- 每次 checkpoint 把 `last_checkpoint`、`last_action` 写回 state.json，并 `memory_add(...tags="checkpoint")`。

## 定时兜底监测

```sh
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/monitor_dialogs.py \
  --days 3 --write-state --json
```

- 默认只监测 `thread_turns.status='inProgress'`；查询成功但为空时返回空集，不再退化成“全部未归档”。
- `--all` 全量扫描，`--no-active-only` 关闭活跃过滤，仅排查历史时使用。
- `--json` 字段：`turns`、`context_tokens`、`context_ratio`、`window_tokens`、`spent_tokens`、`context_peak`。
- 需要无人值守时用 `~/Library/LaunchAgents/com.lis.memory-orchestrator.plist`，每小时跑一次；日志在 `~/Library/Logs/memory-orchestrator.out.log` / `.err.log`。

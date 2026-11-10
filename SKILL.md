---
name: memory-orchestrator
slug: codex-memory-orchestrator
displayName: 对话记忆管家 · Memory Orchestrator
description: 长对话记忆编排技能。统一管理五项记忆闸门、上下文窗口口径、token 成本展示、恢复包、checkpoint、历史压缩和换新对话；任一先到即交接：轮数≥8、累计 token≥150000、单请求 input 峰值≥100000、请求次数≥120、单会话累计 input≥8000000；只监测正在执行任务的对话框，不读消息正文、不上传网络。
version: 2.1.0
platforms: [macos, windows, linux]
i18n:
  en: README.en.md
  zh: README.md
locale: zh-CN
locales: [zh-CN, en-US]
---

# memory-orchestrator

长对话记忆管理的中枢。目标：上下文不失控、新对话 5 行内接续、关键决定不丢失，同时不把“窗口上限”误当成“已消耗 token”。

## 按需加载（长文外移）

| 需要什么 | 读哪里 |
|---|---|
| state.json 字段、bump 与原子写细节 | `references/tooling.md` |

## 单一策略源

所有数值只在 `policy.json` 维护；SKILL、全局 `AGENTS.md`、脚本不得各写一套。

```json
{
  "turn_threshold": 8,
  "turn_warn_at": 7,
  "context_warn_ratio": 0.65,
  "context_over_ratio": 0.80,
  "window_fallback": 128000,
  "absolute_token_threshold": 150000,
  "absolute_token_warn_at": 120000,
  "request_input_peak_threshold": 100000,
  "request_input_peak_warn_at": 80000,
  "request_count_threshold": 120,
  "session_input_threshold": 8000000
}
```

- 五项闸门任一先到即交接：轮数≥8；累计 token（input+output）≥150000；单请求 input 峰值≥100000；请求次数≥120；单会话累计 input≥8000000。判定用 `scripts/memory_gate.py`。
- 上下文比例：`当前请求 input_tokens / 当前模型有效窗口`，`>= 80%` 强制，`>= 65%` 预警；作为加速线，不替代五项闸门。
- 累计 token 口径：`input + output`；`cache_read` 是 input 子集不得重复相加。`spent_tokens` 用于累计闸门与成本展示。
- 临时覆盖可用环境变量：`TURN_THRESHOLD`、`TURN_WARN_AT`、`CONTEXT_WARN_RATIO`、`CONTEXT_OVER_RATIO`；长期调整改 `policy.json`。

## 会话状态（state.py）

> 已外移，按需加载：`references/tooling.md`。`state.py get|bump|touch|cross-check`；状态键是 `thread_id`；`bump` 返回 continue/prepare_split/split_now；不可写时降级 `$TMPDIR/memory-orchestrator/state.json`。

## 窗口与 token 口径（为什么以前会误判）

- **窗口上限本身不消耗 token**。它只决定什么时候压缩、什么时候会超窗断流。
- 真正消耗 token 的是：每轮把多大的上下文重新发给模型，以及一轮里发生了多少次工具调用。
- `config.toml` 的 `model_context_window` 是应用层覆盖，不等于 provider 真实上限；真实值看模型目录的 `context_window × effective_context_window_percent`，或会话 `event_msg.info.model_context_window`。
- 本机 `deepseek-v4.1-flash-1017` 的模型目录是 `128000 × 95% = 121600`；即使 config 写 400000，运行时仍是 121600。因此不能用“200000/400000 固定值”当全局规则。
- 旧版把 `thread_token_usage.total_tokens`（累计计费，含缓存命中和多轮工具调用）当上下文阈值，7 轮就可能显示数百万 token，必然误报。现在分开：
  - `context_tokens`：最近一次请求的输入 token，用来判断上下文压力；
  - `context_peak`：本对话历史最高上下文，仅诊断；
  - `spent_tokens`：累计 input+output token，用于累计闸门与成本展示。

## 省 token 执行细则（全局规则迁入）

省 token 不靠“少干活”，靠不重复搬运已知信息。以下细则由本技能统一管理，全局 `AGENTS.md` 只保留底线。

- 工具输出只取需要的字段：错误日志只留最后 5 行；文件列表给前 5 + 总数；搜索结果前 3 + 摘要；重复命令写“同前”+ 变化；代码 diff 只给必要 hunk。
- 长文档、图纸清单、测试日志分段落盘，不在对话里整篇回显；交付只给路径 + 摘要。
- 同一查询 5 分钟内复用缓存；互不依赖的只读命令并行执行；能一次批量完成的不要拆成多轮。
- 不重复用户已经知道的信息；不复述刚执行过的命令全文。
- 五项闸门任一先到（8 轮 / 150000 累计 token / 100000 单请求峰值 / 120 次请求 / 8000000 单会话 input）或上下文到 80% 时，先生成恢复包再换新对话；65% 预警；换对话只带恢复包，不回灌整段历史。
- 不为“省 token”删掉未决问题、下一步、关键数字和验证证据。

## 每轮实时钩子（Codex）

每轮用户提问结束时调用一次：

```sh
bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh \
  agent=codex active_project=<项目标识> thread_id=<对话框ID>
```

钩子只做一次 `state.py bump`：

- 按 `thread_id` 定位 rollout，自动读取轮数、当前上下文、累计花费和运行窗口；
- 不读取、不记录、不上传任何消息正文；
- 同一 thread 永远同一 state 键，项目名变化不会串号；旧的“项目名||线程”键会自动合并；
- 输出 `action`：
  - `continue`：继续；
  - `prepare_split`：准备恢复包，达到硬阈值就换；
  - `split_now`：立即生成恢复包并开新对话，本对话不再续接。

`state.py bump` 可手工传 `token_count=<当前上下文>` 覆盖自动读取，但正常不需要。

## 恢复包（达到阈值时的动作）

1. 先生成恢复包/记忆摘要（字段见 `references/templates.md`），登记：
   ```sh
   python3 $CODEX_HOME/skills/memory-orchestrator/scripts/recovery.py --add <项目名> <恢复包路径>
   ```
2. 用 `recovery_prompt.py` 生成新对话首条 user 消息：
   ```sh
   python3 $CODEX_HOME/skills/memory-orchestrator/scripts/recovery_prompt.py \
     --recovery-path <恢复包.md> --project <项目> --thread-id <对话框ID> [--json]
   ```
3. 在本 app 调 `create_thread` 开新对话并发送首条消息；本对话随后归档。
4. 当前任务正在收尾、无法立刻接力时：至少生成恢复包并在交付里明确写“本对话已到阈值，下轮请用恢复包开新对话”，不得静默续接。
5. 钩子本身不能后台开对话；“自动换新对话”由当前对话代理执行上述 1-3 步完成。

## cp-memory 工具调用清单（含 Checkpoint）

> 已外移，按需加载：`references/tooling.md`。recall/add/decision/task/restore 的参数与 tags 约定。

## 状态与文件

- 状态文件：`$CODEX_HOME/memory/state.json`（不可写时降级 `$TMPDIR/memory-orchestrator/state.json`，输出里 `storage.mode=fallback`）。
- 恢复包索引：`$CODEX_HOME/memory/recovery-index.md`。
- 最近任务兜底：`$CODEX_HOME/memory/hot.md`。
- 计数只含：项目名、thread_id、agent、轮数、context_tokens、context_peak、context_ratio、window_tokens、spent_tokens、提醒标记、时间戳。

## 定时兜底监测

> 已外移，按需加载：`references/tooling.md`。默认只监测 `inProgress`；查询成功但为空按空集处理，不退化。

## 压缩

- 用户说“总结/压缩/恢复/交接/开新对话”时，先执行本技能。
- 历史压缩用 CLI：`$CODEX_HOME/tools/agent-ctx-compress/bin/ctxcompress`，只能 shell 调用，不注册 MCP。
- 先 `state.py get` 确认 `active_project`，再 `export_ctx.py --project <项目> -i <该项目 rollout> -o <临时目录>/chat.json`；默认拒绝全目录通配，临时产物用完即删。
- 常用参数：`--stats-only` 看占比；`--ratio 0.3-0.5` 保守压缩；`--no-summarize` 只去重。
- 工具不可用时降级为 5-8 行手动摘要，并在交接包里写明降级原因；不得静默假装压缩。

## 归档（会话结束）

1. 汇总本次目标、决定、下一步 → cp-memory（`memory_add(entity=项目名, tags="archive")` 或 `memory_decision_add`）。
2. 更新 `$CODEX_HOME/memory/hot.md` 顶部：只保留最近 1 个项目的最新状态；切换项目前先把旧项目状态写入 cp-memory 防覆盖丢失。
3. 需要人类可读交接时同时生成恢复包并登记 `recovery-index.md`。
4. 结束前把 `turn_count`、`last_checkpoint` 写回 state.json。

## 记忆规则

- 只记结论与决策，不抄过程日志。
- 每条记忆带：主题、时间、状态（进行中/完成/归档）、下一步、责任人（默认用户）。
- 同主题增量更新（幂等），不重复追加相似条目。
- 多项目并存：cp-memory 按 `entity`+`tags` 隔离；`hot.md` 只做“最近一个任务”的最低保底。
- 公司数据只禁公开发布，不禁本人自用传输/备份/云端处理；本技能只做本地记忆，不上传网络。

## 项目步骤编排

把大项目拆成有序步骤，每步一个对话框：

```sh
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/step_orchestrator.py plan <plan.json> --project <项目>
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/step_orchestrator.py render --json
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/step_orchestrator.py complete --note <说明> --thread-id <对话框ID>
```

plan JSON：`{"project":"项目名","steps":[{"id":"s1","title":"标题","prompt":"开工提示词","verify":"验证方式"}]}`。中断后 `status`/`render` 从当前步继续；`complete` 幂等并写审计日志。

## 隐私与红线

- 只读会话元数据和 usage，不读正文、不建立全文索引、不联网上报。
- 公司数据只禁发布，不禁本人自用传输/备份/云端处理；发布前仍按全局脱敏规则执行。
- 删除原始资料、未授权修改系统级配置仍需先问。

## 自检

```sh
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/self_test.py
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/monitor_dialogs.py --days 2 --json
bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=codex active_project=test thread_id=test-id
```

## 禁忌

- 不得把 ctxcompress 注册成 MCP。
- 不得把累计计费 token 当上下文阈值。
- 不得把 config 的窗口值当 provider 真实上限。
- 不得只提醒“该换对话”却不生成恢复包。
- 不得在未切换项目时整份覆盖 `hot.md`。
- 不得读取或替代施工日志/会议纪要等既有项目技能的作用域。

## provider 切换后必查三处（2026-08-30 定）

1. `$CODEX_HOME/config.toml` 的 `model_context_window`；
2. 模型目录快照（`$CODEX_HOME` 下的 model catalog JSON）的 `context_window` 与 `effective_context_window_percent`；
3. `python3 $CODEX_HOME/scripts/protect-codex-config.py --check-only` 是否 `config ok`。

以模型目录算出的有效窗口为准；config 写大不会扩大 provider 真实上限。改完必须重启 Codex App（运行中的实例用启动时的快照）。

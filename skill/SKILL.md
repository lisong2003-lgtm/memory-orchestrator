---
name: memory-orchestrator
slug: codex-memory-orchestrator
displayName: 对话记忆管家 · Memory Orchestrator
description: 长对话记忆编排技能。负责会话开始时的记忆检索、自动监测每个对话框的对话轮数与 token 用量，轮数阈值或 token 阈值（默认 15 万）哪个先到先触发，达到阈值（8 轮或 15 万 token，先到者为准）自动生成恢复包并换新对话；默认只监测正在执行任务的对话框，停止/已完成/已归档对话不计数、不续接；即将达到阈值或上下文变模糊时提前提醒；负责恢复包生成、checkpoint、历史压缩（ctxcompress）、会话结束归档。触发词：“总结/压缩/恢复/交接/开新对话/checkpoint”。
version: 1.9.0
---

# memory-orchestrator

长对话记忆管理的中枢。目标是：上下文不失控、新对话 5 行内接续、关键决定不丢失。

## 安装后自动检测（任意 Agent 实时提醒）

- 安装本 Skill 后，在各 Agent 运行规则（本机 `AGENTS.md` / skill 说明 / 该 Agent 的每轮指令）中固化一句：**每轮用户提问结束时调用一次实时钩子，只统计轮数，不读取正文、不记录内容、不上传网络**。

### 本机已落地接线（Codex）
- 已固化：全局 `$CODEX_HOME/AGENTS.md`「长对话记忆管理」第 8 条 = 每轮调用 `agent_hook.sh`；新对话/重启后自动生效。
- Codex 实参示例：`bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=codex active_project=<项目标识> thread_id=<对话框ID>`。
- 兜底已接线（本轮实测回读 2026-10-20）：
  - heartbeat 自动化 `memoryorchestrator`：状态 ACTIVE，rrule `FREQ=HOURLY`，每小时跑 `python3 <skill>/scripts/monitor_dialogs.py --days 3 --write-state --json`（默认轮数阈值 8/7、token 阈值 150000/130000），默认只监测正在执行任务的对话框（thread_turns.status=inProgress），停止/已完成/已归档对话不计数、不提醒、不续接；仅当最近 3 天出现新的 ≥7/≥8 轮或 ≥13万/≥15万 token 对话框时才通知；
  - 启动兜底 LaunchAgent `com.lis.memory-orchestrator`：`RunAtLoad=true` + `StartInterval=3600`，ProgramArguments 为 `monitor_dialogs.py --all --write-state`（登录即全量首扫，同样只统计正在执行任务），日志写 `~/Library/Logs/memory-orchestrator.out.log` / `.err.log`。
- 实时钩子（纯本地、哑调用）：
  ```sh
  bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=<Agent名> active_project=<项目名> thread_id=<对话框ID>
  # 或 MEMORY_AGENT=<Agent名>。阈值可用环境变量覆盖：TURN_THRESHOLD / TURN_WARN_AT（默认 8 / 7）；
  # TOKEN_THRESHOLD / TOKEN_WARN_AT（默认 150000 / 130000）。
  ```
- 钩子做的事情 = 一次 `state.py bump`：只把“项目名 + 对话框标识 + 轮数 + 是否已提醒”写进 `state.json`，**绝不写入任何对话文本/摘要/正文**。
- state.json 是唯一本地计数文件；脚本没有 socket/requests/urllib/http 调用，不连网络、不上云、不推远端 git。发布版同样不包含任何上报逻辑。
- 每个对话框按 `active_project||thread_id` 独立计数、独立提醒，多 Agent/多对话框互不串号。
- 阈值与提前提醒（默认可覆盖）：
  - 轮数硬阈值默认 `>= 8`（SKILL/AGENTS/state 统一 8 轮，2026-10-19 确认）；提前 1 轮 `>= 7`；
  - token 硬阈值默认 `>= 150000`（2026-10-20 加，`TOKEN_THRESHOLD`），提前线 `>= 130000`（`TOKEN_WARN_AT`）；
  - 互补触发：轮数或 token 哪个先到就先触发（warning/over 只按先到者报，另一维度达到时再报）；
  - 提前提醒：达到提前线（7 轮或 13 万 token）时输出一次提醒（每对话框只出现一次，不刷屏）；
  - 到 `>= 8` 强制提醒：先生成恢复包，再引导开新对话；
  - **自动换新对话（互补，先到先触发，仅限正在执行任务）**：轮数 `>= 8` 或 token `>= 150000` 哪个先达到，本对话框即自动执行——先落本对话框恢复包/记忆摘要（checkpoint），再用 `create_thread`/`fork_thread` 开新对话（用 `recovery_prompt.py` 生成首条 user 消息）完成接力，本对话框随后归档收尾；不能 `create_thread` 时降级为 `handoff_gateway.py` 深层链接/复制剪贴板并提醒用户。停止/已完成/已归档对话框不做续接、不开新对话。
- 兜底（实时钩子遗漏时）：`monitor_dialogs.py` 定时扫描会话目录做真实轮数复核；两者互补。

### WorkBuddy 跨 Agent 接线（本机试点，2026-10-20）
- 试点对象：本机 WorkBuddy（`~/.workbuddy/workbuddy.db`，`mode=ro` 只读 `sessions`/`session_usage` 轮次与用量元数据，不读任何会话正文；实测当前含 3 个 session 的 token 用量，无独立轮数字段）。
- 共享计数：Codex/WorkBuddy 跨 Agent 状态统一写 `$CODEX_HOME/memory/state.json` 的 `dialogs`；WorkBuddy 侧使用 `@workbuddy` 命名空间（即 `agent=workbuddy`）登记，只写对话框标识/项目名/轮次/提醒标记，不写正文。
- 交叉核对：codex 侧 `state.py cross-check [agent=codex|workbuddy...] --json` 可列示其他 Agent 的超阈值/接近阈值对话框；临时模拟验证 workbuddy `turn_count=9 → over` 链路通过（真实 state 未伪造轮数）。
- 真实轮数边界：当前 db 无轮数列，真实轮数须由 WorkBuddy 发出端每轮调用 `agent_hook.sh agent=workbuddy active_project=<项目> thread_id=<会话ID>` 登记后才可得；未登记前不得伪造轮数数据。

## 会话状态（每次会话开始/结束）

- 状态文件：`$CODEX_HOME/memory/state.json`
- 更新命令：
  ```sh
  $CODEX_HOME/skills/memory-orchestrator/scripts/state.py set active_project=<项目名> [agent=<Agent名>]
  $CODEX_HOME/skills/memory-orchestrator/scripts/state.py bump active_project=<项目名> [thread_id=<对话框ID>] [agent=<Agent名>]  # 每轮+1，可带阈值参数
  $CODEX_HOME/skills/memory-orchestrator/scripts/state.py touch agent=<Agent名>                                   # 登记本 Agent 已装 Skill 的存活标记
  $CODEX_HOME/skills/memory-orchestrator/scripts/state.py cross-check [agent=<Agent名>] --json                   # 读共享注册表，交叉提醒其他 Agent
  $CODEX_HOME/skills/memory-orchestrator/scripts/state.py get
  bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=<Agent名> active_project=<项目名> thread_id=<对话框ID>  # 实时自检钩子
  ```
- 对话轮数监测（每个对话框自动执行）：以该对话框真实累计轮数为准，不只数本窗口；按 `active_project||thread_id` 在 `state.json` 的 `dialogs` 字典中隔离计数；
  - 硬阈值默认 `turn_count >= 8`（SKILL/AGENTS/state 统一 8 轮，2026-10-19 确认）；可用 `--threshold N / --warn-at N` 或环境变量覆盖；
  - token 硬阈值默认 `>= 150000`（`TOKEN_THRESHOLD`），提前线 `>= 130000`（`TOKEN_WARN_AT`）；`state.py bump` 可传 `token_count=<整数>` 一并判定；
  - 互补触发：轮数或 token 哪个先到先触发；`token_count >= 150000` 时即便轮数 <8 也按“强制开新对话”处理，message 会注明触达的是 token 阈值；
  - 提前 1 轮提醒：当 `turn_count >= 7` 或 `token_count >= 130000` 时输出一次提醒“请准备开新对话”（本提醒只出现一次，不重复刷屏）；
  - 到 `turn_count >= 8` 或 `token_count >= 150000`（先到者为准）时触发强制换新对话（仅限正在执行任务）：先生成恢复包/记忆摘要，再用 `create_thread` 开新对话，本对话框随后归档（互补触发，token 先到也照此执行）；停止/已完成/已归档对话框不续接、不开新对话；
  - 单轮内容极大（如图纸批次 >10 张、往返文件多）时，即使未到轮数也要按里程碑先落恢复包，不只看轮数；
  - 触发依据可与 state.json 的 `turn_count` / `dialogs` 核对，缺省按本规则执行。
- 每次 checkpoint 后把 `last_checkpoint` 和 `last_action` 写回 state.json。
- state.json / recovery-index.md 主路径不可写时自动降级到 `$TMPDIR/memory-orchestrator/`（可用 `CODEX_MEMORY_STATE_FALLBACK` / `RECOVERY_INDEX_FALLBACK` 覆盖），并在输出 JSON 的 `storage` 字段标明 `primary/fallback`。
- 并发安全：`state.py` 用文件锁 + 原子写（先写临时文件再 rename），多 Agent 并行 bump 不会互相覆盖。

## cp-memory 工具调用清单（真实签名，2026-10-18 实测）

- 会话开始检索：`memory_recall(query=项目名或主题, intent=resume, limit=5)`；也可 `memory_search(query=..., limit=5)` / `memory_probe(entity=<项目名>)`。
- 写 checkpoint/归档：`memory_add(entity=<项目名>, property=next_step|decision|checkpoint, value=一句话, tags="checkpoint|archive", content=长文本可选)`。
- 记决策：`memory_decision_add(title, context, decision, rationale)`。
- 记当前任务：`memory_task_set(task_name=...)`；完成：`memory_task_done(result=...)`。
- 恢复上下文：`memory_restore_context(prompt=最近问题, max_chars=...)`。
- 状态核对：`memory_health()` / `memory_stats()`。
- 多项目隔离：`entity` 一律用项目名；tags 带项目名，避免串记。
- 以上工具名均来自本机 `cp-memory-mcp`（v1.30.0）`tools/list` 实测结果。

## 跨对话框轮数监测（monitor_dialogs.py）

- 脚本：`scripts/monitor_dialogs.py`；纯 stdlib（Python 3.9+ / Windows 兼容），要求 Python 能 read 会话目录。
- **只监测正在执行任务的对话框**（2026-10-20 定）：默认仅统计 `thread_turns.status=inProgress`（App 本地 db `thread_history_1.sqlite`）；停止/已完成/已归档对话框不计数、不提醒、不续接、不开新对话。可用 `--no-active-only` 关闭过滤（不推荐）。
- 跨平台路径（自动探测，可用 CLI 覆盖）：
  - Codex Home：`$CODEX_HOME`/`$OPENAI_CODEX_HOME` 生效，否则 `$CODEX_HOME`（macOS/Linux）或 `%USERPROFILE%\.codex`（Windows，`Path.home()` 自动处理）。
  - 会话目录默认 `<Codex Home>/sessions`；可用 `--sessions-dir` 覆盖（如 Windows 安装到其他位置时显式传入）。
  - 项目/标题元数据默认 `<Codex Home>/sqlite/codex-dev.db`；可用 `--catalog-db` 覆盖。数据库不可用时降级为仅报告 rollout 文件名/目录。
- 数据来源（2026-10-18 在 macOS 实测，格式在桌面/CLI 会话中一致）：`rollout-*.jsonl` 中 `event_msg/item_completed` 且 `item.type == "UserMessage"`（按 turn_id 去重）。Windows/Linux CLI 如无该类型事件，则退化为统计文件内 `role=user` 的消息。
- 默认阈值：轮数 `>=8` 超限、提前 `>=7`；token `>=150000` 超限、提前 `>=130000`；可 `--threshold/--warn-at/--token-threshold/--token-warn-at` 覆盖；`--days` 只扫描最近 N 天。
- token 数据源：rollout 内 `token_usage_record.payload.(thread_)token_usage.total_tokens`（兜底 `event_msg.info.total_token_usage.total_tokens`），取该对话累计最大真实 usage；只读元数据不读正文。
- 运行 `--write-state` 会把扫描快照写入 state.json 的 `index`（兼容原有 active_project/turn_count）。
- 只读会话日志、不自动生成恢复包；发现超限**正在执行**对话框时应按“恢复包”章节为该对话框生成交接包并引导开新对话；停止/已归档对话框不续接、不生成续接对话框。
- 安装后如何自动开始（按平台，不需用户每次手动跑）：
  - macOS 桌面 Codex：在 Codex 里建 heartbeat/cron 自动化，运行 `python3 <skill>/scripts/monitor_dialogs.py --days 3 --write-state --json`，仅在状态变化时汇报（本机 2026-10-20 已接：heartbeat `memoryorchestrator` ACTIVE/每小时 + LaunchAgent `com.lis.memory-orchestrator` RunAtLoad/3600s 兜底）。
  - Windows：任务计划程序创建每日任务（`schtasks /create /tn "MemoryOrchestratorMonitor" /sc daily /st 09:30 /tr "python <skill路径>\scripts\monitor_dialogs.py --days 14 --write-state"`），系统用户登录即开始。
  - Linux/WSL：`crontab -e` 加 `30 9 * * * python3 <skill-path>/scripts/monitor_dialogs.py --days 30 --write-state`。
  - 无法注册系统定时任务的受限环境：把“打开新会话时运行一次 monitor_dialogs.py”写进该环境 AGENTS.md，作为降级触发。
- 存量全量检测（R1）：安装完成即运行一次
  ```sh
  python3 $CODEX_HOME/skills/memory-orchestrator/scripts/monitor_dialogs.py --all --write-state
  # --all 关闭时间过滤全量扫历史，与 --days 互斥；结果写 state.json.index：last_full_scan / scanned_files / 每会话 over_warned
  # 同一对话框提醒后写入 over_warned_ids，二次扫描不重复刷屏
  ```
- 本脚本不替代“当前对话框是否接近阈值”的会话内提醒；两者互补。

## 多 Agent 交叉提醒与一键新对话承接（R2）

- 共享注册表：所有已装本 Skill 的 Agent 读写同一个 `state.json`，`dialogs` 每条带 `agent`/`owner` 字段；
  进程只读他人的行、只写自己 `owner` 的行；非 codex Agent 的对话框键加 `@<agent>` 命名空间防碰撞。
- `state.py bump` 触发提醒时自动读注册表做交叉检查：列出其他 Agent 已超阈值/接近阈值的对话框，
  以及注册表中无存活标记（`agent_alive != true`）的 Agent 并提示“建议在其也安装本 Skill”。
- `state.py touch agent=<Agent名>` 登记本 Agent 的存活标记；`cross-check` 可单独触发交叉提醒。
- 一键承接：`scripts/handoff_gateway.py` 按 `references/agent-gateways.md` 能力矩阵降级——
  Codex = full_auto（本 app 内 create_thread/fork_thread 注入续接文本 + `codex://threads/<id>`）；
  Claude = deep_link（`claude://new?text=` + 剪贴板）；无注入能力 Agent = 生成恢复包 + 复制剪贴板 + 打开目标应用。
  真实跳转写 `$CODEX_HOME/audit.log`。全程本地，不把会话内容发云端。


## Checkpoint（每 8 轮、里程碑或提前 1 轮提醒后）

1. 导出可压缩源（仅当前项目/会话，禁止默认扫全部日志）：先用 `state.py get` 确认 active_project，再用 `scripts/export_ctx.py` 指定该项目 rollout 文件转成 messages 数组；压缩前向用户说明将读取的范围与用途。

   ```sh
   export ACT="<项目标识>"                              # 必须先经 state.py get 与用户确认
   export OUT="${TMPDIR:-/tmp}/memorch-$$/chat.json"   # 私有临时目录
   mkdir -p "$(dirname "$OUT")"
   python3 $CODEX_HOME/skills/memory-orchestrator/scripts/export_ctx.py --project "$ACT" -i "$HOME/.codex/sessions/**/rollout-*.jsonl" -o "$OUT"
   ctxcompress --input "$OUT" --stats-only
   ```
   仅当前 active_project；export_ctx.py 默认拒绝全目录通配，必须显式 `--project`；兼容真实 rollout 的 `payload` 包裹结构，只导出 user/assistant 交换轮（跳过 developer 指令）；`--project` 会按文件名/父目录/session_meta.payload.cwd 匹配真实项目。临时文件用完即删，原始对话不落入长期记忆。

2. 无法获得对话转储时，按规则手写压缩摘要（5-8 行，见 `references/templates.md`）。
3. 把 checkpoint 通过 `memory_add(...tags="checkpoint")` 写入 cp-memory，并同步更新 hot.md 与 state.json。

## 压缩（ctxcompress）

- ctxcompress 是 **CLI**，只能经 shell 调用，绝不注册为 MCP 工具。
- 命令形态：

  ```sh
  export ACT="<项目标识>"                                                        # 与 state.py 的 active_project 一致，先征得用户同意
  python3 $CODEX_HOME/skills/memory-orchestrator/scripts/export_ctx.py --project "$ACT" -i "<当前项目 rollout 路径/glob>" -o "$OUT"
  ctxcompress --input "$OUT" --ratio 0.3 --format compact --output "$(dirname "$OUT")/compact.txt"
  ```

- 常用参数：`--stats-only` 看占比；`--ratio 0.3-0.5` 保守压缩；`--no-summarize` 只去重。
- 工具不可用或异常时，降级为 5-8 行手动摘要（同样限定 active_project），降级原因写进交接包，不静默假装压缩。
- 临时压缩产物用完即删（`rm -f "$OUT" "$(dirname "$OUT")/compact.txt"`），原始对话不写入长期记忆。

## 恢复包

- 命名固定：`恢复包-<项目名>-<YYYYMMDD>.md`。
- 生成后登记索引：
  ```sh
  python3 $CODEX_HOME/skills/memory-orchestrator/scripts/recovery.py --add <项目名> <恢复包路径>
  ```
- 索引文件：`$CODEX_HOME/memory/recovery-index.md`，新对话先读它定位最近恢复包。
- 生成 `create_thread` 提示词：`python3 $CODEX_HOME/skills/memory-orchestrator/scripts/recovery_prompt.py --recovery-path <恢复包.md> --project <项目> --thread-id <对话框ID> [--json]`，输出可直接作为本 app `create_thread`/`fork_thread` 的首条 user 消息。
- 模板见 `references/templates.md`；字段：会话信息、目标与已完成、关键决策与依据、下一步、未决/风险、交接对象与验证方式。

## 归档（会话结束或“总结/交接”）

1. 汇总本次目标、决定、下一步 → cp-memory（`memory_add(entity=项目名, tags="archive")` 或 `memory_decision_add`）。
2. 更新 `$CODEX_HOME/memory/hot.md` 顶部（只保留最近 1 个项目的最新状态；切换项目前先把旧项目状态写入 cp-memory 防覆盖丢失）。
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
- 不得在 cp-memory 不可用时停摆：至少落到 `$CODEX_HOME/memory/hot.md`。
- 不得默认导出全目录 rollout；必须限定 active_project 并先经用户确认。
- 不得用“换新对话”替代真实交接：必须先生成恢复包/记忆摘要再提醒开新对话。
- 不得在压缩时丢弃未决问题、下一步、关键数字。
- 不得在未切换项目时整份覆盖 hot.md（先归档旧项目）。
- 不读取或替代施工日志/会议纪要等既有项目技能的作用域。

## 项目步骤自动编排（新增能力，2026-10-20）

把一个大项目拆成有序步骤，由对话记忆管家为每步生成开工提示词；每完成一步自动开新对话框进入下一步，直到完成。

- 脚本：`scripts/step_orchestrator.py`（纯 stdlib，不上网）。plan 文件默认目录 `$CODEX_HOME/memory/plans/`（Windows 用 `%USERPROFILE%\.codex\memory\plans\`），可用 `CODEX_MEMORY_STATE_FALLBACK` 覆盖。
- plan JSON 规范：
  ```json
  {"project": "项目名", "steps": [
    {"id":"s1","title":"步骤标题","prompt":"该步开工提示词","verify":"完成验证方式"}
  ]}
  ```
- 命令：
  - `step_orchestrator.py plan <plan.json> --project 项目` 初始化计划（幂等，重复 init 提示已存在不覆盖已完成步骤）；
  - `render` 输出当前步开工提示词（`--json` 可输出结构化提示词，便于交给 `create_thread`）；`complete --note ... [--thread-id <对话框ID>]` 标记完成并推进；`status` 查看进度；`complete` 自动写 `$CODEX_HOME/audit.log`（附 thread-id 则一并记录接力证据）。
- 断点恢复：中途中断后重跑 `status`/`render` 即从 `current` 处继续；重复 `complete` 已完成步骤不会重复推进（幂等）。
- 开新对话框接力：`complete` 后读取下一次 `render` 的输出，在本 app 用 `create_thread` 把它作为首条 user 消息开新对话框，直到 `current` 到尾。
- 默认免逐步确认（用户预授权全部步骤的本地操作）：调用“对话记忆管家做步骤编排”即进入 auto，新对话框按开工提示词**直接执行、不逐次弹授权**；`complete` 后自动渲染下一步提示词直接接力。
- 权限两档：
  - 默认（不设环境变量）：免逐步确认，新对话框直接执行、不逐次确认；
  - `AUTO=0` / `APPROVAL_MODE=manual`：关闭免确认，回到每完成一步前向用户确认。
- 红线永不豁免（即使 auto）：公司数据上云/Git 远端、删除原始资料、未授权系统配置改动，一律先询；其他脚本只记录轮次/进度/审计，不读对话正文、不上网、不上云。

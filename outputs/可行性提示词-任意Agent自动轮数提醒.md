# 可行性提示词：把 codex-memory-orchestrator 改为「安装后任意 Agent 自动按轮数提醒」

> 用途：把这个提示词交给负责改造的 Agent，先做可行性说明，再进入实施。
> 遵循用户规则：先说明（功能/边界/风险/验证计划/回归清单）→ 确认后再改代码；最终交付必须带验证证据。

## 一、任务目标（按用户原话转成验收标准）

1. 用户安装本 Skill 后，使用任意 Agent 的对话框中，能**自动检测该对话框的对话轮数**。
2. **只检测轮数，不记录内容**：不把任何对话文本写入 state、hot.md、记忆或交接包。
3. 检测与提醒**只留在本机**，任何情况不上传网络（不发云端、不发远端 git、不调第三方 API）。
4. 按用户设置阈值提醒，且**提前 1 轮**提醒（例如硬阈值 8，则在第 7 轮提醒一次；第 8 轮强制提醒）。
5. 提醒方式：输出一句话告知「再 1 轮将达到阈值，请准备开新对话」，且同一对话框同一阈值只提醒一次，不刷屏。
6. 多 Agent/多对话框并行：各自的轮数独立计数、独立提醒，不串号。

## 二、现状核查（已读本机 SKILL.md / monitor_dialogs.py / self_test.py）

- 现有 `scripts/monitor_dialogs.py`：扫描 `<CodexHome>/sessions/rollout-*.jsonl`，按 `item_completed.UserMessage` + `turn_id` 去重统计轮数；`--threshold 8` / `--warn-at 7`；`--write-state` 写 `.codex/memory/state.json`。
- 现有 SKILL.md 已写：硬阈值 `>=8` 强制、`>=7` 提前提醒、每轮 `state.py bump`、桌面 heartbeat / Windows 计划任务 / Linux cron 的自启动方案。
- 自启动目前是**定时扫描**（每天一次），不是"Agent 使用中实时自动执行"。
- 数据来源只在本机 rollout 文件，SQLite 仅用于关联项目名；无网络调用。

## 三、可行性结论（分三档）

| 方案 | 做法 | 可行性 | 说明 |
|---|---|---|---|
| A. 现有定时扫描 | 保留 monitor_dialogs.py + heartbeat/cron | ✅ 已实现 | 只覆盖本机 Codex 桌面/CLI 可读会话目录；其他 Agent 读不到 |
| B. Agent 自检钩子 | 安装 Skill 时在 `AGENTS.md`/skill 说明写入规则：每轮结束时由 Agent 自己调用 `state.py bump`，脚本只写轮数，不读正文 | ✅ 可做（推荐核心） | 「使用任意 Agent 时自动检测」的真正增量；依赖该 Agent 遵守 skill/AGENTS.md 指令（Codex 类 agent 可用）；不读会话文件正文，隐私最干净 |
| C. 混合 | A 做兜底补漏 + B 做实时提醒 | ✅ 推荐交付形态 | 单次改造同时满足"实时自动"与"飞轮漏算兜底" |

**结论：可行，且 B+C 组合能最大化满足需求。** 不足以自动覆盖的边界见下节。

## 四、能力边界（必须写进提示词，向用户明示）

1. "任意 Agent" 有硬边界：只能对**能读到 skill/AGENTS.md 指令并执行脚本调用**的 Agent（本机 Codex 桌面/CLI、按规则接入的 Agent）实时自检；不支持或不读本机指令的第三方 Agent 无法保证，只能靠方案 A 扫它的会话目录（若目录可读）或明确标注"不支持"。
2. 下列场景无法保证实时提醒：会话日志被 Agent 加密/存云端、远程 host 会话不在本机、人工不遵守 skill 规则。此时降级为方案 A 的每日扫描提醒。
3. 只记轮数的前提下，`state.json` 允许记录：项目名、轮数、提醒状态（已提醒/未提醒）、last_checkpoint 时间。**禁止记录**任何消息文本、摘要、正文片段。
4. 网络红线：改造后的脚本不得出现 `socket`/`requests`/`urllib`/`http`/网络 API 调用；发布说明中明确"永不联网"。

## 五、风险

- R1（行为风险）：Agent 忘记每轮调用 `bump` ⇨ 用 AGENTS.md 写死步骤 + 方案 A 兜底扫描。
- R2（隐私风险）：脚本若误把正文写进 state ⇨ 单元测试断言 state 不含项目名以外的字符串、不含对话内容。
- R3（多线程竞态）：多 Agent 并行 bump 同一 state.json ⇨ 每次 bump 加文件锁 + 原子写（先写临时文件再 rename）。
- R4（提醒刷屏）：提前提醒重复出现 ⇨ state 记录 `warned_*` 标记，只提醒一次。
- R5（升级破坏兼容）：新 `state.py` 参数变化 ⇨ 保持旧 CLI 参数（`set/bump/get`）不变，只加 `--threshold/--warn-at/--no-network` 等新参数。

## 六、验证计划（改完必须跑）

1. `self_test.py`：全部通过；新增对 `bump` 幂等、提前一轮提醒只触发一次、state 不落正文的断言。
2. 造 8 轮假 rollout 跑 `monitor_dialogs.py --write-state`：第 7 轮输出一条提醒、第 8 轮输出强制提醒、第 9 次运行不再重复第 7 轮提醒。
3. 网络证明：`grep -nE "socket|requests|urllib|http|aiohttp|httpx" scripts/*.py` 输出为空；有需要时用 `lsof -i` 观察运行脚本无出站连接。
4. 多对话框隔离：两个不同线程分别 bump，确认 state 各自计数不互相覆盖。
5. 回归清单：现有 `state.py`/`monitor_dialogs.py`/`recovery.py`/`export_ctx.py` 原功能不变；SKILL.md 双平台路径说明仍一致。

## 七、实施范围建议（供确认，不在此步骤执行）

- 小改：`state.py` 增加阈值参数与"只提醒一次"标记；新增原子写 + 文件锁。
- 中改：新增 `scripts/agent_hook.sh`（一行式 bump，供任意 Agent 每轮调用）；SKILL.md 增加"安装后自动开启"与"每轮调用指令"章节。
- 增加 AGENTS.md / skill 安装指南：说明如何让各 Agent 自动在每轮结束时调用该钩子，并写明不读正文、不联网。
- 保留 monitor_dialogs.py 作为兜底扫描，不动其核心统计逻辑（只可能与新 state 格式兼容）。

## 八、不做什么（防范围蔓延）

- 不做云端同步、不做内容摘要、不记录对话正文、不接入任何网络 API。
- 不承诺覆盖不支持本地指令的第三方 Agent（只在 SKILL.md 写明边界）。
- 不重写现有 monitor_dialogs.py 的统计口径（避免回归）。

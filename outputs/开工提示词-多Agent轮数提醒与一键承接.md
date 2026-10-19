# 开工提示词（完善版）：任意 Agent 自动轮数提醒 · 安装后存量全量检测 · 多 Agent 交叉提醒与一键新对话承接

> 用途：交给负责改造 codex-memory-orchestrator 的 Agent，作为“先说明”阶段的完整可执行提示词。
> 范围 = 三阶段需求合并：
> ① 本 Agent 实时自检（只计轮数，只留本地，不上传，提前 1 轮提醒）；
> ② 安装后对“安装前已存在的老对话框”自动全量检测一次并提醒；
> ③ 用户同时开多个 Agent 时，一旦任一 Agent 超阈值，其他已装 Skill 的 Agent 也要交叉提醒，并自动提示“请在对应 Agent 也安装本 Skill”；用户点“确定”后，自动在该 Agent 新开对话框承接之前的对话。

---

## 一、需求汇总（可验收，分 R0 / R1 / R2）

### R0 本 Agent 实时自检
1. 每轮用户提问结束时自动检测当前对话框轮数，只统计轮数、不记录内容。
2. 只写本机 `state.json`，不读取正文、不上传网络、不进远端 git。
3. 默认硬阈值 `>=8`，提前 1 轮（`>=7`）提醒；阈值可用 `--threshold/--warn-at` 或环境变量 `TURN_THRESHOLD/TURN_WARN_AT` 覆盖；同一对话框同一阈值只提醒一次。
4. 多对话框并行时按 `agent || active_project || thread_id` 独立计数、独立提醒，不串号。

### R1 安装后存量全量检测
5. 安装完成即自动对**安装前已存在对话框**（本机可读会话目录）做一次全量检测。
6. 输出分组提醒：🔴 已超阈值（先生成恢复包再开新对话）、⚠️ 接近阈值（再 1 轮将到阈值，准备开新对话）；✅ 无命中时也给出完成确认。
7. 全量结果写 `state.json` 的 `index`（含 `last_full_scan`、`scanned_files`、每会话 `over_warned` 标记），二次扫描不重复刷屏。
8. `monitor_dialogs.py` 新增 `--all`（关闭时间过滤，全量扫历史），与 `--days` 互斥。

### R2 多 Agent 交叉提醒 + 一键新对话承接
9. 所有已装本 Skill 的 Agent 共用同一个本机注册表（`state.json` 的 `dialogs`），每条带 `agent` 字段（默认 `codex`）。
10. 任一 Agent 在提醒时，同时读注册表：
    - 列出**其他 Agent** 中已超阈值/接近阈值的对话框并自动提醒；
    - 对注册表中未写入“本 Agent 已装 Skill 的存活标记”的 Agent，提示“建议在《Agent 名》也安装本 Skill，才能在这边实时提醒”。
11. 用户在提醒上点“确定/确认”后，系统**自动在该 Agent 新开一个对话框并承接之前的对话**：
    - 优先用该 Agent 的“新对话 + 续接上下文”能力（深链/CLI/API）承接；
    - 无续接注入能力的 Agent 降级为：生成恢复包 + 复制续接包到剪贴板 + 打开该应用的新对话窗口，用户粘贴即可。
12. 一切仍只在本机完成：不把任何会话内容发到云端。

---

## 二、现状核查（已读本机代码）

| 能力 | 现有实现 | 状态 |
|---|---|---|
| 本 Agent 轮数实时自检 | `scripts/state.py`（按 active_project‖thread_id 隔离、阈值/提前提醒、文件锁+原子写）+ `scripts/agent_hook.sh` | ✅ 已实现（上一版落地） |
| 超阈值/接近阈值分组 | `scripts/monitor_dialogs.py` 已有 over/warn 输出 | ✅ 已实现 |
| 安装后存量全量检测 | monitor 只有 `--days N`；`--days 0` 扫不到任何文件；**无 `--all`、无安装首跑入口** | ❌ 缺 |
| 会话→对话框标题/项目映射 | SQLite catalog + 文件名降级 | ✅ 局部 |
| 多 Agent 注册表 + agent 字段 | state.json 目前只按 active_project‖thread_id 计数，**无 agent 字段**、无交叉读取入口 | ❌ 缺 |
| 一键新开对话框并承接 | 无通用实现；Codex 可用本 app 线程工具/深链，第三方 Agent 需逐 app 适配 | ❌ 缺 |

---

## 三、可行性结论（分级，先说明）

- **R0**：✅ 可行且已基本实现，只做接口补齐。
- **R1**：✅ 可行。新增 `--all` + 安装首跑 + 去重标记即可；受限于“本机可读会话目录”。
- **R2**：🟡 部分可行，必须按 Agent 分级：
  - ✅ **能交叉提醒**：只要其他 Agent 也装本 Skill（写同一 `state.json` 注册表）或本地能读到其会话元数据。本 Skill 负责把注册表做成“多 Agent 共享钱包”，谁都能读、只写自己的行。
  - 🟡 **建议安装提示**：注册表里没有“此 Agent 已装 Skill”存活标记的 Agent，提醒文本中列出并建议安装（纯文本提醒，可做）。
  - 🟡 **点确定→自动新开对话框承接**：对 Codex 本机可做（新建同项目线程并把恢复包/续接提示注入首条消息）。对多数第三方 Agent **没有公开“新对话+注入续接文本”的 API**，只能做成能力矩阵：支持深链 → 打开新窗口并把恢复包复制到剪贴板；完全不支持 → 生成恢复包并打开该应用目录/新窗口，提示用户手动粘贴承接。不能承诺“所有 Agent 都一键无缝承接”。

---

## 四、设计建议（供确认后实施，不在本提示词阶段改码）

### 4.1 注册表与 agent 字段
- `state.json` 每条 dialog 增加：
  ```json
  {
    "agent": "codex",
    "agent_alive": 1,
    "thread_id": "<id>",
    "active_project": "<项目>",
    "turn_count": 8,
    "warned": true, "forced": true,
    "checked_at": "..."
  }
  ```
- `agent_hook.sh` 新增 `agent=<name>`（默认取环境变量 `AGENT_NAME`，无则 `codex`），写注册表时带上 agent。
- `state.py` 新增只读命令 `list` / `cross-check --threshold 8 --warn-at 7`：读全注册表，按 agent 分组返回 over/warn；每个 Agent 只“写自己的行、读全部行”，从不越权改别人行。

### 4.2 安装时全量检测
```sh
python3 <skill>/scripts/monitor_dialogs.py --all --write-state --json
```
把输出转成用户可读中文提醒；在 `index.last_full_scan` 落时间戳与文件数；命中对话写 `over_warned` 防重复。安装入口写入 SKILL.md / README / 各平台发布说明；桌面环境用一次性 heartbeat（只跑一次），Windows 用一次 schtasks，Linux 用一次 at 或首跑说明。

### 4.3 一键新开对话框承接（按 Agent 能力矩阵）
- Codex：调用本 app `create_thread` 或 `fork_thread`（同目录），把恢复包/续接要点作为新线程首条 user 消息，然后深链 `codex://threads/<id>` 打开；提醒按钮“确定”即触发。
- 其他 Agent（Claude/ChatGPT 网页/其他本地 Agent）：
  - 若提供 “new chat” 深链且能带初始文本 → `open "schema://new?text=<encoded 恢复包>"`；
  - 若只有新窗口深链（不能注入文本）→ 打开新窗口 + 自动复制恢复包到剪贴板；
  - 若任何都不可用 → 生成 `恢复包-<项目>-<日期>.md`，登记进 `recovery-index.md`，并 `open <该应用>`，提示用户手动粘贴。
- 每种适配都要写进 `references/agent-gateways.md`（能力矩阵表：agent 名、新对话入口、是否支持注入初始文本、凭证要求、验证方式）。

### 4.4 私密与安全
- 全程本地：不调用任何网络库；恢复包只在本机生成；“打开新对话”只做本机应用跳转，**不涉及任何云端上报**。
- 跳转第三方 Agent 等于在本机启动该应用并注入文本，属“本机自动化”，不违反公司数据红线（公司内容若装入云版第三方 Agent，仍需先经用户确认是否外发）。

---

## 五、能力边界（必须向用户明示，写入交付文档）

1. “自动检测任意 Agent”只对两类的组合有效：A. 已装本 Skill 并写共享注册表的 Agent；B. 本地可读其会话元数据的 Agent。读不到的 Agent 无法检测。
2. “一键新开对话框承接”按能力矩阵分级：Codex 全自动；带深链 Agent 半自动（剪贴板承接）；无能力 Agent 只能生成恢复包 + 人工粘贴。
3. 安装前的老对话框，只有本机存了会话文件才能全量检测；已删除/加密/远端 host 的读不到。
4. 交叉提醒只提醒、不代开对话；只有用户点“确定”后才执行本机跳转开新对话。

---

## 六、风险

- R2-1（其他 Agent 无 API）→ 走能力矩阵降级，如实提示“该 Agent 需手动粘贴承接”。
- R2-2（跨 Agent 误开窗口）→ 开新对话前必须确认目标 Agent 与目标对话框标题，写 `~/.codex/audit.log`（时间、目标 agent、目标 thread、结果）。
- R2-3（重复提醒刷屏）→ 注册表 `warned/forced/over_warned` 标记 + `last_full_scan` 时间戳去重。
- R2-4（他人 agent 行被误改）→ 每条记录 `owner=agent`, 任何进程只 `list`/`get` 全量、只写自己的 `owner`，写操作前校验 owner 匹配。
- R1-1（全量扫描慢）→ 首次 `--all` 允许交互或 `--json` 分段；超 3 分钟提示，不阻塞说明。
- R0-1（agent 忘记每轮调用钩子）→ SKILL.md/AGENTS.md 写死步骤 + R1 定时兜底扫描。

---

## 七、验证计划（改完必须跑）

1. 单 Agent：造 8 轮/7 轮/3 轮假 rollout → R1 全量检测 over=1、warn=1；`--all --days 1` 报参数冲突；跑两次不重复提醒。
2. 多 Agent 假注册表（agent=codex/claude/local，各 2-3 条）→ `state.py cross-check` 输出按 agent 分组的 over/warn，且 target 列表含“未装 Skill 的 agent=claude（无 agent_alive）”。
3. 一键承接降级验证：模拟无深链 Agent → 生成恢复包＋登记 index＋打开目标 app（用 `open -a` 只做 dry-run 或记录命令不真实跳转）→ 断言返回恢复包路径与复制内容为恢复包全文。
4. 权限与审计：跨 Agent 跳转前有确认弹层，动作写 `~/.codex/audit.log`。
5. 隐私/联网：grep 核心脚本无 `socket|requests|urllib|http`；用 `lsof -i` 抽查本次进程无出站连接；state.cpp/恢复包均无对话正文。
6. 回归：现有 15 项 self_test 全绿（state/hook/monitor/export/recovery/export_ctx 不回归）。

---

## 八、实施步骤顺序建议（供后续拆分）

1. 先补 R1：`monitor_dialogs.py --all` + 安装首跑 + `over_warned` 去重 + self_test。
2. 再补 R2 注册表：state.py 增加 `agent/owner/agent_alive` 与 `cross-check`，agent_hook 带 `agent=`.
3. 最后补 R2 一键承接：先 Codex（create_thread/fork_thread+注入恢复包+深链），再 `references/agent-gateways.md` 能力矩阵，逐个 Agent 适配。
4. 每步独立提交、独立验证；发布更新三平台前再过 skill-publisher 合规脱敏。

## 九、不做什么（防范围蔓延）

- 不做云端同步、不记录对话正文、不接入网络 API。
- 不承诺“所有第三方 Agent 都能一键无缝承接新对话”；只按能力矩阵给最合理的降级。
- 不把别人的注册表条目删改（只读他人、只写自己）。
- 不自动关闭旧对话；超阈值后仍先生成恢复包，再引导开新对话。

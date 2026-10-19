## 1.4.0（2026-10-19）

- R1 存量全量检测：`monitor_dialogs.py` 新增 `--all`（与 `--days` 互斥），全量扫历史；`--write-state` 写入 `index.last_full_scan / scanned_files / over_warned_ids / 每会话 over_warned`，同一对话框提醒后二次扫描不再重复刷屏。
- R2 多 Agent 共享注册表：`state.py` 每条 dialog 记录增加 `agent/owner`，非 codex Agent 用 `@<agent>` 键命名空间；新增 `touch`（登记存活标记）与 `cross-check`（读共享注册表，列出其他 Agent 超阈值/接近阈值对话框并建议在无存活标记的 Agent 安装本 Skill）；`bump` 触发提醒时自动带交叉检查。
- R2 一键承接：新增 `scripts/handoff_gateway.py`（按 `references/agent-gateways.md` 能力矩阵：Codex=full_auto、Claude=deep_link、其他=生成恢复包+剪贴板+打开目标应用；真实跨 Agent 跳转写 `$CODEX_HOME/audit.log`；全程本地不联网）。
- `agent_hook.sh` 支持 `MEMORY_AGENT`/`agent=` 传 Agent 名。
- `self_test.py` 新增 R1/R2/handoff 自检；SKILL.md/README/CHANGELOG 同步说明。

## 1.3.0（2026-10-19）

- 新增 `agent_hook.sh`：任意 Agent 每轮实时自检钩子，只 bump 轮数，不读取/不记录正文。
- `state.py` 按 `active_project||thread_id` 隔离多对话框计数；支持 `--threshold/--warn-at` 与环境变量；提前 1 轮提醒且每对话框只提醒一次；文件锁 + 原子写防并发覆盖。
- SKILL.md 增加「安装后自动检测」章节与隐私/联网红线说明；README 同步。

# Changelog

## v1.2.0 (2026-10-18)

- 跨平台化：monitor_dialogs.py 自动探测 Codex Home（$CODEX_HOME / $CODEX_HOME / %USERPROFILE%\.codex），新增 `--sessions-dir`/`--catalog-db`；SKILL 记录 macOS 自动化、Windows 任务计划程序、Linux crontab 三种“安装后自动开始”方式。

- 新增 `scripts/monitor_dialogs.py`：跨对话框自动监测，按 rollout 中 `UserMessage` 真实计数，映射 `local_thread_catalog` 的项目与标题；`--write-state` 写入 state.json.index。
- 修复 `self_test.py` 在 Python 3.9（无 tomllib）崩溃：增加 TOML 降级解析；新增 monitor_dialogs 自检（13 项）。
- 修复 `_mcp_lines` 文本模式缓冲导致 cp-memory 自检挂起：改为二进制无缓冲。
- SKILL.md 增加“跨对话框轮数监测”章节，README 更新结构性说明。

## v1.1.4 (2026-10-18)

- 对话轮数监测改为自动执行：按真实累计轮数，默认硬阈值 8 轮；提前 1 轮（>=7）提醒一次；>=8 强制生成恢复包并引导开新对话；单轮内容极大（如图纸批次>10 张或往返文件多）时按里程碑先落恢复包。
- README / references/templates 阈值同步到 8/7 轮；平台与 GitHub 版本统一到 1.1.4。

## v1.1.3 (2026-10-18)
- SKillHub 平台展示：中文名「对话记忆管家 / Memory Orchestrator」+ 第一版蓝图风系列图标（平台专用，不回写本机）。
- 本机原版与平台版本号统一到 1.1.3；功能保持一致。

## v1.1.2 (2026-10-18)

- export_ctx.py 增加 `--project` 校验，默认拒绝 `**/*.jsonl` 全目录通配；示例改为项目限定 + 私有临时目录 + 用后清理。

## v1.1.1 (2026-10-18)

- 限制 checkpoint/压缩默认范围到当前 active_project，仅导出当前项目 rollout；压缩前需用户确认读取范围。
- 明确不持久化对话原文，/tmp 临时产物用完即删，避免跨项目隐私风险。

## v1.1.0 (2026-10-18)

- 新增自检 `scripts/self_test.py`，12 项全覆盖：结构、模板、降级线、AGENTS 注入、config 数值、protect 对齐、ctxcompress 真实运行、cp-memory 初始化与写读清闭环、export_ctx、state、recovery index。
- README / CHANGELOG / LICENSE 补齐。

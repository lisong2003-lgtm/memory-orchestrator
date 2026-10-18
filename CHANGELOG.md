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

# Changelog

## v1.1.2 (2026-10-18)

- export_ctx.py 增加 --project 校验，默认拒绝 `**/*.jsonl` 全目录通配；示例改为项目限定+私有临时目录+用后清理。

## v1.1.1 (2026-10-18)

- 限制 checkpoint/压缩默认范围到当前 active_project，仅导出当前项目 rollout；压缩前需用户确认读取范围。
- 明确不持久化对话原文，/tmp 临时产物用完即删，避免跨项目隐私风险（ClawHub 安全审查意见）。

## v1.1.0 (2026-10-18)

- 新增自检 `scripts/self_test.py`，12 项全覆盖：结构、模板、降级线、AGENTS 注入、config 数值、protect 对齐、ctxcompress 真实运行、cp-memory 初始化与写读清闭环、export_ctx、state、recovery index。
- 路径改为 `${CODEX_HOME:-$HOME/.codex}` 通用形式，不再写死私有主目录路径。
- 新增 assets 蓝图图标（skill-banner.svg / skill-icon.svg）。
- README / CHANGELOG / LICENSE 补齐。

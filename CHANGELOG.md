# Changelog

## v1.1.0 (2026-10-18)

- 新增自检 `scripts/self_test.py`，12 项全覆盖：结构、模板、降级线、AGENTS 注入、config 数值、protect 对齐、ctxcompress 真实运行、cp-memory 初始化与写读清闭环、export_ctx、state、recovery index。
- 路径改为 `${CODEX_HOME:-$HOME/.codex}` 通用形式，不再写死私有主目录路径。
- 新增 assets 蓝图图标（skill-banner.svg / skill-icon.svg）。
- README / CHANGELOG / LICENSE 补齐。

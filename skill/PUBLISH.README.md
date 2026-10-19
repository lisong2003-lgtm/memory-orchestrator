# 发布状态（2026-10-19，v1.6.0）

- 版本：v1.6.0（本机技能原版 canonical）
- 合规预检：check_release.py --path releases/memory-orchestrator-v1.6.0-full.zip / -skillhub.zip → problems=0；self_test 22/22 PASS。
- 发布包：releases/memory-orchestrator-v1.6.0-full.zip、releases/memory-orchestrator-v1.6.0-skillhub.zip、releases/SHA256SUMS.txt。
- 内容变更：实时钩子接线固化进 Codex 全局 AGENTS 第 8 条；新增 heartbeat 兜底自动化 memoryorchestrator；SKILL/README/CHANGELOG 同步；本机实测阈值 7/8 提醒、state 隔离、monitor 检测、export+ctxcompress、recovery 全链路通过。

## 三平台状态（回查中）
- GitHub：等待同步 + Release v1.6.0。
- SkillHub：slug=codex-memory-orchestrator，v1.6.0 versionId=446089，reviewStatus=pending。
- ClawHub：slug=codex-memory-orchestrator，v1.6.0 已提交，等待 moderation。

# 发布状态（2026-10-19，v1.6.0 三平台发布完成）

- 版本：v1.6.0（本机技能原版 canonical）
- 合规预检：check_release.py（full + skillhub 包）problems=0；self_test 22/22 PASS。
- 发布包：releases/memory-orchestrator-v1.6.0-full.zip、releases/memory-orchestrator-v1.6.0-skillhub.zip、releases/SHA256SUMS.txt。
- 内容变更：实时钩子接线固化进 Codex 全局 AGENTS 第 8 条；新增 heartbeat 兜底自动化 memoryorchestrator；SKILL/README/CHANGELOG 同步；本机实测阈值 7/8 提醒、state 隔离、monitor 检测、export+ctxcompress、recovery 全链路通过。

## 三平台状态（已回查）
- GitHub：main=3e0cd90，Release v1.6.0 已创建，3 个资产（full/skillhub/SHA256SUMS）已上传且非 draft。
- SkillHub：slug=codex-memory-orchestrator，v1.6.0 versionId=446089，reviewStatus=approved、keen=benign、sanbu=benign、isLatest=true。
- ClawHub：slug=codex-memory-orchestrator，latest=1.6.0、moderation verdict=clean（isSuspicious=false、isMalwareBlocked=false）。

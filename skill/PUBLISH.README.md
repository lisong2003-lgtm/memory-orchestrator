# 发布状态（2026-10-20，v1.8.0 三平台发布 · 实机回查）

- 本机技能原版 canonical：v1.8.0；合规预检 problems=0；self_test 22/22 PASS。
- 发布包：releases/memory-orchestrator-v1.8.0-full.zip、releases/memory-orchestrator-v1.8.0-skillhub.zip、releases/SHA256SUMS.txt。
- 变更：步骤编排支持免逐步确认模式、render --json 纯净输出；发布脱敏移除私有本机路径；保留 1.7.0 的 15 万 token/8 轮互补换新对话规则。

## 三平台实机回查

- GitHub：Release `v1.8.0`（commit e7f6cc0），非草案、资产 3 个齐全（full zip / skillhub zip / SHA256SUMS.txt）。
- SkillHub：`codex-memory-orchestrator` 当前 latest = **1.8.1（SkillHub 平台合规版）**，versionId=448107，reviewStatus=approved，keen=benign、sanbu=benign，isLatest=true。说明：平台安全扫描将 1.8.0 默认免确认标记为可疑（suspicious），故 SkillHub 平台专用版将步骤编排默认改为“逐次确认”，仅用户显式 AUTO=1 时免确认；此调整不回写本机原版/GitHub/ClawHub。历史 v1.8.0 已退出 latest（sanbu 保留 suspicious 状态，不影响 latest）。
- ClawHub：`codex-memory-orchestrator` 当前 latest = **1.8.0**，moderation 回查为 clean（isSuspicious=false、isMalwareBlocked=false、verdict=clean）。

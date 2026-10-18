# memory-orchestrator

Codex 长对话记忆管理技能：对话超过 12 轮或上下文变模糊时主动提醒开新对话；用 cp-memory 检索/写入长期记忆；用 ctxcompress（CLI，shell 调用）压缩历史；按模板生成恢复包，让新对话 5 行内接续。

## 能力边界

- 只做本地记忆与交接，不上传公司数据。
- cp-memory 不可用时降级写 `$CODEX_HOME/memory/hot.md`（或 `$HOME/.codex/memory/hot.md`）。
- ctxcompress 是 CLI，只能 shell 调用，不注册为 MCP 工具。
- 触发词：总结 / 压缩 / 恢复 / 交接 / 开新对话 / checkpoint。

## 目录结构

```
memory-orchestrator/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── LICENSE.md
├── assets/
│   ├── skill-banner.svg
│   └── skill-icon.svg
├── references/
│   └── templates.md        # 恢复包模板
└── scripts/
    ├── export_ctx.py       # rollout jsonl → messages 数组
    ├── state.py            # 轮次计数/活跃项目
    ├── recovery.py         # 恢复包索引
    └── self_test.py        # 12 项自检
```

## 使用前提

- 可选：`uvx cp-memory-mcp` 或本机持久 `cp-memory-mcp`（记忆库）。
- 可选：`agent-ctx-compress` 提供 `ctxcompress`；缺失时用 5-8 行手动摘要降级。
- 在 Codex 全局规则 `AGENTS.md` 注入 4 条铁律后生效。

## 授权与发布

本技能源码以 MIT 协议发布。平台专用调整不回写本机原版。

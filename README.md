# memory-orchestrator

Codex 长对话记忆管理技能（本机原版 v1.2.0）：对话自动监测：累计轮数达到阈值（硬阈值 8，提前 1 轮即 >=7 提醒一次，>=8 强制生成恢复包并引导开新对话）；用 cp-memory 检索/写入长期记忆；用 ctxcompress（CLI，shell 调用）压缩历史；按模板生成恢复包，让新对话 5 行内接续。

## 能力边界

- 只做本地记忆与交接，不上传公司数据。
- cp-memory 不可用时降级写 `$CODEX_HOME/memory/hot.md`。
- ctxcompress 是 CLI，只能 shell 调用，不注册为 MCP 工具。
- 触发词：总结 / 压缩 / 恢复 / 交接 / 开新对话 / checkpoint。
- checkpoint/压缩默认限定当前 active_project，仅处理该项目的 rollout 文件；临时产物用完即删。

## 目录结构

```
memory-orchestrator/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── LICENSE.md
├── references/
│   └── templates.md        # 恢复包模板
└── scripts/
    ├── export_ctx.py       # rollout jsonl → messages 数组（--project 校验）
    ├── monitor_dialogs.py  # 跨对话框轮数监测（UserMessage 真实计数）
    ├── state.py            # 轮次计数/活跃项目
    ├── recovery.py         # 恢复包索引
    └── self_test.py        # 12 项自检
```

## 使用前提

- 可选：本机持久 `cp-memory-mcp`（记忆库）。
- 可选：`agent-ctx-compress` 提供 `ctxcompress`；缺失时用 5-8 行手动摘要降级。
- 在 Codex 全局规则 `AGENTS.md` 注入上下文健康铁律后生效。
- 跨对话框监测依赖 Codex Home 下 `sessions/` 与 `sqlite/codex-dev.db`（Windows 自动用 `%USERPROFILE%\.codex`，可用 `--sessions-dir`/`--catalog-db` 覆盖）。自动运行：macOS 用 Codex 自动化，Windows 用任务计划程序，Linux 用 crontab，详见 SKILL.md。

## 授权与发布

本技能源码以 MIT 协议发布。平台专用调整不回写本机原版。

# memory-orchestrator
**[English](./README.en.md) | [中文](./README.md)**

对话记忆管家 v2.1.0：管住长对话的上下文，而不是把“窗口上限”误当成“已消耗 token”。所有阈值只在 `policy.json` 维护；五项闸门任一先到即交接——**8 轮 / 累计 token（input+output）150000 / 单请求 input 峰值 100000 / 请求次数 120 / 单会话累计 input 8000000**；另设**当前上下文达到有效窗口 80% 强制、65% 预警**作为加速线。

## 它解决的四个问题

1. **token 口径错**：旧版把 `thread_token_usage.total_tokens`（累计计费，含缓存命中和多轮工具调用）当上下文阈值，七轮就能报出数百万，必误报。现在分开记 `context_tokens`（当前请求输入）、`context_peak`（历史峰值）、`spent_tokens`（累计花费）。
2. **窗口口径错**：`config.toml` 的 `model_context_window` 只是应用层覆盖；真实窗口看模型目录 `context_window × effective_context_window_percent`，或会话 `event_msg.info.model_context_window`。窗口上限本身不消耗 token。
3. **状态串号**：state 以 `thread_id` 为稳定键，项目名变化不再拆成多条；旧的“项目名||线程”记录自动合并。
4. **监测失真**：只监测 `thread_turns.status='inProgress'` 的对话框；查询成功但为空时返回空集，不退化成“全部未归档”。

## 省 token 的实际动作

- 每轮只做一次轻量 `state.py bump`：读 rollout 元数据，不读正文，不额外调用模型。
- 达到预警线先提醒一次并准备恢复包；达到硬阈值输出 `split_now`，新对话只带恢复包，不回灌整段历史。
- 跨对话扫描只读 usage 字段，不导出消息；历史压缩用本机 `ctxcompress`，不注册 MCP。
- 提醒去重：同一线程 `warned`/`forced` 只触发一次，避免每轮重复刷屏、重复消耗。

## 安装位置

```
$CODEX_HOME/skills/memory-orchestrator/
├── SKILL.md
├── policy.json              # 唯一策略源
├── README.md / README.en.md / CHANGELOG.md
├── references/
│   ├── templates.md         # 恢复包模板
│   └── agent-gateways.md    # 跨 Agent 能力矩阵
└── scripts/
    ├── thread_usage.py      # 只读 rollout：轮数/上下文/累计花费/窗口
    ├── state.py             # 按 thread_id 计数、阈值判定、旧键合并
    ├── agent_hook.sh        # 每轮实时钩子（不读正文）
    ├── monitor_dialogs.py   # 跨对话框定时兜底
    ├── recovery.py          # 恢复包索引
    ├── recovery_prompt.py   # 恢复包 → create_thread 首条消息
    ├── handoff_gateway.py   # 一键新对话（能力矩阵降级）
    ├── export_ctx.py        # rollout → messages（压缩前导出）
    └── self_test.py         # 自检
```

## 使用

```sh
# 每轮用户提问结束时（写进全局 AGENTS.md）
bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh \
  agent=codex active_project=<项目> thread_id=<对话框ID>

# 定时兜底：每小时
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/monitor_dialogs.py \
  --days 3 --write-state --json

# 自检
python3 $CODEX_HOME/skills/memory-orchestrator/scripts/self_test.py
```

输出 `action`：`continue` / `prepare_split` / `split_now`。到 `split_now` 时先生成恢复包，再开新对话，本对话不再续接。

## 无人值守

`~/Library/LaunchAgents/com.lis.memory-orchestrator.plist` 每小时跑一次 `monitor_dialogs.py --days 3 --write-state --json`，日志在 `~/Library/Logs/memory-orchestrator.out.log` / `.err.log`。没有 LaunchAgent 时，也可用 Codex 自动化每天/每小时调用同一命令。

## 能力边界

- 只做本地记忆与交接，不上传公司数据；公司数据只禁公开发布，不禁本人自用传输/备份/云端处理。
- cp-memory 不可用时降级写 `$CODEX_HOME/memory/hot.md`；state/recovery 主路径不可写时降级到 `$TMPDIR/memory-orchestrator/` 并标 `storage.mode`。
- ctxcompress 是 CLI，只能 shell 调用，不注册为 MCP 工具。
- 触发词：总结 / 压缩 / 恢复 / 交接 / 开新对话 / checkpoint。
- 恢复包默认限定当前 `active_project`，临时产物用完即删。
- 跨对话框监测依赖 `$CODEX_HOME/sessions/` 与 `$CODEX_HOME/sqlite/codex-dev.db`；可用 `--sessions-dir`/`--catalog-db` 覆盖。

## 授权与发布

本技能源码以 MIT 协议发布。平台专用调整不回写本机原版；发布前按全局规则脱敏，公司真图/真项目名/真路径/真实人名不得进入公开发布包。

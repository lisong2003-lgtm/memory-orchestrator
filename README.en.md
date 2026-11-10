# Long-Conversation Memory Orchestrator

> memory-orchestrator v2.1.0 · 中文版见 [README.md](README.md).

## What it is

Orchestrates long-conversation memory without confusing the **context-window size** with **tokens actually spent**. All thresholds live in `policy.json`, with five gates that trigger a handoff at whichever comes first: 8 turns / 150000 cumulative tokens (input+output) / 100000 peak single-request input / 120 model requests / 8000000 cumulative session input. In addition, 80% of the effective context window is a hard line and 65% a warning line.

## Token semantics

- `context_tokens`: input tokens of the latest model request — the real context pressure.
- `context_peak`: largest context seen in this thread — diagnostics only.
- `spent_tokens`: cumulative `thread_token_usage.total_tokens` — cost display only.
- `window_tokens`: the runtime `model_context_window` (model catalog × effective percent). `config.toml` is an app-level override, not the provider guarantee.
- The window limit itself consumes no tokens. Tokens are consumed by resending a large context and by tool calls per turn.

## When to use it

Use in any long-running agent workflow that must not lose context or blow past the context window.

## Quick start

```bash
python3 scripts/step_orchestrator.py status --project MyProject
python3 scripts/state.py get
bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=codex active_project=MyProject thread_id=<id>
```

The hook prints `action`: `continue`, `prepare_split`, or `split_now`. At `split_now`, write a recovery pack first, then open a new thread; the old thread is not continued.

## Install across the three platforms

- **GitHub**: clone or download the repo, copy the skill folder into `$CODEX_HOME/skills/` (or `~/.claude/skills/` / your agent's skill directory).
- **SkillHub**: install the SkillHub lightweight package (text-only). The lightweight package removes platform-only launcher files (`.cmd`/`.ps1`, extensionless scripts and binary language models) and documents Windows usage inside its own README; the GitHub full package keeps all launchers and assets.
- **ClawHub**: install the ClawHub full package, which keeps cross-platform launchers and assets.
- All platform packages serve the same canonical logic; platform copies never change the canonical code.

## Unattended monitoring

`~/Library/LaunchAgents/com.lis.memory-orchestrator.plist` runs `monitor_dialogs.py --days 3 --write-state --json` hourly; logs under `~/Library/Logs/memory-orchestrator.{out,err}.log`.

## Dependencies

Python 3.8+ standard library; optional ctxcompress CLI at `$CODEX_HOME/tools/agent-ctx-compress/bin/ctxcompress` for history compression.

## Privacy

Reads session metadata and usage fields only; never reads message content and never uploads data.

## Boundaries / limitations

Does not store chat transcripts; it writes recovery packs and state files locally only. Company data is restricted from public release, not from the owner's own transfer, backup, or cloud processing.

## License

MIT

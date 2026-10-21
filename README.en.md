# Long-Conversation Memory Orchestrator

> memory-orchestrator (memory-orchestrator) v1.9.0 · overseas-friendly lightweight layer. 中文版见 [README.md](README.md).

## What it is
Orchestrates long-conversation memory: session-start memory retrieval, automatic monitoring of dialog turn count and token usage, threshold-triggered recovery-pack generation (default 8 turns or 150k tokens, whichever arrives first), checkpointing, history compression, and end-of-session archiving into a new dialog.

## When to use it
Use in any long-running agent workflow that must not lose context or blow past the context window.

## Quick start
```bash
python3 scripts/step_orchestrator.py status --project MyProject
python3 scripts/state.py get
bash $CODEX_HOME/skills/memory-orchestrator/scripts/agent_hook.sh agent=codex active_project=MyProject thread_id=<id>
```

## Install across the three platforms
- **GitHub**: clone or download the repo, copy the skill folder into `$CODEX_HOME/skills/` (or `~/.claude/skills/` / your agent's skill directory).
- **SkillHub**: install the SkillHub lightweight package (text-only). The lightweight package removes platform-only launcher files (`.cmd`/`.ps1`, extensionless scripts and binary language models) and documents the Windows usage inside its own README; the GitHub full package keeps all platform launchers and assets.
- **ClawHub**: install the ClawHub full package, which keeps cross-platform launchers and assets.
- All platform packages serve the same canonical logic; platform copies never change the canonical code.

## Dependencies
Python 3.8+ standard library; optional ctxcompress CLI at $CODEX_HOME/tools/agent-ctx-compress/bin/ctxcompress for history compression.

## Privacy
Only counts turns and token metrics; never reads conversation content or uploads data.

## Boundaries / limitations
Does not store chat transcripts; it writes recovery packs and state files locally only.

## License
CC-BY-NC-SA-4.0

---

## Culture note
- `--lang en|zh` controls UI/help/JSON message language (default `zh`); business algorithms are identical in both languages.
- For image-ocr, `--lang` remains the OCR language; UI language is `--ui-lang en|zh`.
- Local Chinese templates and plant/concept dictionaries are NOT replaced; overseas inputs can select alternatives via parameters (e.g. `--plant-library`, `--project-rules`) so existing Chinese users are unaffected.
- Review flags, confidence tiers and evidence coordinates are language-independent fields.

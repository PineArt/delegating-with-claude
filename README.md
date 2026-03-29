# delegating-with-claude

Higher-level delegation workflow for Claude from Codex.

This skill sits above `collaborating-with-claude` and answers one specific problem:

How do you make Codex automatically prepare a compact structured handoff before delegating to Claude?

## What It Changes

Instead of calling Claude with ad-hoc `--context` text, this skill standardizes the flow:

1. Codex synthesizes the current known context.
2. Codex maps it into a fixed structured handoff.
3. Codex calls `scripts/claude_delegate.py`.

## Recommended Structured Fields

- `summary`
- `relevant_files`
- `findings`
- `constraints`
- `next_step`

Optional:

- `repo_facts`
- `open_questions`

## Delegate Wrapper

This skill is self-contained and now ships the required scripts locally:

- `scripts/claude_delegate.py`
- `scripts/claude_bridge.py`

## Why A Separate Skill

The bridge and wrapper can transport context, but they cannot infer Codex's internal working context on their own.

That synthesis step must live in skill instructions, because the model has to decide:

- what is already known
- what is worth handing off
- what should be omitted

## Minimal Example

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "Short high-confidence summary." \
  --context-file-ref "src/app.ts :: entry point" \
  --context-finding "Concrete known conclusion." \
  --context-constraint "Keep API unchanged." \
  --context-next-step "Specific next action." \
  --PROMPT "Do the next task."
```

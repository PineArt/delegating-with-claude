# delegating-with-claude

Higher-level delegation workflow for Claude from Codex.

This skill sits above `collaborating-with-claude` and answers one specific problem:

How do you make Codex automatically prepare a compact structured handoff before delegating to Claude?

## What It Changes

Instead of calling Claude with ad-hoc `--context` text, this skill standardizes the flow:

1. Codex synthesizes the current known context.
2. Codex maps it into a fixed structured handoff.
3. Codex calls the delegate wrapper with an explicit subcommand.

## Recommended Structured Fields

- `summary`
- `relevant_files`
- `findings`
- `constraints`
- `next_step`

Optional:

- `repo_facts`
- `open_questions`

## Delegate Entrypoint

This skill is self-contained. Run the delegate wrapper explicitly with Python and a subcommand:

- `python scripts/claude_delegate.py run` for a synchronous one-shot delegation
- `python scripts/claude_delegate.py start` for an async delegation job

Never execute `scripts/claude_delegate.py` directly, including for `--help` smoke checks. On Windows, direct `.py` execution can exit without useful stdout depending on file association behavior.

It also ships `scripts/claude_bridge.py` as an internal Claude CLI transport used by the delegate wrapper. Call the bridge directly only for low-level diagnostics, such as checking whether Claude CLI launch, stdin transport, or JSON response parsing works without the structured handoff layer.

The old no-subcommand invocation is intentionally removed. Use `run` when you want a blocking call, or `start/status/wait/stop/resume` when the main Codex thread should choose how long to wait and how often to poll.

Async job semantics:

- `start` returns a local `job_id` and persists prompt, handoff, stdout, stderr, and job metadata.
- `status` reads local job state only; it does not contact Claude.
- `wait --timeout <seconds>` only stops waiting and reports `timed_out`; it never kills the job.
- `stop` is the only user-facing command that terminates a running job.
- `resume --SESSION_ID <id>` starts an async resume job and refuses to run when the same session already has a running job.

`run` keeps `--timeout-seconds <seconds>` for short one-shot delegations. Async jobs use `wait --timeout` instead.

## Why A Separate Skill

The delegate wrapper can transport context, but it cannot infer Codex's internal working context on its own.

That synthesis step must live in skill instructions, because the model has to decide:

- what is already known
- what is worth handing off
- what should be omitted

## Minimal Example

```bash
python scripts/claude_delegate.py --help
```

```bash
python scripts/claude_delegate.py run \
  --cd "/project" \
  --context-summary "Short high-confidence summary." \
  --context-file-ref "src/app.ts :: entry point" \
  --context-finding "Concrete known conclusion." \
  --context-constraint "Keep API unchanged." \
  --context-next-step "Specific next action." \
  --PROMPT "Do the next task."
```

```bash
python scripts/claude_delegate.py start \
  --cd "/project" \
  --context-summary "Short high-confidence summary." \
  --context-next-step "Specific next action." \
  --PROMPT "Review the current plan."
```

```bash
python scripts/claude_delegate.py status --job-id "<job_id>"
python scripts/claude_delegate.py wait --job-id "<job_id>" --timeout 60
python scripts/claude_delegate.py stop --job-id "<job_id>"
python scripts/claude_delegate.py resume --SESSION_ID "<session_id>" --cd "/project" --PROMPT "Report progress."
```

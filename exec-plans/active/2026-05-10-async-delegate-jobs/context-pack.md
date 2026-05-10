## Step S2. Context Pack

Core Context:
- The wrapper currently uses a synchronous `subprocess.run(..., timeout=...)` path and kills on timeout.
- The user wants the main thread to own wait/poll cadence.
- The agreed design is an async job model with explicit `start/status/wait/stop/resume/run`.

Optional Context:
- Existing handoff synthesis, preview, save, review-item handling, stdin prompt transport, UTF-8 handling, and model forwarding should remain intact.
- The old no-subcommand invocation should be removed rather than quietly preserved.

Forbidden Scope:
- Do not build a new general task runner unrelated to Claude delegation.
- Do not add unrelated repo-wide refactors.

Stable Prefix:
- Use the current `scripts/claude_delegate.py` and `scripts/claude_bridge.py` as the implementation surface.

Required Tools:
- `python`
- `pytest`
- `python scripts/validate_harness_run.py <run-workspace>`


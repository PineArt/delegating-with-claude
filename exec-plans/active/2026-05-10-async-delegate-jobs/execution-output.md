## Step S4. Execution Output Record

Objective:
Implement an explicit async delegate job model with `start`, `status`, `wait`, `stop`, `resume`, and `run`.

Inputs:
- S0-S3 harness artifacts in this run workspace.
- Opus consensus recommending the async job model.
- User decision to remove old no-subcommand compatibility.

Method:
- Added explicit subcommand parsing in `scripts/claude_delegate.py`.
- Added local async job primitives in `scripts/claude_jobs.py`.
- Updated docs in `README.md` and `SKILL.md`.
- Added regression coverage in `tests/test_claude_delegate.py`.
- Added `.claude-delegate-jobs/` to `.gitignore`.

Outputs:
- `scripts/claude_delegate.py`: explicit subcommands and migration error for no-subcommand usage.
- `scripts/claude_jobs.py`: local job store, worker launcher, status/wait/stop/session lock handling.
- `tests/test_claude_delegate.py`: tests for explicit subcommands, async wait/stop/status/session lock behavior, resolved background `cd`, launch-failure lock cleanup, and help contracts.
- `README.md` and `SKILL.md`: documented async command surface.

Acceptance:
- `python -m py_compile scripts\claude_delegate.py scripts\claude_jobs.py scripts\claude_bridge.py` passed with `PYTHONDONTWRITEBYTECODE=1`.
- `pytest -q tests\test_claude_delegate.py tests\test_claude_bridge.py` passed with 33 tests.
- Fake `claude.cmd` async CLI smoke passed through `start -> wait -> status`.
- `python scripts\claude_delegate.py --cd . --PROMPT hi` fails with the migration hint.
- Final Quality Gate re-gate returned Pass after reviewing the atomic lock rework and launch-failure cleanup.

Risks:
- The default job store is local repo state; cleanup policy is intentionally not automated yet.
- Stale detection depends on local PID visibility and is best-effort.

Escalation:
- If gate finds job lifecycle or CLI semantics issues, return to S4 implementation.

Fact / Inference / Open Question:
- Fact: The async fake CLI smoke persisted session `fake-session-1` and returned `FAKE_OK`.
- Fact: `status` reads local records and does not invoke Claude.
- Inference: The same patterns should handle long Opus jobs without turning wait timeout into process termination.
- Open Question: Whether to add a future cleanup command for old job records.

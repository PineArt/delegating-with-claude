## S4 Rework Output

Objective:
Close the Quality Gate finding that `SESSION_ID` locking was scan-then-create rather than atomic.

Inputs:
- Gate Decision 001.
- Existing `scripts/claude_jobs.py` job store implementation.

Method:
- Added a hashed per-session lock file under `<job-store>/locks/`.
- Acquired the lock with exclusive file creation before writing a job record.
- Made the lock block if a competing job record is not yet visible, closing the scan/create window.
- Released locks when jobs enter terminal states.
- Allowed stale/terminal locks to be reclaimed after local stale refresh.

Outputs:
- `scripts/claude_jobs.py`: atomic `acquire_session_lock()` and `release_session_lock()` helpers.
- `tests/test_claude_delegate.py`: tests for atomic acquisition, second-acquire rejection, terminal lock reclaim, and stale same-session recovery.

Acceptance:
- `PYTHONDONTWRITEBYTECODE=1 python -m py_compile scripts\claude_delegate.py scripts\claude_jobs.py scripts\claude_bridge.py` passed.
- `pytest -q tests\test_claude_delegate.py tests\test_claude_bridge.py` passed with 33 tests after final startup-failure and resolved-`cd` hardening.
- Fake CLI async smoke still passed through `start -> wait -> status`.

Risks:
- Lock cleanup remains best-effort for abruptly killed parent processes before any job record is written.

Escalation:
- If re-gate still fails on lock behavior, return to S4 and add an explicit lock recovery policy.

Fact / Inference / Open Question:
- Fact: A second lock acquisition for the same session now raises before job creation.
- Fact: Terminal lock records can be reclaimed.
- Inference: Concurrent same-session resume is now mechanically blocked on local filesystems that honor exclusive create.
- Open Question: Whether to add age-based orphan lock cleanup in a future command.

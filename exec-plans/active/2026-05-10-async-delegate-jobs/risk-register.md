## Step S5. Risk Register

Risk: Async job store records may accumulate over time.
Severity: Low
Evidence: `.claude-delegate-jobs/` is ignored and no cleanup command was added.
Owner: Orchestrator
Mitigation: Documented as residual risk; cleanup can be a future explicit command.

Risk: Stale detection and orphan lock recovery are best-effort.
Severity: Medium
Evidence: Implementation uses stored worker/child PID visibility to mark stale jobs as failed before session-lock decisions; locks are reclaimed when their job record is terminal or stale-refreshed.
Owner: Implementer
Mitigation: Tests cover stale same-session release and terminal lock reclaim; real process edge cases should be watched after first long run.

Risk: Users may still try the removed high-level `run` command from old examples.
Severity: Low
Evidence: This follow-up removes the `run` subparser and updates README/SKILL examples to use `start`/`wait`.
Owner: Orchestrator
Mitigation: Tests assert `run` is rejected and public docs state the delegate wrapper is async-only; low-level synchronous diagnostics remain in `scripts/claude_bridge.py`.

Risk: New helper module could be missed in staging.
Severity: Medium
Evidence: `scripts/claude_jobs.py` is new and appears untracked in `git status`.
Owner: Orchestrator
Mitigation: Include it explicitly in the gate package and final staging.

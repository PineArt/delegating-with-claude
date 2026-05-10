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

Risk: `run` still has synchronous timeout semantics.
Severity: Low
Evidence: `run` deliberately preserves `--timeout-seconds`; async jobs move timeout semantics to `wait`.
Owner: Orchestrator
Mitigation: Docs clearly recommend async jobs for long review-heavy work.

Risk: New helper module could be missed in staging.
Severity: Medium
Evidence: `scripts/claude_jobs.py` is new and appears untracked in `git status`.
Owner: Orchestrator
Mitigation: Include it explicitly in the gate package and final staging.

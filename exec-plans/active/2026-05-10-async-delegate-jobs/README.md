# Async Delegate Jobs Harness

## Step S0. Task Brief

Goal:
Refactor the Claude delegate wrapper into an explicit async job model with `start`, `status`, `wait`, `stop`, `resume`, and `run`, removing the old no-subcommand compatibility path.

Non-goals:
- No unrelated refactors outside the delegate wrapper, its helper layer, and targeted docs/tests.
- No attempt to preserve the legacy no-subcommand entrypoint behavior.
- No live remote deployment work in this run.

Constraints:
- `wait --timeout` only stops waiting; it never kills the underlying job.
- `stop` is the only explicit kill path.
- `status` must read local job state only.
- `SESSION_ID` resume must reject concurrent jobs for the same session.
- Existing prompt synthesis, stdin transport, UTF-8 handling, and explicit model forwarding must keep working.

Success Criteria:
- The CLI exposes explicit subcommands for the async job model.
- The old no-subcommand invocation fails with a migration hint.
- Tests prove wait timeout does not kill, stop does kill, status is local-only, and concurrent same-session resumes are rejected.
- The run validates through the harness script and focused test commands.

Human Decision Points:
- Whether the default convenience path should be `run` or something else.
- Whether any extra job-store cleanup policy is needed after completion.

## Run Workspace

Run ID:
2026-05-10-async-delegate-jobs
Tier: Lite
Created Before Step: S0
Active Path:
C:/Users/wangsong/.codex/skills/delegating-with-claude-worktrees/20260510-async-delegate-jobs-async-delegate-jobs/exec-plans/active/2026-05-10-async-delegate-jobs
Completed Path:
C:/Users/wangsong/.codex/skills/delegating-with-claude-worktrees/20260510-async-delegate-jobs-async-delegate-jobs/exec-plans/completed/2026-05-10-async-delegate-jobs
Artifact Index:
- CURRENT.md
- checkpoints/0001-S1.md
- checkpoints/0002-S3.md
- checkpoints/0003-S5.md
- checkpoints/0004-S7.md
- checkpoints/0005-S8.md
- README.md
- role-owner-table.md
- responsibility-matrix.md
- context-pack.md
- task-graph.md
- execution-output.md
- runtime-evidence.md
- decision-log.md
- risk-register.md
- integration-ledger.md
- gate-decision-001.md
- gate-decision-002.md
- publish-record.md
Step Closure Gates:
- S0: Task Brief, Run Workspace, Decision Log
- S1: Role Owner Table, Run-Specific Responsibility Matrix, validator pass, fresh checkpoint
- S2: Context Pack
- S3: Task Graph, fresh checkpoint
- S4: implementation outputs and validation evidence
- S5: Risk Register
- S6: Integration Ledger
- S7: Gate Decision
- S8: publish evidence and final records
Exception Paths:
- If the harness validator rejects the run as non-publishable, stop and reclassify before implementation.
Continuation Current: CURRENT.md
Checkpoint Directory: checkpoints/

## Telemetry

Telemetry Mode: Off
Event Log Path: <none>
Profiler Summary Path: <none>
Timing Semantics: Use the Run Telemetry timing rules in artifact-registry.md

# Harness Record: delegate entrypoint and bridge diagnostic boundary

Date: 2026-04-29
Repo: C:\Users\wangsong\.codex\skills\delegating-with-claude
Tier: Lite implementation

## Task Brief

Goal:
Reduce caller friction around `claude_delegate.py` versus `claude_bridge.py` without losing the low-level bridge diagnostic path.

Non-goals:
- Do not physically merge bridge transport code into delegate.
- Do not remove bridge CLI diagnostics.
- Do not change Claude invocation behavior.

Constraints:
- Keep the existing import boundary: delegate calls `run_claude()` in-process.
- Make delegate the only normal public entrypoint.
- Mark bridge as internal diagnostic transport.

Success Criteria:
- README and SKILL no longer present delegate and bridge as peer entrypoints.
- Script docstrings/help match the intended boundary.
- Existing tests pass.
- External critique finds no blocking issue.

Human Decision Points:
- User approved changing the surface after discussing physical merge versus product-surface merge.

## Role Owner Table

Role | Owner | Context Boundary | Shared? | Notes
Orchestrator | Codex | Main Codex thread | Yes | Scoped and integrated the change.
Implementer | Codex | Main Codex thread | Yes | Edited README, SKILL, and script docstrings/help description.
Critic | Claude/Opus delegate | External Claude session | No | Pre-change SESSION_ID a3a8eda9-8afb-4063-95f2-8c6c5b4e7666; post-change SESSION_ID a8d7d550-df5d-4986-828a-7ecb8af93beb.
Quality Gate | Codex | Main Codex thread | Yes | Gate based on source diff, tests, smoke, and external critique.

Boundary note:
Lite publish-grade separation is limited because Codex owns implementation and gate, but the user requested harness for a small surface change and external Claude critique was used before and after the edit.

## Context Pack

Core Context:
- Prior architecture already removed the delegate-to-bridge Python subprocess boundary.
- `claude_delegate.py` imports `run_claude()` from `claude_bridge.py`.
- `claude_bridge.py` remains useful as a raw Claude CLI transport diagnostic.

Optional Context:
- README previously listed both scripts under the same wrapper section.
- SKILL already preferred delegate, but the wording still allowed callers to treat bridge as an alternate normal path.

Forbidden Scope:
- No behavior changes to Claude invocation, prompt transport, timeout, UTF-8 handling, or JSON parsing.

Stable Prefix:
- Delegate is the normal structured handoff entrypoint.
- Bridge is internal transport and direct diagnostic only.

Required Tools:
- `apply_patch`
- `py_compile`
- pytest
- delegate preview-handoff
- bridge help
- Claude/Opus review

## Task Graph

Task:
Pre-change critique.
Owner:
Claude/Opus delegate
Context Boundary:
External Claude session
Depends On:
Current code/docs inspection
Outputs:
Plan selection critique
Writable Area:
Claude delegate output
Fallback:
Use inspected source evidence if delegate failed.

Task:
Patch entrypoint wording.
Owner:
Codex
Context Boundary:
Main Codex thread
Depends On:
Pre-change critique
Outputs:
README/SKILL/docstring/help wording changes
Writable Area:
README.md, SKILL.md, scripts/claude_bridge.py, scripts/claude_delegate.py
Fallback:
Revert only Codex edits if tests failed beyond wording repair.

Task:
Validate and review.
Owner:
Codex plus Claude/Opus delegate
Context Boundary:
Main Codex thread plus external Claude session
Depends On:
Patch entrypoint wording
Outputs:
Validation record and post-change critique
Writable Area:
output/harness
Fallback:
Address concrete findings and rerun tests.

## Execution Output Record

Objective:
Make the public surface say `claude_delegate.py` is the normal entrypoint and `claude_bridge.py` is internal diagnostic transport.

Inputs:
- README.md
- SKILL.md
- scripts/claude_bridge.py
- scripts/claude_delegate.py
- tests/test_claude_bridge.py
- tests/test_claude_delegate.py

Method:
- Updated README `Delegate Wrapper` to `Delegate Entrypoint` and listed only `scripts/claude_delegate.py` as normal entrypoint.
- Added README note that `scripts/claude_bridge.py` is internal transport for low-level diagnostics.
- Strengthened SKILL Recommended Command Pattern with the same boundary.
- Updated bridge docstring to mark internal diagnostic transport.
- Updated delegate docstring and argparse description to call it the primary structured delegation entrypoint.

Outputs:
- Modified README.md
- Modified SKILL.md
- Modified scripts/claude_bridge.py
- Modified scripts/claude_delegate.py

Acceptance:
- Wording consistently demotes bridge from normal caller surface.
- No behavior code changed except argparse description text.
- Tests and smoke checks pass.

Risks:
- Very small risk that users who intentionally call bridge see the word internal and hesitate; diagnostic direct use remains explicitly documented.

Escalation:
- If future confusion continues, consider renaming bridge to transport with a compatibility stub, but do not do that in this patch.

Fact / Inference / Open Question:
- Fact: Code behavior is unchanged except help description text.
- Fact: Existing tests pass.
- Inference: This should reduce caller friction by removing peer-entrypoint framing.
- Open Question: Whether a future rename from bridge to transport is worth the churn.

## Runtime Evidence Record

State Surface:
Local Windows Python runtime and repo test suite.

Starting State:
`main...origin/main`, clean before edits.

Method:
- `python -m py_compile scripts\claude_delegate.py scripts\claude_bridge.py`
- `C:\Users\wangsong\AppData\Roaming\Python\Python313\Scripts\pytest.exe tests`
- `python scripts\claude_delegate.py --cd . --context-summary "中文 smoke" --context-file-ref "README.md :: entrypoint docs" --preview-handoff --PROMPT "检查入口说明"`
- `python scripts\claude_bridge.py --help`
- `git diff --check`

Evidence:
- py_compile passed.
- pytest collected 14 items and passed 14/14.
- preview-handoff printed the expected Chinese handoff.
- bridge help still printed diagnostic CLI options.
- git diff --check produced only CRLF warnings for modified files.

Result:
Validation passed.

Residual Risk:
No live Claude call was run for this docs/help wording patch because behavior code was not changed.

Fact / Inference / Open Question:
- Fact: Tests lock bridge/delegate behavior after the wording change.
- Inference: Preview smoke is enough for this non-behavioral change.

## Risk Register

- Risk:
  Accidentally implying bridge cannot be used directly at all.
  Severity:
  Low
  Evidence:
  README/SKILL/docstring explicitly say direct bridge use is for low-level diagnostics.
  Owner:
  Codex
  Required Action:
  Keep diagnostic wording in final patch.
  Status:
  Closed

- Risk:
  Physical merge is still desired later.
  Severity:
  Low
  Evidence:
  Pre-change critique judged physical merge higher risk and lower value because import boundary already removed the subprocess layer.
  Owner:
  Codex
  Required Action:
  Treat rename/merge as separate future design work if confusion persists.
  Status:
  Closed

## Integration Ledger

Agent:
Claude/Opus pre-change
Claim:
Plan A is the smallest change that fixes README peer-entrypoint confusion without losing diagnostics.
Artifact Name:
Pre-change critique
Owner:
Claude/Opus delegate
Evidence Source:
SESSION_ID a3a8eda9-8afb-4063-95f2-8c6c5b4e7666
Decision:
Accepted
Next Step Or Fallback:
Patch README/SKILL/docstrings only.

Agent:
Codex
Claim:
Patch changes wording only and preserves behavior.
Artifact Name:
Execution Output Record
Owner:
Codex
Evidence Source:
`git diff`
Decision:
Accepted
Next Step Or Fallback:
Run tests and smoke.

Agent:
Claude/Opus post-change
Claim:
No findings; patch is acceptable as-is.
Artifact Name:
Post-change critique
Owner:
Claude/Opus delegate
Evidence Source:
SESSION_ID a8d7d550-df5d-4986-828a-7ecb8af93beb
Decision:
Accepted
Next Step Or Fallback:
Report result.

## Decision Log

Decision:
Use product-surface merge, not physical file merge.
Decision Owner:
Codex
Reason:
Existing code already uses an in-process import boundary; bridge remains valuable for diagnostics.
Affected Artifact:
README.md, SKILL.md, scripts docstrings
Recorded At:
2026-04-29 13:05 Asia/Shanghai
Next Step:
Keep behavior code unchanged.

Decision:
Treat CRLF messages from `git diff --check` as non-blocking warnings.
Decision Owner:
Codex
Reason:
`git diff --check` found no whitespace errors, only Windows line-ending conversion notices.
Affected Artifact:
Runtime Evidence Record
Recorded At:
2026-04-29 13:05 Asia/Shanghai
Next Step:
No action.

## Gate Decision

Gate:
Lite implementation gate
Verdict:
Pass
Blocking:
None
Source Fidelity:
Pass. Change follows inspected source and external critique.
Boundary Integrity:
Conditional by strict publish standard, but sufficient for this small non-behavioral patch with external critique.
Execution Completeness:
Pass. Scope, patch, validation, risk scan, and critique are complete.
External Feedback:
Pass. pytest, preview smoke, bridge help, and external review passed.
Return Step:
N/A
Rework Owner:
N/A
Re-gate Owner:
N/A
Re-gate Condition:
N/A
Re-gate Evidence:
N/A
Due Before:
N/A

---
name: delegating-with-claude
description: High-level Claude delegation workflow for Codex. Always synthesize a compact structured handoff from current context before calling the Claude delegate wrapper. Use when you want automatic context packaging rather than manually writing --context.
---

## Purpose

Use this skill when Codex should delegate work to Claude **with a structured handoff generated first**.

This skill is the workflow layer on top of `collaborating-with-claude`:

- First, synthesize what Codex already knows into a compact handoff.
- Second, pass that handoff through `scripts/claude_delegate.py`.
- Third, continue with `SESSION_ID` if more Claude turns are needed.

Use `collaborating-with-claude` directly only when you explicitly want low-level manual control.

## Required Workflow

Before calling Claude, always do the following:

1. Collect only the context already established in the current Codex turn.
2. Convert that context into a structured handoff.
3. Prefer structured fields over free-form `--context`.
4. Omit unknown sections instead of inventing details.
5. Call `scripts/claude_delegate.py` with the structured handoff.

Do not skip handoff generation unless the user explicitly asks for raw passthrough.

## Default Handoff Schema

Prefer this minimal schema:

- `summary`
- `relevant_files`
- `findings`
- `constraints`
- `next_step`

Optional when useful:

- `repo_facts`
- `open_questions`
- `review_items`

## Handoff Quality Bar

Good handoffs are:

- Short
- High-confidence
- Actionable
- File-specific where possible

Bad handoffs:

- Paste long transcripts
- Repeat the whole repo layout
- Speculate about files not inspected
- Mix user asks with uncertain conclusions

## Translation Rules

Use these rules when building the handoff:

- `summary`: 1 to 3 sentences. State the task status and current understanding.
- `relevant_files`: one line per file, with a short role note after `::`.
- `findings`: concrete conclusions already supported by inspection.
- `constraints`: user constraints, architecture constraints, API stability constraints, testing constraints.
- `next_step`: the single most useful next action for Claude.
- `repo_facts`: stable project facts only.
- `open_questions`: only unresolved questions that materially affect implementation.
- `review_items`: one explicit option/change/checkpoint per line when Claude should compare or review items one by one.

## Option-by-Option Reviews

When asking Claude/Opus to compare multiple plans or review several approved changes, pass each item with `--context-review-item`.

This preserves the list structure in the final handoff and adds an output contract requiring one section per item. Do not hide multiple options only inside a broad prose prompt when item-by-item critique matters.

The wrapper does not infer review items from numbered prose in `--PROMPT`; use `--context-review-item` explicitly when the response must stay item-by-item.

## Recommended Command Pattern

Use `scripts/claude_delegate.py`, not `claude_bridge.py`, unless low-level behavior is required.

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "Short high-confidence summary." \
  --context-file-ref "src/app.ts :: entry point" \
  --context-finding "Observed issue or conclusion." \
  --context-constraint "Constraint that must remain true." \
  --context-review-item "Option A or change 1." \
  --context-review-item "Option B or change 2." \
  --context-next-step "Specific next action for Claude." \
  --PROMPT "Concrete task for Claude"
```

## Preview First When Risky

If the handoff is complex, expensive, or likely to be reused, preview or save it first:

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "..." \
  --context-file-ref "src/app.ts :: entry point" \
  --preview-handoff \
  --PROMPT "preview"
```

Or save it without sending:

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "..." \
  --preview-handoff \
  --save-handoff ".tmp/claude-handoff.txt" \
  --PROMPT "preview"
```

## Resume Behavior

- On the first call, send the structured handoff.
- On `SESSION_ID` resume, do not resend the handoff unless the context materially changed or `--context-on-resume` is needed.
- If new important findings appear, generate a refreshed compact handoff instead of appending a long free-form update.

## Examples

### Code Review Delegation

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "Recent changes affect cancellation flow in gallery polling." \
  --context-file-ref "frontend/src/pages/Gallery/index.tsx :: gallery page polling integration" \
  --context-file-ref "frontend/src/hooks/usePolling.ts :: shared polling state machine" \
  --context-finding "Cancellation can leave stale polling state." \
  --context-constraint "Review only. No code edits." \
  --context-next-step "Audit for race conditions and missing test coverage." \
  --PROMPT "Review the implementation and return only concrete findings."
```

### Implementation Delegation

```bash
python scripts/claude_delegate.py \
  --cd "/project" \
  --context-summary "Model options mismatch is frontend-driven and already localized." \
  --context-file-ref "frontend/src/pages/Practice/index.tsx :: model option selection UI" \
  --context-file-ref "frontend/src/pages/Gallery/index.tsx :: source of supported model choices" \
  --context-finding "Backend types do not block matching the gallery choices." \
  --context-constraint "Keep the existing API payload shape unchanged." \
  --context-next-step "Update the practice page options to match gallery behavior and verify UI state handling." \
  --PROMPT "Implement the minimal patch and summarize the result."
```

## Relationship To Other Skill

- `delegating-with-claude`: high-level workflow with automatic handoff synthesis.
- `collaborating-with-claude`: low-level execution and bridge details.

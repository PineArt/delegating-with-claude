## Step S3. Task Graph

Task | Owner | Context Boundary | Depends On | Outputs | Writable Area | Validation Checkpoint | Fallback
--- | --- | --- | --- | --- | --- | --- | ---
Async delegate job core and explicit subcommands | Implementer | worker agent context for code edits | S1, S2 | updated `scripts/claude_delegate.py` plus helper module if needed | scripts/ | focused async lifecycle unit tests and CLI smoke tests | reduce to a smaller helper if the file becomes too broad
Docs and help text for explicit async semantics | Implementer | worker agent context for code edits | Async delegate job core | updated `README.md` and `SKILL.md` | docs | `python scripts/claude_delegate.py --help` smoke check plus docs grep checks | keep wording minimal and aligned with actual CLI
Harness validation and gate review | Quality Gate | separate Codex gate context | implementation outputs and docs | gate notes and final verdict | exec-plans/active/2026-05-10-async-delegate-jobs | final diff review plus validator output | request rework if a blocking issue remains

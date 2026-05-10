## Decision Log

- 2026-05-10: User requested that we continue with the full harness instead of treating the earlier consensus as enough.
- 2026-05-10: We agreed not to preserve the old no-subcommand invocation because there is no current compatibility need and it muddies the execution model.
- 2026-05-10: The publishable run is organized as an async delegate job refactor with explicit subcommands and main-thread-controlled waiting.
- 2026-05-10: S1-S3 harness artifacts were written and the validator passed at stage s2 and s3 after fixing boundary wording and owner separation.
- 2026-05-10: S4 implementation completed, focused tests passed, and fake async CLI smoke passed without calling the real Claude CLI.
- 2026-05-10: Quality Gate returned Fail because session lock was scan-then-create; S4 rework added an exclusive per-session lock file and increased focused tests from 29 to 31.
- 2026-05-10: Quality Gate returned Pass after the atomic session-lock rework and confirmed the explicit no-subcommand-removal CLI contract can proceed.
- 2026-05-10: Final hardening added resolved background `cd` persistence and startup-failure lock release; two regression tests increased focused coverage to 33 tests.
- 2026-05-10: Final Quality Gate re-gate returned Pass with no blockers; S8 publish can proceed after final validation, commit, and push evidence.
- 2026-05-10: Follow-up added `--effort` passthrough plus async completion notifications through `--notify-file` and `--notify-command`; Opus review returned Pass with no blockers.
- 2026-05-11: User chose to remove the remaining high-level synchronous `run` command because there is no legacy script dependency and it weakens the async-only contract; `scripts/claude_bridge.py` remains available for low-level synchronous diagnostics.

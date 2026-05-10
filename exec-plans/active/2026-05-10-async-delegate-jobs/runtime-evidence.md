## Runtime Evidence Record

State Surface:
Local CLI execution against a fake `claude.cmd` placed at the front of `PATH`.

Starting State:
No prior fake job store; `.tmp-tests/cli-smoke` was recreated for the smoke.

Method:
- Create a temporary fake `claude.cmd` that reads stdin and prints Claude-style JSON with `session_id` and `result`.
- Run `python scripts\claude_delegate.py start --job-store <tmp> --cd . --PROMPT "fake async smoke"`.
- Run `python scripts\claude_delegate.py wait --job-store <tmp> --job-id <id> --timeout 10`.
- Run `python scripts\claude_delegate.py status --job-store <tmp> --job-id <id>`.

Evidence:
- Smoke output: `{"start_state":"starting","wait_state":"succeeded","wait_success":true,"session":"fake-session-1","message":"FAKE_OK","job_id":"77ac47070f684b83bee4438390d0bd28"}`
- Test output before lock rework: `29 passed in 1.84s`.
- Test output after lock rework: `31 passed in 1.69s`.
- Final test output after startup-failure and resolved-`cd` hardening: `33 passed in 1.64s`.
- Diff check output: `git diff --check` completed with only CRLF warnings.
- Harness validator output before final publish: `Harness run validation passed.`

Result:
Pass. The async CLI path works end-to-end without invoking the real Claude CLI, and the atomic session-lock primitive is covered by focused tests.

Residual Risk:
The smoke validates process and JSON plumbing, not long-running real Claude behavior.

Fact / Inference / Open Question:
- Fact: The fake CLI path proved local job persistence and wait/status result extraction.
- Fact: The rework test suite proves same-session lock acquisition fails atomically for the second claimant.
- Fact: The final test suite proves background jobs persist resolved `cd` values and release session locks on startup failure.
- Inference: Real Claude JSON output will be parsed through the same `_extract_result_json` path.
- Open Question: Whether a real long Opus job should be tested before publishing broadly.

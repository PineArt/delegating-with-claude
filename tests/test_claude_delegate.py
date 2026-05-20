from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
DELEGATE_PATH = ROOT / "scripts" / "claude_delegate.py"
JOBS_PATH = ROOT / "scripts" / "claude_jobs.py"


def load_delegate():
    spec = importlib.util.spec_from_file_location("claude_delegate_under_test", DELEGATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_jobs():
    spec = importlib.util.spec_from_file_location("claude_jobs_under_test", JOBS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_temp_dir() -> Path:
    path = ROOT / ".tmp-tests" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def make_args(**overrides):
    values = {
        "PROMPT": "Reply with exactly OK.",
        "context_summary": "",
        "context_file_ref": [],
        "context_finding": [],
        "context_constraint": [],
        "context_repo_fact": [],
        "context_open_question": [],
        "context_review_item": [],
        "context_next_step": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def run_delegate(delegate, monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["claude_delegate.py", *argv])
    delegate.main()
    captured = capsys.readouterr()
    return captured.out


def test_build_handoff_uses_direct_inline_shape():
    delegate = load_delegate()
    handoff = delegate.build_handoff(
        make_args(
            context_summary="sanity check",
            context_file_ref=["scripts/claude_delegate.py :: handoff builder"],
            context_finding=["Bridge call works directly."],
            context_constraint=["No file edits."],
            context_next_step="Return OK.",
        )
    )

    assert handoff.startswith("Please complete this task directly: Reply with exactly OK.")
    assert "Use these handoff notes as the source for your answer:" in handoff
    assert "\nTask:" not in handoff
    assert "\nWorking context:" not in handoff
    assert handoff.endswith("\n")


def test_build_handoff_preserves_explicit_review_items():
    delegate = load_delegate()
    handoff = delegate.build_handoff(
        make_args(
            PROMPT="Review the planned changes only.",
            context_summary="Three implementation choices need targeted critique.",
            context_review_item=[
                "Option A: preserve current refresh flow and add chart toggle.",
                "Option B: move records into the partial before adding the toggle.",
                "Option C: split the views and chart bootstrap logic.",
            ],
            context_constraint=["Do not do broad code review."],
            context_next_step="Assess each option individually.",
        )
    )

    assert "1. Option A: preserve current refresh flow and add chart toggle." in handoff
    assert "2. Option B: move records into the partial before adding the toggle." in handoff
    assert "3. Option C: split the views and chart bootstrap logic." in handoff
    assert "Review only the numbered items below." in handoff
    assert "Reply with one section per numbered item." in handoff
    assert "Use these handoff notes as the source for your answer:" not in handoff


def test_numbered_prompt_without_review_items_uses_inline_shape():
    delegate = load_delegate()
    handoff = delegate.build_handoff(
        make_args(
            PROMPT=(
                "Review these changes only:\n"
                "1. Fix shell F5 restore.\n"
                "2. Add a third billing chart.\n"
                "3. Merge today's usage into the quota panel."
            ),
            context_summary="Three approved fixes need item-by-item review.",
            context_constraint=["Do not inspect unrelated plans."],
        )
    )

    assert handoff.startswith("Please complete this task directly: Review these changes only:")
    assert "Review only the numbered items below." not in handoff
    assert "Reply with one section per numbered item." not in handoff
    assert "Use these handoff notes as the source for your answer:" in handoff


def test_preview_handoff_saves_and_prints_utf8(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        save_path = tmp_dir / "handoff.txt"

        output = run_delegate(
            delegate,
            monkeypatch,
                capsys,
            [
                "start",
                "--cd",
                str(tmp_dir),
                "--context-summary",
                "摘要中文",
                "--preview-handoff",
                "--save-handoff",
                str(save_path),
                "--PROMPT",
                "中文测试",
            ],
        )

        assert output == save_path.read_text(encoding="utf-8")
        assert "中文测试" in output
        assert "摘要中文" in output
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_start_uses_handoff_and_records_prompt(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        monkeypatch.setattr("claude_jobs._spawn_worker", lambda store, job_id, worker_log_path: 4321)

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "start",
                "--cd",
                str(tmp_dir),
                "--job-store",
                str(job_store),
                "--context-summary",
                "sanity check",
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        parsed = json.loads(output)
        assert parsed["success"] is True
        assert parsed["state"] == "starting"
        record = json.loads(Path(parsed["paths"]["record"]).read_text(encoding="utf-8"))
        assert record["handoff_used"] is True
        assert Path(record["paths"]["prompt"]).read_text(encoding="utf-8").startswith("Please complete this task directly:")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_run_subcommand_is_removed(monkeypatch, capsys):
    delegate = load_delegate()
    monkeypatch.setattr(sys, "argv", ["claude_delegate.py", "run", "--help"])

    try:
        delegate.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Expected removed run subcommand to fail")

    captured = capsys.readouterr()
    assert "invalid choice: 'run'" in captured.err
    assert "start" in captured.err


def test_resume_without_context_on_resume_stores_raw_prompt(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        monkeypatch.setattr("claude_jobs._spawn_worker", lambda store, job_id, worker_log_path: 4321)

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "resume",
                "--cd",
                str(tmp_dir),
                "--job-store",
                str(job_store),
                "--SESSION_ID",
                "session-1",
                "--context-summary",
                "sanity check",
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        parsed = json.loads(output)
        assert parsed["success"] is True
        record = json.loads(Path(parsed["paths"]["record"]).read_text(encoding="utf-8"))
        assert record["handoff_used"] is False
        assert Path(record["paths"]["prompt"]).read_text(encoding="utf-8") == "Reply with exactly OK."
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_no_subcommand_is_rejected_with_migration_hint(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "claude_delegate.py",
                "--cd",
                str(tmp_dir),
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        try:
            delegate.main()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("Expected no-subcommand usage to fail")

        captured = capsys.readouterr()
        assert "Use `start/status/wait/stop/resume` for async jobs" in captured.err
        assert "claude_bridge.py" in captured.err
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_top_level_help_still_works(monkeypatch, capsys):
    delegate = load_delegate()
    monkeypatch.setattr(sys, "argv", ["claude_delegate.py", "--help"])

    try:
        delegate.main()
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("Expected argparse help to exit")

    captured = capsys.readouterr()
    assert "start" in captured.out
    assert "status" in captured.out
    assert "claude_bridge.py" in captured.out
    assert "{start,resume,status,wait,stop}" in captured.out
    assert "{run" not in captured.out
    assert ",run" not in captured.out
    assert "run}" not in captured.out


def test_delegate_subcommands_do_not_expose_timeout_seconds(monkeypatch, capsys):
    delegate = load_delegate()
    for subcommand in ("start", "resume"):
        monkeypatch.setattr(sys, "argv", ["claude_delegate.py", subcommand, "--help"])
        try:
            delegate.main()
        except SystemExit as error:
            assert error.code == 0
        else:
            raise AssertionError(f"Expected {subcommand} help to exit")
        help_text = capsys.readouterr().out
        assert "--timeout-seconds" not in help_text


def test_start_rejects_timeout_seconds(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "claude_delegate.py",
                "start",
                "--cd",
                str(tmp_dir),
                "--timeout-seconds",
                "900",
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        try:
            delegate.main()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("Expected start --timeout-seconds to fail")

        assert "unrecognized arguments: --timeout-seconds 900" in capsys.readouterr().err
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_resume_rejects_timeout_seconds(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "claude_delegate.py",
                "resume",
                "--cd",
                str(tmp_dir),
                "--SESSION_ID",
                "session-1",
                "--timeout-seconds",
                "900",
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        try:
            delegate.main()
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("Expected resume --timeout-seconds to fail")

        assert "unrecognized arguments: --timeout-seconds 900" in capsys.readouterr().err
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_start_writes_record_and_returns_metadata_without_real_claude(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        spawned = []

        def fake_spawn_worker(store, job_id, worker_log_path):
            spawned.append({"store": store, "job_id": job_id, "worker_log_path": worker_log_path})
            return 4321

        monkeypatch.setattr(delegate, "start_job", delegate.start_job)
        monkeypatch.setattr("claude_jobs._spawn_worker", fake_spawn_worker)

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "start",
                "--cd",
                str(tmp_dir),
                "--job-store",
                str(job_store),
                "--context-summary",
                "async start test",
                "--model",
                "opus",
                "--effort",
                "xhigh",
                "--notify-file",
                str(tmp_dir / "notify.json"),
                "--notify-command",
                json.dumps([sys.executable, "-c", "import sys; sys.stdin.read()"]),
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        parsed = json.loads(output)
        job_id = parsed["job_id"]
        assert parsed["success"] is True
        assert parsed["state"] == "starting"
        assert spawned == [{"store": job_store.resolve(), "job_id": job_id, "worker_log_path": Path(parsed["paths"]["worker_log"])}]

        record_path = Path(parsed["paths"]["record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["job_id"] == job_id
        assert record["worker_pid"] == 4321
        assert record["options"]["model"] == "opus"
        assert record["options"]["effort"] == "xhigh"
        assert record["notify_file"] == str((tmp_dir / "notify.json").resolve())
        assert json.loads(record["notify_command"])[0] == sys.executable
        assert "timeout_seconds" not in record["options"]
        assert Path(record["paths"]["prompt"]).read_text(encoding="utf-8").startswith("Please complete this task directly:")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_start_stores_resolved_cd_for_background_worker(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        monkeypatch.chdir(tmp_dir)
        monkeypatch.setattr("claude_jobs._spawn_worker", lambda store, job_id, worker_log_path: 4321)

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "start",
                "--cd",
                ".",
                "--job-store",
                str(job_store),
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        parsed = json.loads(output)
        record = json.loads(Path(parsed["paths"]["record"]).read_text(encoding="utf-8"))
        assert record["cd"] == str(tmp_dir.resolve())
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_wait_timeout_returns_without_killing(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-running"
        jobs.write_record(
            job_store,
            job_id,
            {
                "job_id": job_id,
                "state": "running",
                "paths": {"record": str(job_store / job_id / "record.json")},
            },
        )
        killed = []
        monkeypatch.setattr(jobs, "_terminate_pid", lambda pid: killed.append(pid))

        result = jobs.wait_job(job_store, job_id, timeout_seconds=0.01, poll_interval=0.01)

        assert result["timed_out"] is True
        assert result["state"] == "running"
        assert killed == []
        assert jobs.read_record(job_store, job_id)["state"] == "running"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_stop_is_explicit_kill_path(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-running"
        jobs.write_record(
            job_store,
            job_id,
            {
                "job_id": job_id,
                "state": "running",
                "child_pid": 12345,
                "worker_pid": 67890,
                "paths": {"record": str(job_store / job_id / "record.json")},
            },
        )
        killed = []
        monkeypatch.setattr(jobs, "_terminate_pid", lambda pid: killed.append(pid))

        result = jobs.stop_job(job_store, job_id)

        assert killed == [12345]
        assert result["state"] == "stopped"
        assert result["success"] is False
        assert result["stop_requested"] is True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_status_reads_local_records_only(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-local"
        record_dir = job_store / job_id
        record_dir.mkdir(parents=True)
        (record_dir / "record.json").write_text(
            json.dumps({"job_id": job_id, "state": "running", "created_at": "2026-05-10T00:00:00Z"}),
            encoding="utf-8",
        )

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "status",
                "--job-store",
                str(job_store),
                "--job-id",
                job_id,
            ],
        )

        parsed = json.loads(output)
        assert parsed["job_id"] == job_id
        assert parsed["state"] == "running"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_status_accepts_positional_job_id(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-local"
        record_dir = job_store / job_id
        record_dir.mkdir(parents=True)
        (record_dir / "record.json").write_text(
            json.dumps({"job_id": job_id, "state": "running", "created_at": "2026-05-10T00:00:00Z"}),
            encoding="utf-8",
        )

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "status",
                "--job-store",
                str(job_store),
                job_id,
            ],
        )

        parsed = json.loads(output)
        assert parsed["job_id"] == job_id
        assert parsed["state"] == "running"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_wait_accepts_positional_job_id(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-done"
        record_dir = job_store / job_id
        record_dir.mkdir(parents=True)
        (record_dir / "record.json").write_text(
            json.dumps({"job_id": job_id, "state": "succeeded", "success": True}),
            encoding="utf-8",
        )

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "wait",
                "--job-store",
                str(job_store),
                job_id,
                "--timeout",
                "0.01",
            ],
        )

        parsed = json.loads(output)
        assert parsed["job_id"] == job_id
        assert parsed["state"] == "succeeded"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_stop_accepts_positional_job_id(monkeypatch, capsys):
    delegate = load_delegate()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-running"
        record_dir = job_store / job_id
        record_dir.mkdir(parents=True)
        (record_dir / "record.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "running",
                    "success": False,
                    "paths": {"record": str(record_dir / "record.json")},
                }
            ),
            encoding="utf-8",
        )

        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "stop",
                "--job-store",
                str(job_store),
                job_id,
            ],
        )

        parsed = json.loads(output)
        assert parsed["job_id"] == job_id
        assert parsed["state"] == "stopped"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_conflicting_positional_and_flagged_job_id_is_rejected(monkeypatch, capsys):
    delegate = load_delegate()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claude_delegate.py",
            "wait",
            "job-a",
            "--job-id",
            "job-b",
        ],
    )

    try:
        delegate.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Expected conflicting job ids to fail")

    assert "job id specified twice with different values" in capsys.readouterr().err


def test_status_does_not_refresh_or_mutate_stale_records(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-stale"
        jobs.write_record(
            job_store,
            job_id,
            {
                "job_id": job_id,
                "state": "running",
                "worker_pid": 999999,
                "paths": {"record": str(job_store / job_id / "record.json")},
            },
        )
        monkeypatch.setattr(jobs, "_pid_alive", lambda pid: False)

        status = jobs.local_status(job_store, job_id)
        record = jobs.read_record(job_store, job_id, refresh_stale=False)

        assert status["state"] == "running"
        assert "stale_detected" not in status
        assert record["state"] == "running"
        assert "stale_detected" not in record
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_resume_refuses_same_session_running_job():
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        jobs.write_record(
            job_store,
            "job-1",
            {
                "job_id": "job-1",
                "state": "running",
                "requested_SESSION_ID": "session-1",
            },
        )

        try:
            jobs.ensure_session_available(job_store, "session-1")
        except RuntimeError as error:
            assert "already has a running delegate job" in str(error)
        else:
            raise AssertionError("Expected same-session running job to be rejected")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_session_lock_acquisition_is_atomic():
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        first_lock = jobs.acquire_session_lock(job_store, "session-1", "job-1")
        assert first_lock is not None
        assert first_lock.is_file()

        try:
            jobs.acquire_session_lock(job_store, "session-1", "job-2")
        except RuntimeError as error:
            assert "already has a running delegate job: job-1" in str(error)
        else:
            raise AssertionError("Expected second same-session lock acquisition to fail")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_terminal_session_lock_can_be_reclaimed():
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        jobs.acquire_session_lock(job_store, "session-1", "job-1")
        jobs.write_record(
            job_store,
            "job-1",
            {
                "job_id": "job-1",
                "state": "succeeded",
                "requested_SESSION_ID": "session-1",
            },
        )

        lock = jobs.acquire_session_lock(job_store, "session-1", "job-2")
        payload = json.loads(lock.read_text(encoding="utf-8"))

        assert payload["job_id"] == "job-2"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_resume_allows_stale_same_session_job(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        jobs.write_record(
            job_store,
            "job-1",
            {
                "job_id": "job-1",
                "state": "running",
                "worker_pid": 999999,
                "requested_SESSION_ID": "session-1",
                "paths": {"record": str(job_store / "job-1" / "record.json")},
            },
        )
        monkeypatch.setattr(jobs, "_pid_alive", lambda pid: False)

        jobs.ensure_session_available(job_store, "session-1")
        refreshed = jobs.read_record(job_store, "job-1", refresh_stale=False)

        assert refreshed["state"] == "failed"
        assert refreshed["stale_detected"] is True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_worker_launch_failure_releases_session_lock(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-launch-failure"
        session_id = "session-1"
        paths = {
            "record": str(job_store / job_id / "record.json"),
            "prompt": str(job_store / job_id / "prompt.txt"),
            "handoff": str(job_store / job_id / "handoff.txt"),
            "stdout": str(job_store / job_id / "stdout.txt"),
            "stderr": str(job_store / job_id / "stderr.txt"),
        }
        jobs.acquire_session_lock(job_store, session_id, job_id)
        Path(paths["prompt"]).parent.mkdir(parents=True, exist_ok=True)
        Path(paths["prompt"]).write_text("prompt", encoding="utf-8")
        jobs.write_record(
            job_store,
            job_id,
            {
                "job_id": job_id,
                "state": "starting",
                "cd": str(tmp_dir),
                "requested_SESSION_ID": session_id,
                "SESSION_ID": "",
                "paths": paths,
                "options": {
                    "permission_mode": "bypassPermissions",
                    "add_dir": [],
                    "model": "",
                    "effort": "",
                    "return_raw_result": False,
                },
            },
        )
        monkeypatch.setattr(jobs, "_build_command", lambda args: ["missing-claude"])
        monkeypatch.setattr(jobs, "_resolve_executable", lambda name, env: (_ for _ in ()).throw(FileNotFoundError(name)))

        jobs.run_worker(job_store, job_id)

        record = jobs.read_record(job_store, job_id, refresh_stale=False)
        assert record["state"] == "failed"
        assert not jobs.session_lock_path(job_store, session_id).exists()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_completion_notification_writes_file_and_runs_hook(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        notify_file = tmp_dir / "notify.json"
        hook_inputs = []
        job_id = "job-notify"
        record = {
            "job_id": job_id,
            "state": "succeeded",
            "success": True,
            "SESSION_ID": "session-1",
            "requested_SESSION_ID": "",
            "agent_messages": "OK",
            "finished_at": "2026-05-10T00:00:00Z",
            "notify_file": str(notify_file),
            "notify_command": json.dumps(["notify-tool"]),
            "notify_timeout_seconds": 5,
            "paths": {"record": str(job_store / job_id / "record.json")},
            "options": {"model": "opus", "effort": "high"},
        }
        jobs.write_record(job_store, job_id, record)

        def fake_run(command, **kwargs):
            hook_inputs.append({"command": command, "payload": json.loads(kwargs["input"]), "timeout": kwargs["timeout"]})
            return jobs.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        monkeypatch.setattr(jobs.subprocess, "run", fake_run)

        jobs._emit_completion_notification(job_store, job_id, record)
        jobs._emit_completion_notification(job_store, job_id, jobs.read_record(job_store, job_id, refresh_stale=False))

        file_payload = json.loads(notify_file.read_text(encoding="utf-8"))
        refreshed = jobs.read_record(job_store, job_id, refresh_stale=False)
        assert file_payload["job_id"] == job_id
        assert file_payload["agent_messages"] == "OK"
        assert file_payload["options"]["effort"] == "high"
        assert hook_inputs == [{"command": ["notify-tool"], "payload": file_payload, "timeout": 5}]
        assert "notification_sent_at" in refreshed
        assert "notification_errors" not in refreshed
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_completion_notification_records_hook_errors(monkeypatch):
    jobs = load_jobs()
    tmp_dir = make_temp_dir()
    try:
        job_store = tmp_dir / "jobs"
        job_id = "job-notify-failure"
        record = {
            "job_id": job_id,
            "state": "failed",
            "success": False,
            "error": "delegate failed",
            "notify_command": json.dumps(["notify-tool"]),
            "notify_timeout_seconds": 5,
            "paths": {"record": str(job_store / job_id / "record.json")},
            "options": {},
        }
        jobs.write_record(job_store, job_id, record)

        def fake_run(command, **kwargs):
            return jobs.subprocess.CompletedProcess(command, 2, stdout="", stderr="hook failed")

        monkeypatch.setattr(jobs.subprocess, "run", fake_run)

        jobs._emit_completion_notification(job_store, job_id, record)

        refreshed = jobs.read_record(job_store, job_id, refresh_stale=False)
        assert "notification_sent_at" in refreshed
        assert refreshed["notification_errors"] == ["notify_command exit 2: hook failed"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

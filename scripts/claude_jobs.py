"""Local async job primitives for claude_delegate.py."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from claude_bridge import (
    _augment_path_env,
    _build_command,
    _extract_result_json,
    _resolve_executable,
    _rewrite_npm_wrapper,
)

DEFAULT_JOB_STORE = SCRIPT_DIR.parent / ".claude-delegate-jobs"
TERMINAL_STATES = {"succeeded", "failed", "stopped"}
ACTIVE_STATES = {"queued", "starting", "running", "stopping"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_job_store(value: str = "") -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_JOB_STORE


def job_dir(job_store: Path, job_id: str) -> Path:
    return job_store / job_id


def record_path(job_store: Path, job_id: str) -> Path:
    return job_dir(job_store, job_id) / "record.json"


def lock_dir(job_store: Path) -> Path:
    return job_store / "locks"


def session_lock_path(job_store: Path, session_id: str) -> Path:
    digest = sha256(session_id.encode("utf-8")).hexdigest()
    return lock_dir(job_store) / f"session-{digest}.lock"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def write_record(job_store: Path, job_id: str, record: Dict[str, Any]) -> None:
    record = dict(record)
    record["updated_at"] = utc_now()
    _atomic_write_text(record_path(job_store, job_id), json.dumps(record, ensure_ascii=False, indent=2))


def _notification_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": record.get("job_id", ""),
        "state": record.get("state", ""),
        "success": bool(record.get("success", False)),
        "SESSION_ID": record.get("SESSION_ID", ""),
        "requested_SESSION_ID": record.get("requested_SESSION_ID", ""),
        "agent_messages": record.get("agent_messages", ""),
        "error": record.get("error", ""),
        "paths": record.get("paths", {}),
        "finished_at": record.get("finished_at") or record.get("stopped_at", ""),
        "options": record.get("options", {}),
    }


def _parse_notify_command(value: str) -> List[str]:
    stripped = value.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return shlex.split(stripped, posix=os.name != "nt")
    if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item for item in parsed):
        raise ValueError("--notify-command JSON form must be a non-empty string array")
    return parsed


def _emit_completion_notification(job_store: Path, job_id: str, record: Dict[str, Any]) -> None:
    if record.get("notification_sent_at"):
        return
    notify_file = str(record.get("notify_file", ""))
    notify_command = str(record.get("notify_command", ""))
    if not notify_file and not notify_command:
        return

    payload = _notification_payload(record)
    notification_errors: List[str] = []
    if notify_file:
        try:
            _atomic_write_text(Path(notify_file).expanduser(), json.dumps(payload, ensure_ascii=False, indent=2))
        except OSError as error:
            notification_errors.append(f"notify_file failed: {error}")

    if notify_command:
        try:
            command = _parse_notify_command(notify_command)
            if command:
                completed = subprocess.run(
                    command,
                    input=json.dumps(payload, ensure_ascii=False),
                    cwd=record.get("cd") or None,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                    timeout=int(record.get("notify_timeout_seconds") or 30),
                )
                if completed.returncode != 0:
                    notification_errors.append(f"notify_command exit {completed.returncode}: {completed.stderr.strip()}")
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            notification_errors.append(f"notify_command failed: {error}")

    updated = read_record(job_store, job_id, refresh_stale=False)
    updated["notification_sent_at"] = utc_now()
    if notification_errors:
        updated["notification_errors"] = notification_errors
    else:
        updated.pop("notification_errors", None)
    write_record(job_store, job_id, updated)


def _read_record_file(job_store: Path, job_id: str) -> Dict[str, Any]:
    path = record_path(job_store, job_id)
    if not path.is_file():
        raise FileNotFoundError(f"Unknown delegate job: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_record(job_store: Path, job_id: str, *, refresh_stale: bool = True) -> Dict[str, Any]:
    record = _read_record_file(job_store, job_id)
    if not refresh_stale:
        return record
    return _refresh_record_if_stale(job_store, job_id, record)


def list_records(job_store: Path, *, refresh_stale: bool = True) -> List[Dict[str, Any]]:
    if not job_store.is_dir():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(job_store.glob("*/record.json")):
        try:
            job_id = path.parent.name
            records.append(read_record(job_store, job_id, refresh_stale=refresh_stale))
        except (OSError, json.JSONDecodeError):
            continue
    records.sort(key=lambda item: item.get("created_at", ""))
    return records


def local_status(job_store: Path, job_id: str = "") -> Dict[str, Any]:
    if job_id:
        return read_record(job_store, job_id, refresh_stale=False)
    return {"jobs": list_records(job_store, refresh_stale=False)}


def _job_paths(job_store: Path, job_id: str) -> Dict[str, str]:
    directory = job_dir(job_store, job_id)
    return {
        "job_dir": str(directory),
        "record": str(directory / "record.json"),
        "prompt": str(directory / "prompt.txt"),
        "handoff": str(directory / "handoff.txt"),
        "stdout": str(directory / "stdout.txt"),
        "stderr": str(directory / "stderr.txt"),
        "worker_log": str(directory / "worker.log"),
    }


def _running_records_for_session(job_store: Path, session_id: str) -> List[Dict[str, Any]]:
    if not session_id:
        return []
    matches: List[Dict[str, Any]] = []
    for record in list_records(job_store, refresh_stale=True):
        if record.get("state") in TERMINAL_STATES:
            continue
        if session_id in {record.get("SESSION_ID"), record.get("requested_SESSION_ID")}:
            matches.append(record)
    return matches


def ensure_session_available(job_store: Path, session_id: str) -> None:
    matches = _running_records_for_session(job_store, session_id)
    if matches:
        job_ids = ", ".join(str(record.get("job_id", "")) for record in matches)
        raise RuntimeError(f"SESSION_ID {session_id!r} already has a running delegate job: {job_ids}")


def _read_lock(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _lock_blocks_session(job_store: Path, path: Path, session_id: str) -> bool:
    lock = _read_lock(path)
    job_id = str(lock.get("job_id", ""))
    if not job_id:
        return True
    try:
        record = read_record(job_store, job_id, refresh_stale=True)
    except FileNotFoundError:
        return True
    if record.get("state") in TERMINAL_STATES:
        path.unlink(missing_ok=True)
        return False
    if session_id in {record.get("SESSION_ID"), record.get("requested_SESSION_ID")}:
        return True
    return True


def acquire_session_lock(job_store: Path, session_id: str, job_id: str) -> Optional[Path]:
    if not session_id:
        return None
    lock_path = session_lock_path(job_store, session_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "job_id": job_id,
        "created_at": utc_now(),
    }
    while True:
        try:
            with lock_path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            return lock_path
        except FileExistsError:
            if _lock_blocks_session(job_store, lock_path, session_id):
                lock = _read_lock(lock_path)
                blocker = lock.get("job_id", "unknown")
                raise RuntimeError(f"SESSION_ID {session_id!r} already has a running delegate job: {blocker}")


def release_session_lock(job_store: Path, session_id: str, job_id: str) -> None:
    if not session_id:
        return
    path = session_lock_path(job_store, session_id)
    lock = _read_lock(path)
    if lock.get("job_id") == job_id:
        path.unlink(missing_ok=True)


def _spawn_worker(job_store: Path, job_id: str, worker_log_path: Path) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        "--job-store",
        str(job_store),
        "--job-id",
        job_id,
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    worker_log_path.parent.mkdir(parents=True, exist_ok=True)
    worker_log = worker_log_path.open("a", encoding="utf-8", errors="replace")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(SCRIPT_DIR.parent),
            stdin=subprocess.DEVNULL,
            stdout=worker_log,
            stderr=worker_log,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            close_fds=True,
        )
    finally:
        worker_log.close()
    return int(process.pid)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = result.stdout.strip()
    return bool(stdout and "No tasks are running" not in stdout and str(pid) in stdout)


def _record_has_live_process(record: Dict[str, Any]) -> bool:
    if record.get("state") in TERMINAL_STATES:
        return False
    for key in ("worker_pid", "child_pid"):
        try:
            pid = int(record.get(key) or 0)
        except (TypeError, ValueError):
            pid = 0
        if _pid_alive(pid):
            return True
    return False


def _refresh_record_if_stale(job_store: Path, job_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    if record.get("state") not in ACTIVE_STATES:
        return record
    if not any(record.get(key) for key in ("worker_pid", "child_pid")):
        return record
    if _record_has_live_process(record):
        return record

    stale_record = dict(record)
    stale_record["finished_at"] = stale_record.get("finished_at") or utc_now()
    stale_record["stale_detected"] = True
    if stale_record.get("stop_requested"):
        stale_record.update(
            {
                "state": "stopped",
                "success": False,
                "error": "Delegate job stopped or lost before a clean shutdown completed.",
            }
        )
    else:
        stale_record.update(
            {
                "state": "failed",
                "success": False,
                "error": "Delegate job record is stale; no live process was found.",
            }
        )
    write_record(job_store, job_id, stale_record)
    release_session_lock(job_store, stale_record.get("requested_SESSION_ID", ""), job_id)
    release_session_lock(job_store, stale_record.get("SESSION_ID", ""), job_id)
    final_record = json.loads(record_path(job_store, job_id).read_text(encoding="utf-8"))
    _emit_completion_notification(job_store, job_id, final_record)
    return read_record(job_store, job_id, refresh_stale=False)


@contextmanager
def _session_lock_for_job(job_store: Path, session_id: str, job_id: str):
    acquired = acquire_session_lock(job_store, session_id, job_id)
    try:
        yield acquired
    except Exception:
        release_session_lock(job_store, session_id, job_id)
        raise


def start_job(
    args: argparse.Namespace,
    prompt_to_send: str,
    handoff: str,
    *,
    require_session_lock: bool = False,
) -> Dict[str, Any]:
    job_store = stable_job_store(getattr(args, "job_store", ""))
    requested_session_id = getattr(args, "SESSION_ID", "")
    job_id = uuid.uuid4().hex
    directory = job_dir(job_store, job_id)
    paths = _job_paths(job_store, job_id)
    should_lock = require_session_lock or bool(requested_session_id)
    with _session_lock_for_job(job_store, requested_session_id if should_lock else "", job_id):
        if should_lock:
            ensure_session_available(job_store, requested_session_id)
        directory.mkdir(parents=True, exist_ok=False)
        Path(paths["prompt"]).write_text(prompt_to_send, encoding="utf-8")
        Path(paths["handoff"]).write_text(handoff, encoding="utf-8")

        now = utc_now()
        record: Dict[str, Any] = {
            "job_id": job_id,
            "state": "queued",
            "created_at": now,
            "updated_at": now,
            "cd": str(Path(args.cd).expanduser().resolve()),
            "requested_SESSION_ID": requested_session_id,
            "SESSION_ID": "",
            "handoff_used": bool(getattr(args, "handoff_used", False)),
            "notify_file": str(Path(args.notify_file).expanduser().resolve()) if getattr(args, "notify_file", "") else "",
            "notify_command": getattr(args, "notify_command", ""),
            "notify_timeout_seconds": int(getattr(args, "notify_timeout_seconds", 30) or 30),
            "paths": paths,
            "options": {
                "permission_mode": args.permission_mode,
                "add_dir": list(args.add_dir),
                "model": args.model,
                "effort": args.effort or "",
                "return_raw_result": bool(args.return_raw_result),
            },
        }
        write_record(job_store, job_id, record)

        worker_pid = _spawn_worker(job_store, job_id, Path(paths["worker_log"]))
        record = read_record(job_store, job_id, refresh_stale=False)
        record["worker_pid"] = worker_pid
        record["state"] = "starting"
        write_record(job_store, job_id, record)
        return read_record(job_store, job_id, refresh_stale=False)


def _build_error(stdout: str, stderr: str, parsed: Optional[Dict[str, Any]], returncode: int) -> str:
    parts: List[str] = []
    if parsed:
        if parsed.get("result"):
            parts.append(str(parsed.get("result")))
        if parsed.get("message"):
            parts.append(str(parsed.get("message")))
    if stdout.strip():
        parts.append(stdout.strip())
    if stderr.strip():
        parts.append(stderr.strip())
    if returncode != 0:
        parts.append(f"Claude exit code: {returncode}")
    return "\n\n".join(part for part in parts if part).strip() or "Unknown Claude job failure."


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)
        return
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return


def stop_job(job_store: Path, job_id: str) -> Dict[str, Any]:
    record = read_record(job_store, job_id, refresh_stale=False)
    if record.get("state") in TERMINAL_STATES:
        return record

    record["stop_requested"] = True
    record["state"] = "stopping"
    write_record(job_store, job_id, record)

    child_pid = int(record.get("child_pid") or 0)
    worker_pid = int(record.get("worker_pid") or 0)
    _terminate_pid(child_pid or worker_pid)

    record = read_record(job_store, job_id)
    if record.get("state") not in TERMINAL_STATES:
        record["state"] = "stopped"
        record["stopped_at"] = utc_now()
        record["success"] = False
        record["error"] = "Delegate job stopped by explicit stop command."
        write_record(job_store, job_id, record)
    final_record = read_record(job_store, job_id)
    release_session_lock(job_store, final_record.get("requested_SESSION_ID", ""), job_id)
    release_session_lock(job_store, final_record.get("SESSION_ID", ""), job_id)
    _emit_completion_notification(job_store, job_id, final_record)
    return read_record(job_store, job_id)


def wait_job(job_store: Path, job_id: str, timeout_seconds: Optional[float], poll_interval: float) -> Dict[str, Any]:
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    while True:
        record = read_record(job_store, job_id)
        if record.get("state") in TERMINAL_STATES:
            return record
        if deadline is not None and time.monotonic() >= deadline:
            return {
                "success": False,
                "timed_out": True,
                "job_id": job_id,
                "state": record.get("state", "unknown"),
                "message": "Wait timed out; job is still running. Use stop to terminate it.",
                "paths": record.get("paths", {}),
            }
        time.sleep(max(0.05, poll_interval))


def _worker_update(job_store: Path, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    record = read_record(job_store, job_id)
    record.update(updates)
    write_record(job_store, job_id, record)
    return record


def run_worker(job_store: Path, job_id: str) -> None:
    record = read_record(job_store, job_id)
    paths = record["paths"]
    options = record["options"]
    prompt = Path(paths["prompt"]).read_text(encoding="utf-8")

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    _augment_path_env(env)

    stdout_path = Path(paths["stdout"])
    stderr_path = Path(paths["stderr"])
    try:
        bridge_args = SimpleNamespace(
            permission_mode=options["permission_mode"],
            SESSION_ID=record.get("requested_SESSION_ID", ""),
            add_dir=options["add_dir"],
            model=options["model"],
            effort=options.get("effort", ""),
            system_prompt="",
            append_system_prompt="",
        )
        command = _build_command(bridge_args)
        command[0] = _resolve_executable(command[0], env)
        command = _rewrite_npm_wrapper(command, env)
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file:
            with stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
                process = subprocess.Popen(
                    command,
                    cwd=record["cd"],
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                )
                _worker_update(
                    job_store,
                    job_id,
                    {
                        "state": "running",
                        "child_pid": int(process.pid),
                        "command": command,
                        "started_at": utc_now(),
                    },
                )
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.flush()
                process.stdin.close()
                returncode = process.wait()
    except FileNotFoundError as error:
        _worker_update(
            job_store,
            job_id,
            {"state": "failed", "success": False, "error": f"Claude executable not found: {error}"},
        )
        record = read_record(job_store, job_id, refresh_stale=False)
        release_session_lock(job_store, record.get("requested_SESSION_ID", ""), job_id)
        release_session_lock(job_store, record.get("SESSION_ID", ""), job_id)
        _emit_completion_notification(job_store, job_id, record)
        return
    except OSError as error:
        _worker_update(
            job_store,
            job_id,
            {"state": "failed", "success": False, "error": f"Failed to launch Claude: {error}"},
        )
        record = read_record(job_store, job_id, refresh_stale=False)
        release_session_lock(job_store, record.get("requested_SESSION_ID", ""), job_id)
        release_session_lock(job_store, record.get("SESSION_ID", ""), job_id)
        _emit_completion_notification(job_store, job_id, record)
        return

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    parsed = _extract_result_json(stdout)
    record = read_record(job_store, job_id)
    stopped = bool(record.get("stop_requested"))
    success = returncode == 0 and isinstance(parsed, dict) and not parsed.get("is_error", False)

    updates: Dict[str, Any] = {
        "returncode": returncode,
        "finished_at": utc_now(),
    }
    if isinstance(parsed, dict) and parsed.get("session_id"):
        updates["SESSION_ID"] = parsed.get("session_id")
    if stopped:
        updates.update(
            {
                "state": "stopped",
                "success": False,
                "error": "Delegate job stopped by explicit stop command.",
            }
        )
    elif success:
        updates.update(
            {
                "state": "succeeded",
                "success": True,
                "agent_messages": parsed.get("result", ""),
            }
        )
        if options.get("return_raw_result"):
            updates["raw_result"] = parsed
    else:
        updates.update(
            {
                "state": "failed",
                "success": False,
                "error": _build_error(stdout, stderr, parsed, returncode),
            }
        )
        if isinstance(parsed, dict) and options.get("return_raw_result"):
            updates["raw_result"] = parsed
    _worker_update(job_store, job_id, updates)
    final_record = read_record(job_store, job_id)
    release_session_lock(job_store, final_record.get("requested_SESSION_ID", ""), job_id)
    release_session_lock(job_store, final_record.get("SESSION_ID", ""), job_id)
    _emit_completion_notification(job_store, job_id, final_record)


def _build_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Internal Claude delegate job worker")
    parser.add_argument("command", choices=["_worker"])
    parser.add_argument("--job-store", required=True)
    parser.add_argument("--job-id", required=True)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = _build_worker_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_worker(stable_job_store(args.job_store), args.job_id)


if __name__ == "__main__":
    main()

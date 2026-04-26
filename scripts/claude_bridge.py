"""
Claude bridge script for Codex skills.
Wraps the Claude CLI and normalizes its response into a small JSON envelope.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def _get_windows_npm_paths() -> List[Path]:
    if os.name != "nt":
        return []

    env = os.environ
    candidates: List[Path] = []
    if prefix := env.get("NPM_CONFIG_PREFIX") or env.get("npm_config_prefix"):
        candidates.append(Path(prefix))
    if appdata := env.get("APPDATA"):
        candidates.append(Path(appdata) / "npm")
    if localappdata := env.get("LOCALAPPDATA"):
        candidates.append(Path(localappdata) / "npm")
    if programfiles := env.get("ProgramFiles"):
        candidates.append(Path(programfiles) / "nodejs")
    return candidates


def _augment_path_env(env: Dict[str, str]) -> None:
    if os.name != "nt":
        return

    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
    entries = [entry for entry in env.get(path_key, "").split(os.pathsep) if entry]
    lower_entries = {entry.lower() for entry in entries}

    for candidate in _get_windows_npm_paths():
        candidate_str = str(candidate)
        if candidate.is_dir() and candidate_str.lower() not in lower_entries:
            entries.insert(0, candidate_str)
            lower_entries.add(candidate_str.lower())

    env[path_key] = os.pathsep.join(entries)


def _resolve_executable(name: str, env: Dict[str, str]) -> str:
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return name

    path_key = next((key for key in env if key.upper() == "PATH"), "PATH")
    path_val = env.get(path_key, "")
    if resolved := shutil.which(name, path=path_val):
        return resolved

    if os.name == "nt":
        for base in _get_windows_npm_paths():
            for ext in (".cmd", ".bat", ".exe", ".com", ".ps1"):
                candidate = base / f"{name}{ext}"
                if candidate.is_file():
                    return str(candidate)

    return name


def _rewrite_npm_wrapper(command: List[str], env: Dict[str, str]) -> List[str]:
    executable = Path(command[0])
    if os.name != "nt" or executable.suffix.lower() not in {".cmd", ".bat"}:
        return command

    npm_dir = executable.parent
    cli_js = npm_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    if not cli_js.is_file():
        return command

    node_path = npm_dir / "node.exe"
    if not node_path.is_file():
        node_resolved = shutil.which("node", path=env.get(next((key for key in env if key.upper() == "PATH"), "PATH"), ""))
        if not node_resolved:
            return command
        node_path = Path(node_resolved)

    return [str(node_path), str(cli_js), *command[1:]]


def _extract_result_json(stdout: str) -> Optional[Dict[str, Any]]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _build_command(args: argparse.Namespace) -> List[str]:
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        args.permission_mode,
    ]

    if args.SESSION_ID:
        command.extend(["-r", args.SESSION_ID])

    for add_dir in args.add_dir:
        command.extend(["--add-dir", add_dir])

    if args.model:
        command.extend(["--model", args.model])

    if args.system_prompt:
        command.extend(["--system-prompt", args.system_prompt])

    if args.append_system_prompt:
        command.extend(["--append-system-prompt", args.append_system_prompt])

    command.append(args.PROMPT)
    return command


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claude Bridge")
    parser.add_argument("--PROMPT", required=True, help="Instruction for the task to send to Claude.")
    parser.add_argument("--cd", required=True, help="Workspace root for the Claude session.")
    parser.add_argument("--SESSION_ID", default="", help="Resume the specified Claude session.")
    parser.add_argument(
        "--permission-mode",
        default="bypassPermissions",
        choices=["acceptEdits", "bypassPermissions", "default", "dontAsk", "plan", "auto"],
        help="Claude permission mode. Defaults to `bypassPermissions` for automation.",
    )
    parser.add_argument(
        "--add-dir",
        action="append",
        default=[],
        help="Additional directories to allow tool access to. Repeat for multiple directories.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Claude model override. Only set this when explicitly requested by the user.",
    )
    parser.add_argument(
        "--system-prompt",
        default="",
        help="System prompt override. Only set this when explicitly requested by the user.",
    )
    parser.add_argument(
        "--append-system-prompt",
        default="",
        help="Additional system prompt text to append.",
    )
    parser.add_argument(
        "--return-raw-result",
        action="store_true",
        help="Include Claude's raw JSON result payload in the output.",
    )
    return parser


def run_claude(args: argparse.Namespace) -> Dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    _augment_path_env(env)

    command = _build_command(args)
    command[0] = _resolve_executable(command[0], env)
    command = _rewrite_npm_wrapper(command, env)

    try:
        completed = subprocess.run(
            command,
            cwd=args.cd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
    except FileNotFoundError as error:
        return {"success": False, "error": f"Claude executable not found: {error}"}
    except OSError as error:
        return {"success": False, "error": f"Failed to launch Claude: {error}"}

    parsed = _extract_result_json(completed.stdout)
    stderr = completed.stderr.strip()
    stdout = completed.stdout.strip()

    success = completed.returncode == 0 and isinstance(parsed, dict) and not parsed.get("is_error", False)

    if success:
        result: Dict[str, Any] = {
            "success": True,
            "SESSION_ID": parsed.get("session_id", ""),
            "agent_messages": parsed.get("result", ""),
        }
        if args.return_raw_result:
            result["raw_result"] = parsed
        return result

    error_parts: List[str] = []
    if parsed:
        if parsed.get("result"):
            error_parts.append(str(parsed.get("result")))
        if parsed.get("message"):
            error_parts.append(str(parsed.get("message")))
    if stdout:
        error_parts.append(stdout)
    if stderr:
        error_parts.append(stderr)
    if completed.returncode != 0:
        error_parts.append(f"Claude exit code: {completed.returncode}")

    message = "\n\n".join(part for part in error_parts if part).strip() or "Unknown Claude bridge failure."
    result = {"success": False, "error": message}
    if parsed and parsed.get("session_id"):
        result["SESSION_ID"] = parsed.get("session_id")
    if args.return_raw_result and parsed:
        result["raw_result"] = parsed
    return result


def main() -> None:
    _configure_stdio()
    parser = _build_parser()
    args = parser.parse_args()
    result = run_claude(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

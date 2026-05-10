"""
Primary structured Claude delegation entrypoint for this skill.
Builds a compact handoff and sends it through the internal Claude transport.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from claude_bridge import DEFAULT_CLAUDE_RUN_TIMEOUT_SECONDS, effort_value, positive_int, run_claude
from claude_jobs import local_status, stable_job_store, start_job, stop_job, wait_job


def _normalize_items(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        trimmed = value.strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _render_list(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_numbered_list(items: Iterable[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _render_section(tag: str, content: Optional[str]) -> str:
    if not content:
        return ""
    title = tag.replace("_", " ").title()
    return f"{title}:\n{content}"


def _inline_context(sections: Iterable[str]) -> str:
    normalized: List[str] = []
    for section in sections:
        compact = " ".join(section.split())
        if compact:
            normalized.append(compact)
    return "; ".join(normalized)


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


def build_handoff(args: argparse.Namespace) -> str:
    sections: List[str] = []

    prompt = args.PROMPT.strip()
    summary = args.context_summary.strip() if args.context_summary else ""
    file_refs = _normalize_items(args.context_file_ref)
    findings = _normalize_items(args.context_finding)
    constraints = _normalize_items(args.context_constraint)
    repo_facts = _normalize_items(args.context_repo_fact)
    open_questions = _normalize_items(args.context_open_question)
    review_items = _normalize_items(getattr(args, "context_review_item", []))
    next_step = args.context_next_step.strip() if args.context_next_step else ""

    if summary:
        sections.append(_render_section("summary", summary))
    if file_refs:
        sections.append(_render_section("relevant_files", _render_list(file_refs)))
    if findings:
        sections.append(_render_section("findings", _render_list(findings)))
    if constraints:
        sections.append(_render_section("constraints", _render_list(constraints)))
    if repo_facts:
        sections.append(_render_section("repo_facts", _render_list(repo_facts)))
    if open_questions:
        sections.append(_render_section("open_questions", _render_list(open_questions)))
    if next_step:
        sections.append(_render_section("next_step", next_step))

    if review_items:
        parts: List[str] = [
            (
                f"Please complete this task directly: {prompt} "
                "Review only the numbered items below."
            ),
            "",
            _render_numbered_list(review_items),
        ]
        if sections:
            parts.extend(["", "Use these handoff notes as context:"])
            parts.append("\n\n".join(sections))
        parts.extend(
            [
                "",
                (
                    "Reply with one section per numbered item. For each item, state: "
                    "assessment, risks, recommendation. Do not add items beyond the "
                    "numbered items."
                ),
            ]
        )
        return "\n".join(parts).strip() + "\n"

    parts: List[str] = []
    if sections:
        context = _inline_context(sections)
        parts.extend(
            [
                (
                    f"Please complete this task directly: {prompt} "
                    f"Use these handoff notes as the source for your answer: {context}"
                ),
            ]
        )
    else:
        parts.append(prompt)
    return "\n".join(parts).strip() + "\n"


def call_bridge(args: argparse.Namespace, prompt_to_send: str) -> dict:
    bridge_args = SimpleNamespace(
        PROMPT=prompt_to_send,
        cd=args.cd,
        SESSION_ID=args.SESSION_ID,
        permission_mode=args.permission_mode,
        add_dir=args.add_dir,
        model=args.model,
        effort=args.effort or "",
        system_prompt="",
        append_system_prompt="",
        return_raw_result=args.return_raw_result,
        timeout_seconds=args.timeout_seconds,
    )
    return run_claude(bridge_args)


def _add_delegate_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_timeout: bool,
    require_session_id: bool = False,
) -> None:
    parser.add_argument("--PROMPT", required=True, help="Task instruction for Claude.")
    parser.add_argument("--cd", required=True, help="Workspace root for Claude.")
    parser.add_argument("--SESSION_ID", required=require_session_id, default="", help="Resume the specified Claude session.")
    parser.add_argument("--context-summary", default="", help="Short high-confidence summary.")
    parser.add_argument("--context-file-ref", action="append", default=[], help="Relevant file reference, e.g. `src/app.ts :: entry point`.")
    parser.add_argument("--context-finding", action="append", default=[], help="Concrete finding already established.")
    parser.add_argument("--context-constraint", action="append", default=[], help="Constraint that must remain true.")
    parser.add_argument("--context-repo-fact", action="append", default=[], help="Stable project fact.")
    parser.add_argument("--context-open-question", action="append", default=[], help="Open question that materially affects implementation.")
    parser.add_argument("--context-review-item", action="append", default=[], help="Explicit review item for option-by-option critique.")
    parser.add_argument("--context-next-step", default="", help="Single most useful next action for Claude.")
    parser.add_argument("--context-on-resume", action="store_true", help="Resend the structured handoff even when resuming an existing session.")
    parser.add_argument("--preview-handoff", action="store_true", help="Print the synthesized handoff and exit without calling Claude.")
    parser.add_argument("--save-handoff", default="", help="Write the synthesized handoff to a file before any delegation.")
    parser.add_argument(
        "--permission-mode",
        default="bypassPermissions",
        choices=["acceptEdits", "bypassPermissions", "default", "dontAsk", "plan", "auto"],
        help="Claude permission mode. Defaults to `bypassPermissions` for automation.",
    )
    parser.add_argument("--add-dir", action="append", default=[], help="Additional directories to allow tool access to.")
    parser.add_argument("--model", default="", help="Claude model override. Only set this when explicitly requested by the user.")
    parser.add_argument("--effort", default=None, type=effort_value, metavar="EFFORT", help="Claude effort override. Choices: low, medium, high, xhigh, max.")
    parser.add_argument("--return-raw-result", action="store_true", help="Include Claude's raw JSON payload in the output.")
    if include_timeout:
        parser.add_argument(
            "--timeout-seconds",
            type=positive_int,
            default=DEFAULT_CLAUDE_RUN_TIMEOUT_SECONDS,
            help=f"Maximum seconds to wait for Claude CLI. Defaults to {DEFAULT_CLAUDE_RUN_TIMEOUT_SECONDS}.",
        )


def _add_job_store_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--job-store",
        default="",
        help="Local async job store directory. Defaults to .claude-delegate-jobs in this skill repo.",
    )


def _add_notification_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--notify-file",
        default="",
        help="Write a terminal-state JSON notification to this file when the async job finishes.",
    )
    parser.add_argument(
        "--notify-command",
        default="",
        help="Run a completion hook after the async job finishes. Prefer a JSON argv array; payload is sent on stdin.",
    )
    parser.add_argument(
        "--notify-timeout-seconds",
        type=positive_int,
        default=30,
        help="Maximum seconds to wait for the notify command. Defaults to 30.",
    )


def _prepare_prompt(args: argparse.Namespace) -> tuple[str, str, bool]:
    handoff = build_handoff(args)

    if args.save_handoff:
        save_path = Path(args.save_handoff)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(handoff, encoding="utf-8")

    if args.preview_handoff:
        sys.stdout.write(handoff)
        return handoff, "", False

    prompt_to_send = args.PROMPT.strip()
    handoff_used = False
    if not args.SESSION_ID or args.context_on_resume:
        prompt_to_send = handoff.rstrip()
        handoff_used = True
    return handoff, prompt_to_send, handoff_used


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_run(args: argparse.Namespace) -> None:
    handoff, prompt_to_send, handoff_used = _prepare_prompt(args)
    if args.preview_handoff:
        return

    result = call_bridge(args, prompt_to_send)

    if args.save_handoff:
        result["handoff_path"] = str(Path(args.save_handoff))
    result["handoff_used"] = handoff_used

    _print_json(result)


def _cmd_start(args: argparse.Namespace) -> None:
    handoff, prompt_to_send, handoff_used = _prepare_prompt(args)
    if args.preview_handoff:
        return
    args.handoff_used = handoff_used
    record = start_job(args, prompt_to_send, handoff)
    _print_json(
        {
            "success": True,
            "job_id": record["job_id"],
            "state": record["state"],
            "paths": record["paths"],
            "SESSION_ID": record.get("SESSION_ID", ""),
            "requested_SESSION_ID": record.get("requested_SESSION_ID", ""),
        }
    )


def _cmd_resume(args: argparse.Namespace) -> None:
    handoff, prompt_to_send, handoff_used = _prepare_prompt(args)
    if args.preview_handoff:
        return
    args.handoff_used = handoff_used
    record = start_job(args, prompt_to_send, handoff, require_session_lock=True)
    _print_json(
        {
            "success": True,
            "job_id": record["job_id"],
            "state": record["state"],
            "paths": record["paths"],
            "requested_SESSION_ID": record.get("requested_SESSION_ID", ""),
        }
    )


def _cmd_status(args: argparse.Namespace) -> None:
    _print_json(local_status(stable_job_store(args.job_store), args.job_id))


def _cmd_wait(args: argparse.Namespace) -> None:
    timeout = None if args.timeout is None else float(args.timeout)
    _print_json(wait_job(stable_job_store(args.job_store), args.job_id, timeout, args.poll_interval))


def _cmd_stop(args: argparse.Namespace) -> None:
    _print_json(stop_job(stable_job_store(args.job_store), args.job_id))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Primary structured Claude delegation entrypoint",
        epilog=(
            "Migration: old no-subcommand usage was removed. Use `run` for a synchronous "
            "delegation, or `start/status/wait/stop/resume` for async jobs."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="Run a delegation synchronously.")
    _add_delegate_arguments(run_parser, include_timeout=True)
    run_parser.set_defaults(func=_cmd_run)

    start_parser = subparsers.add_parser("start", help="Start an async delegation job and return immediately.")
    _add_delegate_arguments(start_parser, include_timeout=False)
    _add_job_store_argument(start_parser)
    _add_notification_arguments(start_parser)
    start_parser.set_defaults(func=_cmd_start)

    resume_parser = subparsers.add_parser("resume", help="Start an async resume job for an existing Claude SESSION_ID.")
    _add_delegate_arguments(resume_parser, include_timeout=False, require_session_id=True)
    _add_job_store_argument(resume_parser)
    _add_notification_arguments(resume_parser)
    resume_parser.set_defaults(func=_cmd_resume)

    status_parser = subparsers.add_parser("status", help="Read local async job state without contacting Claude.")
    _add_job_store_argument(status_parser)
    status_parser.add_argument("--job-id", default="", help="Job id to inspect. Omit to list all local jobs.")
    status_parser.set_defaults(func=_cmd_status)

    wait_parser = subparsers.add_parser("wait", help="Wait for a local async job to finish. Timeout does not stop the job.")
    _add_job_store_argument(wait_parser)
    wait_parser.add_argument("--job-id", required=True, help="Job id to wait for.")
    wait_parser.add_argument("--timeout", type=float, default=None, help="Seconds to wait before returning timed_out.")
    wait_parser.add_argument("--poll-interval", type=float, default=0.25, help="Seconds between local status polls.")
    wait_parser.set_defaults(func=_cmd_wait)

    stop_parser = subparsers.add_parser("stop", help="Explicitly stop a running async job.")
    _add_job_store_argument(stop_parser)
    stop_parser.add_argument("--job-id", required=True, help="Job id to stop.")
    stop_parser.set_defaults(func=_cmd_stop)

    return parser


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0].startswith("-") and raw_args[0] not in {"-h", "--help"}:
        parser.error(
            "Migration: old no-subcommand usage was removed. Use `run` for synchronous delegation "
            "or `start/status/wait/stop/resume` for async jobs."
        )
    args = parser.parse_args(raw_args)
    if not getattr(args, "subcommand", ""):
        parser.error("missing subcommand. Use run, start, status, wait, stop, or resume.")
    return args


def main() -> None:
    _configure_stdio()
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

"""
Structured Claude delegation wrapper for the delegating-with-claude skill.
Builds a compact handoff and forwards it through claude_bridge.py.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


def _normalize_items(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        trimmed = value.strip()
        if trimmed:
            normalized.append(trimmed)
    return normalized


def _render_list(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_section(tag: str, content: Optional[str]) -> str:
    if not content:
        return ""
    title = tag.replace("_", " ").title()
    return f"{title}:\n{content}"


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

    summary = args.context_summary.strip() if args.context_summary else ""
    file_refs = _normalize_items(args.context_file_ref)
    findings = _normalize_items(args.context_finding)
    constraints = _normalize_items(args.context_constraint)
    repo_facts = _normalize_items(args.context_repo_fact)
    open_questions = _normalize_items(args.context_open_question)
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

    parts: List[str] = []
    if sections:
        parts.extend(
            [
                "Complete the task below. Use the advisory context afterwards if it is helpful. Do not comment on the context packaging itself.",
                "",
                "Task:",
                args.PROMPT.strip(),
                "",
                "Working context:",
                *sections,
            ]
        )
    else:
        parts.extend(["Task:", args.PROMPT.strip()])
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Structured Claude delegation wrapper")
    parser.add_argument("--PROMPT", required=True, help="Task instruction for Claude.")
    parser.add_argument("--cd", required=True, help="Workspace root for Claude.")
    parser.add_argument("--SESSION_ID", default="", help="Resume the specified Claude session.")
    parser.add_argument("--context-summary", default="", help="Short high-confidence summary.")
    parser.add_argument("--context-file-ref", action="append", default=[], help="Relevant file reference, e.g. `src/app.ts :: entry point`.")
    parser.add_argument("--context-finding", action="append", default=[], help="Concrete finding already established.")
    parser.add_argument("--context-constraint", action="append", default=[], help="Constraint that must remain true.")
    parser.add_argument("--context-repo-fact", action="append", default=[], help="Stable project fact.")
    parser.add_argument("--context-open-question", action="append", default=[], help="Open question that materially affects implementation.")
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
    parser.add_argument("--return-raw-result", action="store_true", help="Include Claude's raw JSON payload in the output.")
    args = parser.parse_args()

    handoff = build_handoff(args)

    if args.save_handoff:
        save_path = Path(args.save_handoff)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(handoff, encoding="utf-8")

    if args.preview_handoff:
        sys.stdout.write(handoff)
        return

    prompt_to_send = args.PROMPT.strip()
    if not args.SESSION_ID or args.context_on_resume:
        prompt_to_send = handoff.rstrip()

    bridge_script = Path(__file__).with_name("claude_bridge.py")
    command = [
        sys.executable,
        str(bridge_script),
        "--cd",
        args.cd,
        "--PROMPT",
        prompt_to_send,
        "--permission-mode",
        args.permission_mode,
    ]

    if args.SESSION_ID:
        command.extend(["--SESSION_ID", args.SESSION_ID])
    if args.model:
        command.extend(["--model", args.model])
    if args.return_raw_result:
        command.append("--return-raw-result")
    for add_dir in args.add_dir:
        command.extend(["--add-dir", add_dir])

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if completed.returncode != 0:
        error = stderr or stdout or f"claude_bridge.py failed with exit code {completed.returncode}."
        print(json.dumps({"success": False, "error": error}, ensure_ascii=False, indent=2))
        return

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        message = stdout or stderr or "claude_bridge.py returned non-JSON output."
        print(json.dumps({"success": False, "error": message}, ensure_ascii=False, indent=2))
        return

    if args.save_handoff:
        result["handoff_path"] = str(Path(args.save_handoff))
    if not args.SESSION_ID or args.context_on_resume:
        result["handoff_used"] = True
    else:
        result["handoff_used"] = False

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

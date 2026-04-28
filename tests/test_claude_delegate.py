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


def load_delegate():
    spec = importlib.util.spec_from_file_location("claude_delegate_under_test", DELEGATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
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


def install_fake_bridge(delegate, monkeypatch, result):
    calls = []

    if hasattr(delegate, "call_bridge"):
        def fake_call_bridge(args, prompt_to_send):
            calls.append({"prompt": prompt_to_send, "args": args})
            return dict(result)

        monkeypatch.setattr(delegate, "call_bridge", fake_call_bridge)
        return calls

    def fake_run(command, **kwargs):
        calls.append({"command": command, "kwargs": kwargs})
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result, ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr(delegate.subprocess, "run", fake_run)
    return calls


def sent_prompt(call):
    if "prompt" in call:
        return call["prompt"]
    command = call["command"]
    return command[command.index("--PROMPT") + 1]


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


def test_first_call_uses_handoff_and_marks_result(monkeypatch, capsys):
    delegate = load_delegate()
    result = {"success": True, "SESSION_ID": "session-1", "agent_messages": "OK"}
    calls = install_fake_bridge(delegate, monkeypatch, result)
    tmp_dir = make_temp_dir()
    try:
        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "--cd",
                str(tmp_dir),
                "--context-summary",
                "sanity check",
                "--PROMPT",
                "Reply with exactly OK.",
            ],
        )

        parsed = json.loads(output)
        assert parsed["success"] is True
        assert parsed["handoff_used"] is True
        assert sent_prompt(calls[0]).startswith("Please complete this task directly:")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_resume_without_context_on_resume_sends_raw_prompt(monkeypatch, capsys):
    delegate = load_delegate()
    result = {"success": True, "SESSION_ID": "session-1", "agent_messages": "OK"}
    calls = install_fake_bridge(delegate, monkeypatch, result)
    tmp_dir = make_temp_dir()
    try:
        output = run_delegate(
            delegate,
            monkeypatch,
            capsys,
            [
                "--cd",
                str(tmp_dir),
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
        assert parsed["handoff_used"] is False
        assert sent_prompt(calls[0]) == "Reply with exactly OK."
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

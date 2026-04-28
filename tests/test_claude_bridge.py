from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "claude_bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("claude_bridge_under_test", BRIDGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_temp_dir() -> Path:
    path = ROOT / ".tmp-tests" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def test_build_command_includes_optional_arguments():
    bridge = load_bridge()
    args = SimpleNamespace(
        permission_mode="bypassPermissions",
        SESSION_ID="session-1",
        add_dir=["C:/extra/one", "C:/extra/two"],
        model="opus",
        system_prompt="system text",
        append_system_prompt="append text",
        PROMPT="Do the work.",
    )

    assert bridge._build_command(args) == [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "-r",
        "session-1",
        "--add-dir",
        "C:/extra/one",
        "--add-dir",
        "C:/extra/two",
        "--model",
        "opus",
        "--system-prompt",
        "system text",
        "--append-system-prompt",
        "append text",
    ]


def test_extract_result_json_uses_last_json_object():
    bridge = load_bridge()
    stdout = "\n".join(
        [
            "log line",
            json.dumps({"session_id": "old", "result": "old"}),
            "not json",
            json.dumps({"session_id": "new", "result": "OK"}),
        ]
    )

    assert bridge._extract_result_json(stdout) == {"session_id": "new", "result": "OK"}


def test_extract_result_json_returns_none_for_non_json_output():
    bridge = load_bridge()

    assert bridge._extract_result_json("plain text\nnot json") is None


def test_rewrite_windows_npm_wrapper_to_node_cli(monkeypatch):
    bridge = load_bridge()
    monkeypatch.setattr(bridge.os, "name", "nt", raising=False)

    tmp_dir = make_temp_dir()
    try:
        npm_dir = tmp_dir / "npm"
        cli_js = npm_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
        cli_js.parent.mkdir(parents=True)
        cli_js.write_text("console.log('claude')", encoding="utf-8")
        node = npm_dir / "node.exe"
        node.write_text("", encoding="utf-8")

        command = [str(npm_dir / "claude.cmd"), "-p", "prompt"]

        assert bridge._rewrite_npm_wrapper(command, {"PATH": str(npm_dir)}) == [
            str(node),
            str(cli_js),
            "-p",
            "prompt",
        ]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_bridge_cli_and_import_api_return_same_envelope(monkeypatch, capsys):
    bridge = load_bridge()
    expected = {"success": True, "SESSION_ID": "session-1", "agent_messages": "OK"}

    def fake_run_claude(args):
        assert args.PROMPT == "Reply with exactly OK."
        return dict(expected)

    monkeypatch.setattr(bridge, "run_claude", fake_run_claude)
    monkeypatch.setattr(
        "sys.argv",
        [
            "claude_bridge.py",
            "--cd",
            str(ROOT),
            "--PROMPT",
            "Reply with exactly OK.",
        ],
    )

    bridge.main()
    assert json.loads(capsys.readouterr().out) == expected


def test_run_claude_can_be_called_twice_without_prompt_state_leak(monkeypatch):
    bridge = load_bridge()
    seen_prompts = []

    def fake_subprocess_run(command, **kwargs):
        seen_prompts.append(kwargs.get("input"))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"session_id": f"session-{len(seen_prompts)}", "result": kwargs.get("input")}),
            stderr="",
        )

    monkeypatch.setattr(bridge.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(bridge, "_resolve_executable", lambda name, env: name)
    monkeypatch.setattr(bridge, "_rewrite_npm_wrapper", lambda command, env: command)

    base = {
        "cd": str(ROOT),
        "SESSION_ID": "",
        "permission_mode": "bypassPermissions",
        "add_dir": [],
        "model": "",
        "system_prompt": "",
        "append_system_prompt": "",
        "return_raw_result": False,
    }

    first = bridge.run_claude(SimpleNamespace(PROMPT="first prompt", **base))
    second = bridge.run_claude(SimpleNamespace(PROMPT="second prompt", **base))

    assert first["agent_messages"] == "first prompt"
    assert second["agent_messages"] == "second prompt"
    assert seen_prompts == ["first prompt", "second prompt"]


def test_run_claude_sends_multiline_prompt_via_stdin(monkeypatch):
    bridge = load_bridge()
    multiline_prompt = "Line one\n\n1. Alpha\n2. Beta\n\nFinal instruction."
    captured = {}

    def fake_subprocess_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"session_id": "session-1", "result": "OK"}),
            stderr="",
        )

    monkeypatch.setattr(bridge.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(bridge, "_resolve_executable", lambda name, env: name)
    monkeypatch.setattr(bridge, "_rewrite_npm_wrapper", lambda command, env: command)

    result = bridge.run_claude(
        SimpleNamespace(
            PROMPT=multiline_prompt,
            cd=str(ROOT),
            SESSION_ID="",
            permission_mode="bypassPermissions",
            add_dir=[],
            model="",
            system_prompt="",
            append_system_prompt="",
            return_raw_result=False,
        )
    )

    assert result["success"] is True
    assert captured["input"] == multiline_prompt
    assert multiline_prompt not in captured["command"]

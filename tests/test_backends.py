"""Claude Code handoff backend and backend selection."""
import pytest

from scripts import backends


def test_claude_code_writes_prompt_and_raises_pending(tmp_path):
    backend = backends.ClaudeCodeBackend(runs_dir=str(tmp_path / "runs"))
    with pytest.raises(backends.PendingHandoff):
        backend.complete("SYS", "USER", tag="novel/ch00001/translate")

    prompt_file = tmp_path / "runs" / "novel" / "ch00001" / "translate.prompt.md"
    assert prompt_file.exists()
    text = prompt_file.read_text(encoding="utf-8")
    assert "SYS" in text and "USER" in text


def test_claude_code_consumes_existing_response(tmp_path):
    backend = backends.ClaudeCodeBackend(runs_dir=str(tmp_path / "runs"))
    tag = "novel/ch00001/translate"
    # First call writes the prompt and blocks.
    with pytest.raises(backends.PendingHandoff):
        backend.complete("SYS", "USER", tag=tag)
    # Operator supplies the response; second call returns it.
    response_file = tmp_path / "runs" / "novel" / "ch00001" / "translate.response.md"
    response_file.write_text("TRANSLATED OUTPUT", encoding="utf-8")
    assert backend.complete("SYS", "USER", tag=tag) == "TRANSLATED OUTPUT"


def test_get_backend_defaults_to_claude_code():
    backend = backends.get_backend(None, {})
    assert backend.name == "claude_code"


def test_get_backend_unknown_raises():
    with pytest.raises(ValueError):
        backends.get_backend("nope", {})


# --- claude_code_stateless backend (subscription-backed `claude -p`, no API key) ---------------

def test_stateless_command_has_required_flags():
    backend = backends.ClaudeCodeStatelessBackend(model="claude-fable-5")
    cmd = backend.build_command("SYSTEM PROMPT")
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-fable-5"       # explicit model
    assert "--no-session-persistence" in cmd                       # no saved session
    assert cmd[cmd.index("--system-prompt") + 1] == "SYSTEM PROMPT"  # Wenmai prompt replaces default
    assert "--disallowed-tools" in cmd                             # tools disabled
    assert cmd[cmd.index("--output-format") + 1] == "text"


def test_stateless_command_never_continues_a_session():
    cmd = backends.ClaudeCodeStatelessBackend().build_command("SYS")
    for forbidden in ("--continue", "-c", "--resume", "-r", "--fork-session", "--bare"):
        assert forbidden not in cmd


def test_stateless_disallows_file_and_exec_tools():
    cmd = backends.ClaudeCodeStatelessBackend().build_command("SYS")
    tools = cmd[cmd.index("--disallowed-tools") + 1]
    for tool in ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "Task"):
        assert tool in tools


def test_stateless_is_model_configurable():
    # A config change is all it takes to move from the Fable pilot to Opus 4.8.
    fable = backends.get_backend("claude_code_stateless",
                                 {"claude_code_stateless": {"model": "claude-fable-5"}})
    assert fable.build_command("s")[fable.build_command("s").index("--model") + 1] == "claude-fable-5"
    opus = backends.get_backend("claude_code_stateless",
                                {"claude_code_stateless": {"model": "claude-opus-4-8"}})
    assert "claude-opus-4-8" in opus.build_command("s")
    # Default (no config) is Wenmai's intended default model, not the pilot model.
    assert backends.get_backend("claude_code_stateless", {}).model == "claude-opus-4-8"


def test_stateless_complete_passes_user_via_stdin_in_isolated_cwd(monkeypatch):
    captured = {}

    class FakeCompleted:
        returncode = 0
        stdout = "  TRANSLATED CHAPTER  \n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        captured["cwd"] = kwargs.get("cwd")
        return FakeCompleted()

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    backend = backends.ClaudeCodeStatelessBackend(model="claude-fable-5")
    out = backend.complete("SYS", "USER PROMPT BODY", tag="lotm/ch00001/A")

    assert out == "TRANSLATED CHAPTER"                 # stdout captured and stripped
    assert captured["input"] == "USER PROMPT BODY"     # user prompt via stdin, not argv
    assert "USER PROMPT BODY" not in captured["cmd"]   # never on the command line
    # Ran in a fresh temp dir, not the repo, so tools would find nothing.
    assert captured["cwd"] is not None
    assert "wenmai" in str(captured["cwd"]).lower() and "cli" in str(captured["cwd"]).lower()
    assert str(captured["cwd"]) != str(backends.REPO_ROOT)


def test_stateless_complete_raises_on_cli_failure(monkeypatch):
    class FakeFail:
        returncode = 1
        stdout = ""
        stderr = "model not found"

    monkeypatch.setattr(backends.subprocess, "run", lambda cmd, **k: FakeFail())
    with pytest.raises(RuntimeError):
        backends.ClaudeCodeStatelessBackend().complete("SYS", "USER", tag="t")

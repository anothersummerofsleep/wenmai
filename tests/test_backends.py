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

"""Pluggable LLM backends.

A backend is purely about HOW and WHERE the model is called (transport and provider). It has
nothing to do with language: linguistic behaviour lives in the language layer
(prompts/languages/<lang>.md), never here. A backend receives an already-assembled prompt and
returns text; it does not know or care what languages are involved.

Every pass in the pipeline calls one interface, `LLMBackend.complete(...)`. Two backends ship:

- ClaudeCodeBackend: no API key, no billing. Writes the assembled prompt to a handoff file and
  reads the answer back from a sibling file. Lets Claude Code (a human-in-the-loop operator) do the
  translation pass with full review, then re-run to continue.
- AnthropicBackend: calls the Claude API directly for unattended and CI runs.

Add another provider (a different model API, a local runtime) later by subclassing LLMBackend and
registering it in `get_backend`. That is a transport choice, orthogonal to source/target language.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class PendingHandoff(Exception):
    """Raised by ClaudeCodeBackend when it has written a prompt and is waiting for a response file."""


def _rel(path: Path) -> str:
    """Path relative to the repo root for display, robust to paths outside it (e.g. tests)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_config() -> dict:
    """Load config.yaml if present, else fall back to config.example.yaml defaults."""
    import yaml

    for name in ("config.yaml", "config.example.yaml"):
        path = REPO_ROOT / name
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
    return {}


class LLMBackend(ABC):
    name = "base"

    @abstractmethod
    def complete(self, system: str, user: str, *, tag: str) -> str:
        """Return the model's text completion for (system, user).

        `tag` is a short slug like 'novel/ch00001/translate' used for handoff filenames and logs.
        """
        raise NotImplementedError


class ClaudeCodeBackend(LLMBackend):
    """File-handoff backend: prompt out, response in. No network, no key.

    On a call it writes `<runs_dir>/<tag>.prompt.md`. If `<runs_dir>/<tag>.response.md` already
    exists it returns its contents (and the run continues). Otherwise it raises PendingHandoff with
    instructions: fill the response file, then re-run the same command.
    """

    name = "claude_code"

    def __init__(self, runs_dir: str = ".runs"):
        self.runs_dir = REPO_ROOT / runs_dir

    def complete(self, system: str, user: str, *, tag: str) -> str:
        base = self.runs_dir / tag
        base.parent.mkdir(parents=True, exist_ok=True)
        prompt_path = base.with_suffix(".prompt.md")
        response_path = base.with_suffix(".response.md")

        prompt_path.write_text(
            f"<!-- SYSTEM -->\n\n{system}\n\n<!-- USER -->\n\n{user}\n",
            encoding="utf-8",
        )

        if response_path.exists():
            text = response_path.read_text(encoding="utf-8").strip()
            if text:
                return text

        rel_prompt = _rel(prompt_path)
        rel_response = _rel(response_path)
        raise PendingHandoff(
            "claude_code backend is waiting on a response.\n"
            f"  1. Read the assembled prompt:  {rel_prompt}\n"
            f"  2. Write the completion to:    {rel_response}\n"
            "  3. Re-run the same command to continue.\n"
        )


class AnthropicBackend(LLMBackend):
    """Direct Claude API backend for unattended / CI runs. Needs ANTHROPIC_API_KEY."""

    name = "anthropic"

    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 8000):
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, *, tag: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The anthropic backend needs the 'anthropic' package. "
                "Run: pip install -r requirements.txt"
            ) from exc

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment.")

        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()


def get_backend(name: str | None = None, config: dict | None = None) -> LLMBackend:
    """Instantiate the backend named in config (or overridden by `name`)."""
    config = config if config is not None else load_config()
    name = name or config.get("backend", "claude_code")

    if name == "claude_code":
        cc = config.get("claude_code", {})
        return ClaudeCodeBackend(runs_dir=cc.get("runs_dir", ".runs"))
    if name == "anthropic":
        an = config.get("anthropic", {})
        return AnthropicBackend(
            model=an.get("model", "claude-opus-4-8"),
            max_tokens=an.get("max_tokens", 8000),
        )
    raise ValueError(f"Unknown backend: {name!r}. Use 'claude_code' or 'anthropic'.")

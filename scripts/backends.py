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
import subprocess
import tempfile
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


# Tools disabled for the stateless CLI backend, so a translation call cannot read repo files,
# other candidates, or run commands. Belt to the empty-cwd suspenders.
STATELESS_DISALLOWED_TOOLS = (
    "Bash,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,"
    "WebFetch,WebSearch,Task,TodoWrite,Agent,Artifact"
)

# Flags that would share conversational state across calls. This backend must never use them.
_FORBIDDEN_STATELESS_FLAGS = ("--continue", "-c", "--resume", "-r", "--fork-session", "--bare")


class ClaudeCodeStatelessBackend(LLMBackend):
    """Model-configurable backend that runs each completion as a fresh, stateless `claude -p` process.

    Uses Claude Code non-interactively under the logged-in subscription (no ANTHROPIC_API_KEY, no
    `--bare` which would force API auth). Every complete() is a new process with no shared session:

      claude -p --model <model> --no-session-persistence --output-format text
             --system-prompt <Wenmai system prompt> --disallowed-tools <all file/web/exec tools>

    - System prompt (Wenmai's translation prompt) REPLACES Claude Code's coding system prompt via
      --system-prompt; with --system-prompt the default dynamic sections (cwd/env/memory/git) do not
      apply.
    - The Wenmai user prompt is the process's stdin (its only user request) - unbounded size, no
      shell quoting.
    - Tools are disallowed and the process runs in a fresh EMPTY temp directory, so it cannot inspect
      the repository, other candidates, or anything outside the supplied prompt.
    - No --continue/--resume/--fork-session, and --no-session-persistence: nothing is saved or reused.

    Model is configurable (claude_code_stateless.model), so switching to Opus 4.8 is a config change.
    """

    name = "claude_code_stateless"

    def __init__(self, model: str = "claude-opus-4-8", cli: str = "claude",
                 disallowed_tools: str = STATELESS_DISALLOWED_TOOLS, timeout: int = 600):
        self.model = model
        self.cli = cli
        self.disallowed_tools = disallowed_tools
        self.timeout = timeout

    def build_command(self, system: str) -> list[str]:
        """The argv for one stateless call (no secrets; the user prompt goes via stdin, not argv)."""
        cmd = [
            self.cli, "-p",
            "--model", self.model,
            "--no-session-persistence",
            "--output-format", "text",
            "--system-prompt", system,
            "--disallowed-tools", self.disallowed_tools,
        ]
        # Guard the statelessness invariant at construction time.
        assert not any(flag in cmd for flag in _FORBIDDEN_STATELESS_FLAGS), \
            "stateless backend must not use session-continuation flags"
        return cmd

    def complete(self, system: str, user: str, *, tag: str) -> str:
        cmd = self.build_command(system)
        with tempfile.TemporaryDirectory(prefix="wenmai-cli-") as cwd:
            # Fresh empty cwd: nothing for tools to find even if one somehow ran.
            result = subprocess.run(
                cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                cwd=cwd, timeout=self.timeout,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"`{self.cli} -p` failed for {tag} (exit {result.returncode}): "
                f"{(result.stderr or '').strip()[:500]}"
            )
        return (result.stdout or "").strip()


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
    if name == "claude_code_stateless":
        cs = config.get("claude_code_stateless", {})
        return ClaudeCodeStatelessBackend(
            model=cs.get("model", "claude-opus-4-8"),
            cli=cs.get("cli", "claude"),
            disallowed_tools=cs.get("disallowed_tools", STATELESS_DISALLOWED_TOOLS),
            timeout=cs.get("timeout", 600),
        )
    raise ValueError(
        f"Unknown backend: {name!r}. Use 'claude_code', 'claude_code_stateless', or 'anthropic'."
    )

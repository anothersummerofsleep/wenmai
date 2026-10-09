"""Shared pytest fixtures.

Most tests build throwaway novels under a temp directory and point the code at them by patching
`context.NOVELS_DIR`. Prompt files (prompts/translate.md, prompts/languages/*.md) still come from the
real repo, so overlay resolution is exercised for real. The bundled `sample-novel` is used read-only
for the end-to-end smoke test, via a copy so the repo's files are never mutated.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts import config, context

# Keys that select WHERE workspaces are read from. Ambient values (a developer's shell or local
# config.yaml) must not redirect fixtures that point the code at a temp root via NOVELS_DIR.
AMBIENT_ROOT_KEYS = ("content_roots", config.CONFLICT_KEY)


def isolate_ambient_content_roots(monkeypatch) -> None:
    """Drop ambient content-root settings, leaving every other config key intact.

    Removes WENMAI_CONTENT_ROOTS from the environment and strips the content-root keys from what
    config.load_config returns. A test that exercises the feature sets its own values afterwards
    (monkeypatch.setenv / patching config.load_config), which replaces this baseline, so the
    real precedence and collision logic is still what runs.
    """
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    real_load = config.load_config

    def load_without_ambient_roots() -> dict:
        return {k: v for k, v in real_load().items() if k not in AMBIENT_ROOT_KEYS}

    monkeypatch.setattr(config, "load_config", load_without_ambient_roots)


@pytest.fixture(autouse=True)
def _no_ambient_content_roots(monkeypatch):
    isolate_ambient_content_roots(monkeypatch)


@pytest.fixture
def novels_dir(tmp_path, monkeypatch):
    """A temp novels/ root, wired into the code via context.NOVELS_DIR."""
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr(context, "NOVELS_DIR", root)
    return root


# Default explicit language pair for fixtures. Real novels must declare their own (validated); this
# convenience lives only in test setup, never in the normal project-loading path.
DEFAULT_CONFIG = {"source_language": "zh", "target_language": "en"}


@pytest.fixture
def make_novel(novels_dir):
    """Factory: write a novel on disk and return its slug.

    config=None writes NO novel.yaml (to test missing configuration). Pass a dict to control the
    language pair (or omit to get the explicit zh/en default).
    """
    def _make(
        slug: str = "novel",
        *,
        config: dict | None = DEFAULT_CONFIG,
        sources: dict[int, str] | None = None,
        translations: dict[int, str] | None = None,
        contexts: dict[str, str] | None = None,
        phrases: list[str] | None = None,
    ) -> str:
        base = novels_dir / slug
        (base / "source").mkdir(parents=True)
        (base / "translated").mkdir(parents=True)
        (base / "context").mkdir(parents=True)
        (base / "translation_memory").mkdir(parents=True)

        if config is not None:
            import yaml
            (base / "novel.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")

        src = (config or {}).get("source_language", "zh")
        tgt = (config or {}).get("target_language", "en")

        for n, text in (sources or {}).items():
            (base / "source" / f"{context.chapter_id(n)}_{src}.txt").write_text(text, encoding="utf-8")
        for n, text in (translations or {}).items():
            (base / "translated" / f"{context.chapter_id(n)}_{tgt}.md").write_text(text, encoding="utf-8")
        for name, text in (contexts or {}).items():
            (base / "context" / name).write_text(text, encoding="utf-8")
        if phrases is not None:
            (base / "translation_memory" / "phrases.jsonl").write_text(
                "\n".join(phrases) + ("\n" if phrases else ""), encoding="utf-8"
            )
        return slug

    return _make


@pytest.fixture
def sample_novel_copy(tmp_path, monkeypatch):
    """A writable copy of the bundled sample-novel, wired in via context.NOVELS_DIR."""
    real = context.REPO_ROOT / "novels" / "sample-novel"
    root = tmp_path / "novels"
    root.mkdir()
    shutil.copytree(real, root / "sample-novel")
    monkeypatch.setattr(context, "NOVELS_DIR", root)
    # Tripwire: callers mutate this workspace, so it must resolve to the copy, never the tracked one.
    assert context.novel_dir("sample-novel") == root / "sample-novel"
    return "sample-novel"

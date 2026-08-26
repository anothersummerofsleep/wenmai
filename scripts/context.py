"""Context retrieval and assembly (pipeline pass 1).

Mechanical, no LLM: given a novel and a target chapter, gather everything the translator should see
before it starts - style guide, canonical context records, the previous N translated chapters, and
the translation-memory of already-seen idioms - and stitch it into one prompt block.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
NOVELS_DIR = REPO_ROOT / "novels"

CONTEXT_FILES = [
    "characters.yaml",
    "terminology.yaml",
    "locations.yaml",
    "factions.yaml",
    "cultivation_system.yaml",
    "timeline.yaml",
]


def novel_dir(novel: str) -> Path:
    path = NOVELS_DIR / novel
    if not path.is_dir():
        raise FileNotFoundError(f"No such novel: {path}")
    return path


def load_novel_config(novel: str) -> dict:
    path = novel_dir(novel) / "novel.yaml"
    if not path.exists():
        return {"source_language": "zh", "target_language": "en"}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def source_path(novel: str, chapter: int) -> Path:
    return novel_dir(novel) / "source" / f"ch{chapter:04d}_zh.txt"


def translated_path(novel: str, chapter: int) -> Path:
    return novel_dir(novel) / "translated" / f"ch{chapter:04d}_en.md"


def read_source(novel: str, chapter: int) -> str:
    path = source_path(novel, chapter)
    if not path.exists():
        raise FileNotFoundError(f"Missing source chapter: {path}")
    return path.read_text(encoding="utf-8")


def previous_translations(novel: str, chapter: int, n: int) -> list[tuple[int, str]]:
    """Return up to n most recent already-translated chapters before `chapter`, oldest first."""
    out: list[tuple[int, str]] = []
    for prev in range(max(1, chapter - n), chapter):
        path = translated_path(novel, prev)
        if path.exists():
            out.append((prev, path.read_text(encoding="utf-8")))
    return out


def load_context_records(novel: str) -> str:
    """Concatenate the canonical context YAML files into one labelled block."""
    ctx_dir = novel_dir(novel) / "context"
    chunks: list[str] = []
    for fname in CONTEXT_FILES:
        path = ctx_dir / fname
        if path.exists() and path.read_text(encoding="utf-8").strip():
            chunks.append(f"### {fname}\n```yaml\n{path.read_text(encoding='utf-8').strip()}\n```")
    return "\n\n".join(chunks)


def load_translation_memory(novel: str) -> str:
    path = novel_dir(novel) / "translation_memory" / "phrases.jsonl"
    if not path.exists():
        return ""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return "\n".join(lines)


def load_style_guide(novel: str) -> str:
    cfg = load_novel_config(novel)
    path = novel_dir(novel) / cfg.get("style_guide", "style_guide.md")
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_prompt(name: str) -> str:
    return (REPO_ROOT / "prompts" / name).read_text(encoding="utf-8")


def assemble_translation_context(novel: str, chapter: int, previous_chapters: int) -> str:
    """Build the full user-message context block for the translation pass."""
    cfg = load_novel_config(novel)
    parts: list[str] = []

    parts.append(f"## Novel\n{cfg.get('title_english', novel)} "
                 f"(source language: {cfg.get('source_language', 'zh')})")

    style = load_style_guide(novel)
    if style:
        parts.append(f"## Style guide\n{style}")

    records = load_context_records(novel)
    if records:
        parts.append(f"## Canonical context records\n{records}")

    tm = load_translation_memory(novel)
    if tm:
        parts.append("## Translation memory (idioms/jokes already seen - do NOT re-explain these)\n"
                     f"```jsonl\n{tm}\n```")

    prevs = previous_translations(novel, chapter, previous_chapters)
    if prevs:
        blocks = [f"### Chapter {num}\n{text}" for num, text in prevs]
        parts.append("## Previous translated chapters (for voice and continuity)\n"
                     + "\n\n".join(blocks))

    parts.append(f"## Source chapter to translate (chapter {chapter})\n"
                 f"```\n{read_source(novel, chapter)}\n```")

    return "\n\n".join(parts)

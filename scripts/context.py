"""Context retrieval and assembly (pipeline pass 1).

Mechanical, no LLM: given a novel and a target chapter, gather everything the translator should see
before it starts - style guide, canonical context records, the previous N translated chapters, and
the translation memory of already-seen phrases - and stitch it into one prompt block.

Language independence: file naming and the language-specific prompt overlay are derived from the
novel's `source_language` / `target_language` (see novel.yaml), not hardcoded to Chinese. The core
here is language-neutral; Chinese-specific guidance lives in prompts/languages/<lang>.md.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
NOVELS_DIR = REPO_ROOT / "novels"

# Fallback language codes when a novel.yaml omits them. Not an assumption that source is always zh:
# every novel declares its own pair, and these only fill in for a malformed/missing config.
DEFAULT_SOURCE_LANGUAGE = "zh"
DEFAULT_TARGET_LANGUAGE = "en"

# Preferred display order for the generic context files. Any other *.yaml present in a novel's
# context/ dir (genre-specific ones like cultivation_system.yaml, honorifics.yaml, magic_system.yaml)
# is still loaded, appended after these in alphabetical order. Nothing here assumes a genre.
PREFERRED_CONTEXT_ORDER = [
    "characters.yaml",
    "terminology.yaml",
    "locations.yaml",
    "factions.yaml",
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
        return {"source_language": DEFAULT_SOURCE_LANGUAGE, "target_language": DEFAULT_TARGET_LANGUAGE}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def source_language(novel: str) -> str:
    return load_novel_config(novel).get("source_language", DEFAULT_SOURCE_LANGUAGE)


def target_language(novel: str) -> str:
    return load_novel_config(novel).get("target_language", DEFAULT_TARGET_LANGUAGE)


def source_path(novel: str, chapter: int) -> Path:
    """Source file, named by the novel's source language, e.g. ch0001_zh.txt or ch0001_ko.txt."""
    return novel_dir(novel) / "source" / f"ch{chapter:04d}_{source_language(novel)}.txt"


def translated_path(novel: str, chapter: int) -> Path:
    """Translated file, named by the novel's target language, e.g. ch0001_en.md."""
    return novel_dir(novel) / "translated" / f"ch{chapter:04d}_{target_language(novel)}.md"


def read_source(novel: str, chapter: int) -> str:
    path = source_path(novel, chapter)
    if not path.exists():
        raise FileNotFoundError(f"Missing source chapter: {path}")
    return path.read_text(encoding="utf-8")


def list_translated_chapters(novel: str) -> list[Path]:
    """All translated chapter files for the novel, in chapter order (language-derived suffix)."""
    translated = novel_dir(novel) / "translated"
    return sorted(translated.glob(f"ch*_{target_language(novel)}.md"))


def previous_translations(novel: str, chapter: int, n: int) -> list[tuple[int, str]]:
    """Return up to n most recent already-translated chapters before `chapter`, oldest first."""
    out: list[tuple[int, str]] = []
    for prev in range(max(1, chapter - n), chapter):
        path = translated_path(novel, prev)
        if path.exists():
            out.append((prev, path.read_text(encoding="utf-8")))
    return out


def context_files(novel: str) -> list[Path]:
    """Every context YAML present for the novel, preferred generic files first, then any extras.

    Loading whatever *.yaml exists (rather than a fixed list) keeps the core genre- and
    language-agnostic: a novel can add cultivation_system.yaml, honorifics.yaml, magic_system.yaml,
    etc. without a code change.
    """
    ctx_dir = novel_dir(novel) / "context"
    if not ctx_dir.is_dir():
        return []
    present = [p for p in ctx_dir.glob("*.yaml") if not p.name.startswith("_")]

    def sort_key(p: Path):
        try:
            return (0, PREFERRED_CONTEXT_ORDER.index(p.name))
        except ValueError:
            return (1, p.name)

    return sorted(present, key=sort_key)


def load_context_records(novel: str) -> str:
    """Concatenate the novel's context YAML files into one labelled block."""
    chunks: list[str] = []
    for path in context_files(novel):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            chunks.append(f"### {path.name}\n```yaml\n{text}\n```")
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


def load_language_prompt(lang: str) -> str:
    """Language-specific translation guidance overlay, if one exists (prompts/languages/<lang>.md).

    This is where source-language linguistics live (Chinese chengyu/homophones/classical refs for
    zh, Korean honorifics/hanja for ko later). The core prompt stays language-neutral; missing
    overlay is fine.
    """
    path = REPO_ROOT / "prompts" / "languages" / f"{lang}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def assemble_translation_context(novel: str, chapter: int, previous_chapters: int) -> str:
    """Build the full user-message context block for the translation pass."""
    cfg = load_novel_config(novel)
    parts: list[str] = []

    parts.append(f"## Novel\n{cfg.get('title_english', novel)} "
                 f"(source language: {cfg.get('source_language', DEFAULT_SOURCE_LANGUAGE)}, "
                 f"target language: {cfg.get('target_language', DEFAULT_TARGET_LANGUAGE)})")

    style = load_style_guide(novel)
    if style:
        parts.append(f"## Style guide\n{style}")

    records = load_context_records(novel)
    if records:
        parts.append(f"## Canonical context records\n{records}")

    tm = load_translation_memory(novel)
    if tm:
        parts.append("## Translation memory (phrases/jokes already seen - do NOT re-explain these)\n"
                     f"```jsonl\n{tm}\n```")

    prevs = previous_translations(novel, chapter, previous_chapters)
    if prevs:
        blocks = [f"### Chapter {num}\n{text}" for num, text in prevs]
        parts.append("## Previous translated chapters (for voice and continuity)\n"
                     + "\n\n".join(blocks))

    parts.append(f"## Source chapter to translate (chapter {chapter})\n"
                 f"```\n{read_source(novel, chapter)}\n```")

    return "\n\n".join(parts)

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


class ConfigError(ValueError):
    """A novel's configuration is missing or invalid (e.g. no declared language pair)."""

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


def display_path(path: Path) -> str:
    """A short, human-friendly form of `path` for logs, robust to paths outside the repo.

    Novels can live anywhere (and tests use temp dirs), so never assume a path is under REPO_ROOT.
    """
    for base in (NOVELS_DIR, REPO_ROOT):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)


def novel_dir(novel: str) -> Path:
    path = NOVELS_DIR / novel
    if not path.is_dir():
        raise FileNotFoundError(f"No such novel: {path}")
    return path


def load_novel_config(novel: str) -> dict:
    """Read novel.yaml. A novel MUST have one; there is no silent default configuration."""
    path = novel_dir(novel) / "novel.yaml"
    if not path.exists():
        raise ConfigError(
            f"novel '{novel}': novel.yaml is missing. Every novel must declare its language pair, "
            "e.g.\n  source_language: zh\n  target_language: en"
        )
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _require_language(novel: str, field: str) -> str:
    """Return a validated, non-empty language code from novel.yaml, or raise ConfigError.

    Wenmai is a multilingual framework: it never assumes Chinese (or any language). A real novel
    must state its languages explicitly.
    """
    example = "zh" if field == "source_language" else "en"
    value = load_novel_config(novel).get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"novel '{novel}': novel.yaml must define a non-empty '{field}' (e.g. "
            f"`{field}: {example}`). Wenmai does not assume a default language."
        )
    return value.strip()


def source_language(novel: str) -> str:
    return _require_language(novel, "source_language")


def target_language(novel: str) -> str:
    return _require_language(novel, "target_language")


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


def assemble_translation_context(
    novel: str,
    chapter: int,
    previous_chapters: int,
    *,
    include_previous: bool = True,
    include_context: bool = True,
    include_translation_memory: bool = True,
) -> str:
    """Build the user-message context block for the translation pass.

    The header, style guide, and source chapter are always included. The three toggles gate the
    optional context so the benchmark can build its A/B/C conditions from this one assembler,
    guaranteeing identical formatting across conditions:
      - include_previous: the previous N translated chapters (rolling window)
      - include_context: the canonical context/*.yaml records
      - include_translation_memory: the translation-memory phrases
    The normal pipeline uses the defaults (all on).
    """
    cfg = load_novel_config(novel)
    parts: list[str] = []

    parts.append(f"## Novel\n{cfg.get('title_english', novel)} "
                 f"(source language: {source_language(novel)}, "
                 f"target language: {target_language(novel)})")

    style = load_style_guide(novel)
    if style:
        parts.append(f"## Style guide\n{style}")

    if include_context:
        records = load_context_records(novel)
        if records:
            parts.append(f"## Canonical context records\n{records}")

    if include_translation_memory:
        tm = load_translation_memory(novel)
        if tm:
            parts.append(
                "## Translation memory (phrases/jokes already seen - do NOT re-explain these)\n"
                f"```jsonl\n{tm}\n```")

    if include_previous:
        prevs = previous_translations(novel, chapter, previous_chapters)
        if prevs:
            blocks = [f"### Chapter {num}\n{text}" for num, text in prevs]
            parts.append("## Previous translated chapters (for voice and continuity)\n"
                         + "\n\n".join(blocks))

    parts.append(f"## Source chapter to translate (chapter {chapter})\n"
                 f"```\n{read_source(novel, chapter)}\n```")

    return "\n\n".join(parts)

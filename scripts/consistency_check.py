"""Terminology-drift checker (pipeline pass 3, and a standalone tool).

Pure Python, no LLM. Reads the `avoid` lists from the context files and scans translated chapters
for any banned variant. This is what catches "Heavenly Origin Sword Art" in ch20 turning into
"Celestial Source Sword Technique" in ch400.

Run standalone across a whole novel:
    python scripts/consistency_check.py --novel sample-novel

Or check one chapter (used as pass 3 by translate.py):
    python scripts/consistency_check.py --novel sample-novel --chapter 1
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

import yaml

try:
    from . import context as ctx
except ImportError:
    import context as ctx  # type: ignore


@dataclass
class Finding:
    chapter_file: str
    line_no: int
    banned: str
    preferred: str
    line: str


def _walk_avoid_entries(node):
    """Recursively yield (preferred, [banned...]) from any dict that carries an `avoid` list.

    Structure-agnostic: it does not care which file, top-level key, genre, or nesting an entry
    lives in, so new context files (any language, any genre) work with no code change. An entry is
    any dict with an `avoid` list; its canonical form is `preferred` or `english`.
    """
    if isinstance(node, dict):
        avoid = node.get("avoid")
        if isinstance(avoid, list) and avoid:
            preferred = node.get("preferred") or node.get("english") or "?"
            yield preferred, [b for b in avoid if isinstance(b, str)]
        for value in node.values():
            yield from _walk_avoid_entries(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_avoid_entries(item)


def _iter_avoid_pairs(novel: str):
    """Yield (preferred, banned_variant) pairs from every context YAML the novel has."""
    for path in ctx.context_files(novel):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for preferred, banned_list in _walk_avoid_entries(data):
            for banned in banned_list:
                yield preferred, banned


def check_text(text: str, chapter_file: str, avoid_pairs) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for preferred, banned in avoid_pairs:
            # Word-boundary, case-insensitive match for ASCII variants; substring match for
            # non-ASCII scripts (Chinese, Hangul, etc.) where word boundaries do not apply.
            if banned.isascii():
                pattern = r"\b" + re.escape(banned) + r"\b"
                hit = re.search(pattern, line, re.IGNORECASE)
            else:
                hit = banned in line
            if hit:
                findings.append(Finding(chapter_file, line_no, banned, preferred, line.strip()))
    return findings


def check_novel(novel: str, chapter: int | None = None) -> list[Finding]:
    avoid_pairs = list(_iter_avoid_pairs(novel))
    if chapter is not None:
        files = [ctx.translated_path(novel, chapter)]
    else:
        files = ctx.list_translated_chapters(novel)

    findings: list[Finding] = []
    for path in files:
        if not path.exists():
            continue
        findings.extend(check_text(path.read_text(encoding="utf-8"), path.name, avoid_pairs))
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # print CJK safely on Windows consoles
    ap = argparse.ArgumentParser(description="Terminology-drift checker.")
    ap.add_argument("--novel", required=True)
    ap.add_argument("--chapter", type=int, default=None, help="Check one chapter; default is all.")
    args = ap.parse_args()

    findings = check_novel(args.novel, args.chapter)
    if not findings:
        print(f"[consistency] OK - no banned variants found in {args.novel}.")
        return 0

    print(f"[consistency] {len(findings)} drift issue(s) in {args.novel}:")
    for f in findings:
        print(f"  {f.chapter_file}:{f.line_no}  '{f.banned}' -> use '{f.preferred}'")
        print(f"      {f.line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

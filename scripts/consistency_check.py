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
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
NOVELS_DIR = REPO_ROOT / "novels"

# context file -> top-level key holding the mapping of entries
AVOID_SOURCES = {
    "terminology.yaml": "terms",
    "locations.yaml": "locations",
    "factions.yaml": "factions",
    "cultivation_system.yaml": None,  # nested; handled specially
}


@dataclass
class Finding:
    chapter_file: str
    line_no: int
    banned: str
    preferred: str
    line: str


def _iter_avoid_pairs(novel: str):
    """Yield (preferred, banned_variant) pairs from the novel's context files."""
    ctx = NOVELS_DIR / novel / "context"

    for fname, key in AVOID_SOURCES.items():
        path = ctx / fname
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        if fname == "cultivation_system.yaml":
            for section in ("realms", "techniques", "concepts"):
                block = data.get(section)
                if isinstance(block, dict):
                    entries = block.values()
                elif isinstance(block, list):
                    entries = block
                else:
                    continue
                for entry in entries:
                    if isinstance(entry, dict):
                        preferred = entry.get("english") or entry.get("preferred") or "?"
                        for banned in entry.get("avoid", []) or []:
                            yield preferred, banned
            continue

        entries = data.get(key, {}) or {}
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            preferred = entry.get("preferred") or entry.get("english") or "?"
            for banned in entry.get("avoid", []) or []:
                yield preferred, banned


def check_text(text: str, chapter_file: str, avoid_pairs) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for preferred, banned in avoid_pairs:
            # Word-boundary match, case-insensitive, for latin variants; plain substring for CJK.
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
    translated = NOVELS_DIR / novel / "translated"
    if chapter is not None:
        files = [translated / f"ch{chapter:04d}_en.md"]
    else:
        files = sorted(translated.glob("ch*_en.md"))

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

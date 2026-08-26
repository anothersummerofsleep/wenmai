"""Light state validator for a novel's persistent stores.

Catches useful classes of corruption before they silently poison prompts, without turning the
open-ended context model into a rigid schema. It is STRUCTURAL: it checks YAML/JSONL validity, the
required language configuration, basic field types (`avoid` is a list of strings, `aliases` is a
list, etc.), well-formed translation-memory lines, and safely-detectable duplicate canonical
renderings within a file. It does not prescribe which keys a context file must contain.

Chapter filename convention (V1): source and translated files are named

    ch<NNNNN>_<language>.txt   e.g. ch00001_zh.txt     (source, language = source_language)
    ch<NNNNN>_<language>.md    e.g. ch00001_en.md      (translation, language = target_language)

where <NNNNN> is a zero-padded 5-digit chapter number. Files that look like chapters but do not
match are flagged (the pipeline resolves chapters by this exact pattern; it does not do arbitrary
filename ingestion).

Usage:
    python scripts/validate.py --novel sample-novel
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass

import yaml

try:
    from . import context
except ImportError:
    import context  # type: ignore

# Chapter filename patterns. Canonical is 5 digits; allow 5+ so chapters above 99999 still parse.
# <lang> = 2-3 lowercase letters.
SOURCE_NAME_RE = re.compile(r"^ch(\d{5,})_([a-z]{2,3})\.txt$")
TRANSLATED_NAME_RE = re.compile(r"^ch(\d{5,})_([a-z]{2,3})\.md$")
CHAPTERISH_RE = re.compile(r"^ch.*\.(txt|md)$", re.IGNORECASE)


@dataclass
class Issue:
    file: str          # path relative to the novel, e.g. "context/characters.yaml"
    locator: str       # record key path or "line N", or "" if whole-file
    message: str
    severity: str      # "error" or "warning"

    def __str__(self) -> str:
        where = f"{self.file}" + (f" [{self.locator}]" if self.locator else "")
        return f"  {self.severity.upper():7} {where}: {self.message}"


def _walk(node, path: str):
    """Yield (path, dict) for every mapping in the structure, with a dotted locator path."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk(value, child)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")


def _check_types(data, rel: str, issues: list[Issue]) -> None:
    """Structural field-type checks over an open-ended mapping (no required-keys schema)."""
    canonical_seen: dict[str, str] = {}   # canonical rendering -> first locator (within this file)
    source_seen: dict[str, str] = {}      # source token -> first locator (within this file)

    for path, node in _walk(data, ""):
        if "avoid" in node:
            avoid = node["avoid"]
            if not isinstance(avoid, list) or not all(isinstance(x, str) for x in avoid):
                issues.append(Issue(rel, path, "'avoid' must be a list of strings", "error"))
        if "aliases" in node and not isinstance(node["aliases"], list):
            issues.append(Issue(rel, path, "'aliases' must be a list", "error"))
        for field in ("preferred", "english", "source"):
            if field in node and not isinstance(node[field], (str, int)):
                issues.append(Issue(rel, path, f"'{field}' should be a string", "warning"))

        canonical = node.get("preferred") or node.get("english")
        if isinstance(canonical, str) and canonical.strip():
            if canonical in canonical_seen:
                issues.append(Issue(
                    rel, path,
                    f"canonical rendering {canonical!r} also defined at "
                    f"{canonical_seen[canonical]!r} (possible duplicate/conflict)", "warning"))
            else:
                canonical_seen[canonical] = path
        src = node.get("source")
        if isinstance(src, str) and src.strip():
            if src in source_seen:
                issues.append(Issue(
                    rel, path,
                    f"source token {src!r} also defined at {source_seen[src]!r} "
                    "(possible duplicate/conflict)", "warning"))
            else:
                source_seen[src] = path


def _validate_languages(novel: str, issues: list[Issue]) -> tuple[str | None, str | None]:
    src = tgt = None
    for field, sink in (("source_language", "src"), ("target_language", "tgt")):
        try:
            value = context._require_language(novel, field)
        except context.ConfigError as err:
            issues.append(Issue("novel.yaml", field, str(err).splitlines()[0], "error"))
        else:
            if sink == "src":
                src = value
            else:
                tgt = value
    return src, tgt


def _validate_context_files(novel: str, issues: list[Issue]) -> None:
    for path in context.context_files(novel):
        rel = f"context/{path.name}"
        raw = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as err:
            mark = getattr(err, "problem_mark", None)
            loc = f"line {mark.line + 1}" if mark else ""
            issues.append(Issue(rel, loc, f"invalid YAML: {getattr(err, 'problem', err)}", "error"))
            continue
        if data is None:
            continue
        if not isinstance(data, (dict, list)):
            issues.append(Issue(rel, "", "top-level YAML should be a mapping or list", "error"))
            continue
        _check_types(data, rel, issues)


def _validate_translation_memory(novel: str, issues: list[Issue]) -> None:
    path = context.novel_dir(novel) / "translation_memory" / "phrases.jsonl"
    if not path.exists():
        return
    rel = "translation_memory/phrases.jsonl"
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as err:
            issues.append(Issue(rel, f"line {lineno}", f"invalid JSON: {err.msg}", "error"))
            continue
        if not isinstance(obj, dict):
            issues.append(Issue(rel, f"line {lineno}", "each line must be a JSON object", "error"))
            continue
        src = obj.get("source")
        if not (isinstance(src, str) and src.strip()):
            issues.append(Issue(rel, f"line {lineno}", "missing or empty 'source' field", "error"))
        for field in ("gloss", "kind", "handling", "note_text"):
            if field in obj and not isinstance(obj[field], str):
                issues.append(Issue(rel, f"line {lineno}", f"'{field}' should be a string", "warning"))


def _validate_filenames(novel: str, src: str | None, tgt: str | None, issues: list[Issue]) -> None:
    base = context.novel_dir(novel)
    for sub, name_re, lang, kind in (
        ("source", SOURCE_NAME_RE, src, "source"),
        ("translated", TRANSLATED_NAME_RE, tgt, "translation"),
    ):
        d = base / sub
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            m = name_re.match(f.name)
            if m:
                if lang and m.group(2) != lang:
                    issues.append(Issue(f"{sub}/{f.name}", "", (
                        f"{kind} language '{m.group(2)}' does not match novel.yaml "
                        f"({'source_language' if kind=='source' else 'target_language'}='{lang}')"
                    ), "warning"))
                continue
            if CHAPTERISH_RE.match(f.name):
                expect = f"ch<NNNNN>_{lang or '<lang>'}.{'txt' if kind=='source' else 'md'}"
                issues.append(Issue(f"{sub}/{f.name}", "",
                                    f"filename does not match the chapter convention {expect}",
                                    "warning"))


# Canonical serialized first_seen form for benchmark state: exactly chNNNNN (5+ digits).
# The internal parser (context._first_seen_chapter) stays permissive for general use; benchmark
# validation demands the canonical serialization so bounding never depends on lenient parsing.
FIRST_SEEN_CANONICAL_RE = re.compile(r"^ch\d{5,}$")


def _first_seen_ok(value) -> bool:
    """True if `first_seen` is in the canonical serialized form chNNNNN (e.g. 'ch00001')."""
    return isinstance(value, str) and bool(FIRST_SEEN_CANONICAL_RE.match(value))


def _validate_first_seen(novel: str, issues: list[Issue]) -> None:
    """Every durable record must carry a canonical `first_seen` so chapter-bounding can apply.

    Structural, not a rigid schema: a "record" is a direct child entry of a top-level category
    mapping, or a mapping item in a top-level list. Nested sub-mappings (relationships, etc.) are not
    required to carry first_seen. This underpins the benchmark's chapter-bounded-knowledge invariant.
    The value must match ^ch\\d{5,}$ exactly (canonical serialization), not merely be parsable.
    """
    for path in context.context_files(novel):
        rel = f"context/{path.name}"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue  # already reported by _validate_context_files
        if not isinstance(data, dict):
            continue
        for category, entries in data.items():
            records = []
            if isinstance(entries, dict):
                records = [(f"{category}.{k}", v) for k, v in entries.items()]
            elif isinstance(entries, list):
                records = [(f"{category}[{i}]", v) for i, v in enumerate(entries)]
            for locator, rec in records:
                if not isinstance(rec, dict):
                    continue
                if "first_seen" not in rec:
                    issues.append(Issue(rel, locator, "record is missing 'first_seen' "
                                        "(required for chapter-bounding; use chNNNNN)", "error"))
                elif not _first_seen_ok(rec.get("first_seen")):
                    issues.append(Issue(rel, locator, f"non-canonical 'first_seen' "
                                        f"{rec.get('first_seen')!r} (must match chNNNNN, "
                                        "e.g. ch00001)", "error"))

    tm = context.novel_dir(novel) / "translation_memory" / "phrases.jsonl"
    if tm.exists():
        rel = "translation_memory/phrases.jsonl"
        for lineno, line in enumerate(tm.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # already reported by _validate_translation_memory
            if not isinstance(obj, dict):
                continue
            if not _first_seen_ok(obj.get("first_seen")):
                issues.append(Issue(rel, f"line {lineno}", "missing or non-canonical 'first_seen' "
                                    "(must match chNNNNN, e.g. ch00001)", "error"))


def validate_novel(novel: str, *, require_first_seen: bool = False) -> list[Issue]:
    """Return all structural issues found in the novel's persistent state (empty = clean).

    `require_first_seen` adds the stricter benchmark check that every durable record carries a
    parsable `first_seen`. Off by default so general (non-benchmark) novels stay lenient.
    """
    issues: list[Issue] = []
    src, tgt = _validate_languages(novel, issues)
    _validate_context_files(novel, issues)
    _validate_translation_memory(novel, issues)
    _validate_filenames(novel, src, tgt, issues)
    if require_first_seen:
        _validate_first_seen(novel, issues)
    return issues


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Validate a novel's persistent state.")
    ap.add_argument("--novel", required=True)
    ap.add_argument("--require-first-seen", action="store_true",
                    help="also require a parsable first_seen on every durable record (benchmark).")
    args = ap.parse_args()

    try:
        issues = validate_novel(args.novel, require_first_seen=args.require_first_seen)
    except FileNotFoundError as err:
        print(f"[error] {err}")
        return 1

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    if not issues:
        print(f"[validate] OK - {args.novel} has no state issues.")
        return 0

    print(f"[validate] {args.novel}: {len(errors)} error(s), {len(warnings)} warning(s)")
    for issue in issues:
        print(issue)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

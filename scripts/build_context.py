"""Context-extraction pass: propose new notebook entries from a chapter.

Runs the extraction prompt over the ORIGINAL source chapter plus its finished translation (and the
existing canon) and writes the model's proposed YAML additions to
`novels/<novel>/context/_proposals/ch<NNNNN>.yaml` for human review. It never edits either persistent
store directly - a human applies accepted entries (that is the reviewable diff).

Proposals separate the two stores (see prompts/context_update.md):
  - canonical keys (characters, terms, locations, factions, timeline, ...) -> context/<key>.yaml
  - a `translation_memory:` list -> appended as JSON lines to translation_memory/phrases.jsonl

Usage:
    python scripts/build_context.py --novel sample-novel --chapter 1
"""
from __future__ import annotations

import argparse
import sys

try:
    from . import backends, context
except ImportError:
    import backends, context  # type: ignore


def strip_single_outer_fence(text: str) -> str:
    """If the WHOLE extraction response is one Markdown code fence, return its inner content.

    Only for the proposal/extraction layer: some models wrap a YAML proposal in ```yaml ... ```.
    Strips exactly one outer fence, and only when the entire response is that single fenced block
    (opening ```yaml / ```yml / bare ```, closing ```, nothing outside it, no other fence inside).
    Anything else is returned unchanged. Never used on translation candidates - a candidate's stray
    fence is a real benchmark outcome that deterministic evaluation must keep catching.
    """
    stripped = text.strip()
    lines = stripped.splitlines()
    if len(lines) < 2:
        return text
    if lines[0].strip() not in ("```", "```yaml", "```yml"):
        return text
    if lines[-1].strip() != "```":
        return text
    inner = lines[1:-1]
    if any(ln.strip().startswith("```") for ln in inner):  # surrounding/other fences: leave alone
        return text
    return "\n".join(inner)


def run(novel: str, chapter: int, backend_name: str | None, translation_path=None) -> int:
    # translation_path lets a caller (e.g. the benchmark) point extraction at a specific translation
    # for this chapter - Condition C's output for the run - instead of the novel's translated/ dir.
    translated_path = translation_path or context.translated_path(novel, chapter)
    if not translated_path.exists():
        print(f"[error] no translated chapter at {context.display_path(translated_path)}. "
              "Translate it first.")
        return 1

    config = backends.load_config()
    backend = backends.get_backend(backend_name, config)

    # Give the extraction model all three: existing canon, the ORIGINAL source (so source-language
    # terms, names, idioms, and `source:` values are recovered from the source rather than
    # reconstructed from English), and the finished translation. Source path derives from the
    # novel's source_language; nothing is hardcoded to Chinese.
    system = context.load_prompt("context_update.md")
    user_parts = [
        "## Existing canonical context (do not restate what is already here)",
        context.load_context_records(novel),
        f"## Original source chapter ({context.source_language(novel)})",
        context.read_source(novel, chapter),
        "## Finished translation",
        translated_path.read_text(encoding="utf-8"),
    ]
    user = "\n\n".join(user_parts)

    print(f"[extract] proposing context updates from {novel} {context.chapter_id(chapter)} "
          f"via '{backend.name}'...")
    tag = f"{novel}/{context.chapter_id(chapter)}/context_update"
    try:
        proposal = backend.complete(system, user, tag=tag)
    except backends.PendingHandoff as handoff:
        print(str(handoff))
        return 2

    proposals_dir = context.novel_dir(novel) / "context" / "_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    out = proposals_dir / f"{context.chapter_id(chapter)}.yaml"
    out.write_text(strip_single_outer_fence(proposal).rstrip() + "\n", encoding="utf-8")
    print(f"[extract] wrote proposals to {context.display_path(out)}")
    print("Review it, then apply accepted entries by hand: canonical keys -> context/<key>.yaml; "
          "any `translation_memory` list -> appended as JSON lines to "
          "translation_memory/phrases.jsonl.")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # print CJK safely on Windows consoles
    ap = argparse.ArgumentParser(description="Propose context updates from a translated chapter.")
    ap.add_argument("--novel", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--backend", default=None)
    args = ap.parse_args()
    try:
        return run(args.novel, args.chapter, args.backend)
    except (FileNotFoundError, ValueError, RuntimeError) as err:
        print(f"[error] {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Chapter translation orchestrator (v1 three-pass pipeline).

    pass 1  context retrieval   (Python, mechanical)  -> assemble the prompt
    pass 2  translate + annotate (LLM, via backend)   -> produce English Markdown
    pass 3  consistency check    (Python, mechanical)  -> flag terminology drift

Usage:
    python scripts/translate.py --novel sample-novel --chapter 1
    python scripts/translate.py --novel sample-novel --chapter 2 --backend anthropic
    python scripts/translate.py --novel sample-novel --chapter 1 --force   # overwrite existing

Default backend is `claude_code` (file handoff): the first run writes a prompt and stops with
instructions; fill the response file, re-run to finish.
"""
from __future__ import annotations

import argparse
import sys

# Allow running as `python scripts/translate.py` or `python -m scripts.translate`.
try:
    from . import backends, context, consistency_check
except ImportError:
    import backends, context, consistency_check  # type: ignore


def run(novel: str, chapter: int, backend_name: str | None, force: bool) -> int:
    out_path = context.translated_path(novel, chapter)
    if out_path.exists() and not force:
        print(f"[skip] {out_path.relative_to(context.REPO_ROOT)} already exists. Use --force to redo.")
        return 0

    config = backends.load_config()
    prev_n = int(config.get("retrieval", {}).get("previous_chapters", 2))
    backend = backends.get_backend(backend_name, config)

    # Pass 1: assemble context.
    print(f"[pass 1] retrieving context for {novel} ch{chapter:04d} "
          f"(+{prev_n} previous chapters)...")
    src_lang = context.source_language(novel)
    tgt_lang = context.target_language(novel)
    system = (context.load_prompt("translate.md")
              .replace("{SOURCE_LANGUAGE}", src_lang)
              .replace("{TARGET_LANGUAGE}", tgt_lang)
              .replace("{N}", str(prev_n)))
    # Append language-specific linguistic guidance if an overlay exists for this source language.
    overlay = context.load_language_prompt(src_lang)
    if overlay:
        system += f"\n\n---\n\n# Source-language guidance ({src_lang})\n\n{overlay}"
    user = context.assemble_translation_context(novel, chapter, prev_n)

    # Pass 2: translate + annotate.
    print(f"[pass 2] translating via '{backend.name}' backend...")
    tag = f"{novel}/ch{chapter:04d}/translate"
    try:
        translated = backend.complete(system, user, tag=tag)
    except backends.PendingHandoff as handoff:
        print(str(handoff))
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(translated.rstrip() + "\n", encoding="utf-8")
    print(f"[pass 2] wrote {out_path.relative_to(context.REPO_ROOT)}")

    # Pass 3: consistency check on the new chapter.
    print("[pass 3] consistency check...")
    findings = consistency_check.check_novel(novel, chapter)
    if findings:
        print(f"[pass 3] {len(findings)} terminology drift issue(s):")
        for f in findings:
            print(f"    {f.chapter_file}:{f.line_no}  '{f.banned}' -> use '{f.preferred}'")
    else:
        print("[pass 3] OK - no terminology drift.")

    print("\nDone. Next: review the diff, then "
          f"`python scripts/build_context.py --novel {novel} --chapter {chapter}` "
          "to propose new context entries.")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # print CJK safely on Windows consoles
    ap = argparse.ArgumentParser(description="Translate one chapter through the v1 pipeline.")
    ap.add_argument("--novel", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--backend", default=None, help="Override config: claude_code | anthropic")
    ap.add_argument("--force", action="store_true", help="Overwrite an existing translation.")
    args = ap.parse_args()
    try:
        return run(args.novel, args.chapter, args.backend, args.force)
    except (FileNotFoundError, ValueError, RuntimeError) as err:
        print(f"[error] {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

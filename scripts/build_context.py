"""Context-extraction pass: propose new notebook entries from a finished chapter.

Runs the extraction prompt over a translated chapter and writes the model's proposed YAML additions
to `novels/<novel>/context/_proposals/ch<NNNN>.yaml` for human review. It never edits the canonical
context files directly - you merge approved entries in yourself (that is the reviewable diff).

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


def run(novel: str, chapter: int, backend_name: str | None) -> int:
    translated_path = context.translated_path(novel, chapter)
    if not translated_path.exists():
        print(f"[error] no translated chapter at {translated_path}. Translate it first.")
        return 1

    config = backends.load_config()
    backend = backends.get_backend(backend_name, config)

    system = context.load_prompt("context_update.md")
    user_parts = [
        "## Existing canonical context (do not restate what is already here)",
        context.load_context_records(novel),
        "## Newly translated chapter to extract from",
        translated_path.read_text(encoding="utf-8"),
    ]
    user = "\n\n".join(user_parts)

    print(f"[extract] proposing context updates from {novel} ch{chapter:04d} "
          f"via '{backend.name}'...")
    tag = f"{novel}/ch{chapter:04d}/context_update"
    try:
        proposal = backend.complete(system, user, tag=tag)
    except backends.PendingHandoff as handoff:
        print(str(handoff))
        return 2

    proposals_dir = context.novel_dir(novel) / "context" / "_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    out = proposals_dir / f"ch{chapter:04d}.yaml"
    out.write_text(proposal.rstrip() + "\n", encoding="utf-8")
    print(f"[extract] wrote proposals to {out.relative_to(context.REPO_ROOT)}")
    print("Review it, then merge approved entries into the real context/*.yaml files by hand.")
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

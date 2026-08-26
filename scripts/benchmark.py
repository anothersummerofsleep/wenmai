"""Controlled translation benchmark: compare context strategies on a local corpus.

This tests Wenmai's core thesis: does structured persistent narrative memory improve translation
beyond giving a capable model a rolling window of recent chapters? It compares three generation
conditions per chapter, using the SAME backend/model/settings and the SAME assembler for all three
(only the included context differs):

  A  chapter-only     : core prompt + source-language overlay + style guide + source chapter.
  B  rolling-context  : A + the previous N translated chapters (rolling window).
  C  full Wenmai      : B + canonical context/*.yaml + translation memory.

Default mode is `independent`: B accumulates and retrieves only B's own prior translations, C only
C's. This is a true end-to-end comparison of a rolling-context translator vs full Wenmai, including
how decisions and mistakes propagate over time within each system. An optional `shared_c` mode gives
B and C the same window (C's history) as a controlled per-chapter ablation of structured memory.

C's state-update protocol (V1, human-in-the-loop):
    source chapter + C's translation + existing C state  ->  extraction proposal  ->  HUMAN review
    ->  accepted canonical context/*.yaml + translation_memory  ->  used for the next chapter.
The harness accumulates C's translated history automatically; the canonical context and translation
memory are curated by a human into the state novel between chapters (not auto-applied).

The official reference translation NEVER participates in context generation, state curation,
translation prompting, or style-guide construction. It is consulted only after blind scoring, for
post-hoc comparison. See benchmarks/README.md for the full methodology and its known caveats.

Copyright: benchmark source text, the official reference translation, and generated candidates all
live under .local/ (git-ignored) and never enter the public repo. Only code, the manifest, and
aggregate result summaries are public. The reference translation is an evaluation aid only and is
NEVER placed in the prompts that produce A/B/C.

Local layout (all git-ignored):
    .local/benchmarks/<id>/
      state/            a normal Wenmai novel: novel.yaml, style_guide.md, source/, context/,
                        translation_memory/, translated/ (C's accumulating outputs)
      reference/        official translation, chNNNNN_<tgt>.md (eval only, never prompted)
      runs/<run_id>/    blinded candidates + eval templates + deterministic scores + analysis

Usage:
    python scripts/benchmark.py check    --benchmark lotm
    python scripts/benchmark.py generate --benchmark lotm --chapters 1-10 --run r1
    python scripts/benchmark.py evaluate --benchmark lotm --run r1            # writes blank templates
    python scripts/benchmark.py analyze  --benchmark lotm --run r1            # unblind + aggregate
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime

import yaml

try:
    from . import backends, build_context, consistency_check, context, translate, validate
except ImportError:
    import backends, build_context, consistency_check, context, translate, validate  # type: ignore

# The nine evaluation dimensions. All scored 1-5 where 5 is best; for
# hallucination_or_embellishment, 5 means "no unsupported additions".
EVAL_DIMENSIONS = [
    "faithfulness",
    "contextual_correctness",
    "terminology_consistency",
    "character_voice_consistency",
    "english_prose_quality",
    "wordplay_preservation",
    "annotation_precision",
    "annotation_restraint",
    "hallucination_or_embellishment",
]

# Which optional context each condition receives. Order matters: generate A, B, C so C's writeback
# is available as the shared window for the next chapter.
CONDITIONS = {
    "A": dict(include_previous=False, include_context=False, include_translation_memory=False),
    "B": dict(include_previous=True, include_context=False, include_translation_memory=False),
    "C": dict(include_previous=True, include_context=True, include_translation_memory=True),
}

STATE_NOVEL = "state"


# --------------------------------------------------------------------------- paths / manifest

def local_root(bid: str):
    return context.REPO_ROOT / ".local" / "benchmarks" / bid


def manifest_path(bid: str):
    return context.REPO_ROOT / "benchmarks" / bid / "manifest.yaml"


def load_manifest(bid: str) -> dict:
    path = manifest_path(bid)
    if not path.exists():
        raise FileNotFoundError(
            f"No benchmark manifest at {context.display_path(path)}. "
            f"Create benchmarks/{bid}/manifest.yaml (metadata only, no chapter prose)."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _use_state_novel(bid: str) -> str:
    """Point the context layer at this benchmark's local state novel and return its name.

    The state novel dir is <local_root>/state, so NOVELS_DIR is its parent (the benchmark root).
    """
    context.NOVELS_DIR = local_root(bid)
    return STATE_NOVEL


def parse_chapters(spec: str) -> list[int]:
    """Parse '1-10' or '1,3,5' or '4' into a sorted list of chapter numbers."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        elif part:
            out.add(int(part))
    return sorted(out)


# --------------------------------------------------------------------------- checks

def check_local(bid: str, chapters: list[int]) -> list[str]:
    """Return human-readable problems with the local corpus (empty = ready to generate).

    Verifies: novel.yaml + a valid language pair matching the manifest; a required style_guide.md;
    every source chapter present under the five-digit convention; and that the existing persistent
    state passes validation, including chapter-bounding metadata (first_seen). Reuses validate.py.
    """
    _use_state_novel(bid)
    problems: list[str] = []
    state = local_root(bid) / STATE_NOVEL

    if not (state / "novel.yaml").exists():
        problems.append(f"missing {context.display_path(state / 'novel.yaml')} "
                        "(state novel must declare source_language / target_language)")
        return problems  # can't resolve chapter filenames without the language pair

    try:
        src = context.source_language(STATE_NOVEL)
        tgt = context.target_language(STATE_NOVEL)
    except context.ConfigError as err:
        problems.append(str(err).splitlines()[0])
        return problems

    # Language pair must match the manifest (so the corpus is what the benchmark expects).
    pair = (load_manifest(bid).get("language_pair") or {})
    if pair.get("source") and pair["source"] != src:
        problems.append(f"source_language '{src}' does not match manifest "
                        f"language_pair.source '{pair['source']}'")
    if pair.get("target") and pair["target"] != tgt:
        problems.append(f"target_language '{tgt}' does not match manifest "
                        f"language_pair.target '{pair['target']}'")

    # A style guide is required so every condition shares the same prose voice.
    cfg = context.load_novel_config(STATE_NOVEL)
    style = state / cfg.get("style_guide", "style_guide.md")
    if not style.exists():
        problems.append(f"missing required style guide {context.display_path(style)}")

    for ch in chapters:
        expected = context.source_path(STATE_NOVEL, ch)
        if not expected.exists():
            problems.append(f"missing source chapter {ch}: expected "
                            f"{context.display_path(expected)}")

    # Persistent state must validate (YAML/JSONL well-formed, first_seen present and parsable).
    for issue in validate.validate_novel(STATE_NOVEL, require_first_seen=True):
        if issue.severity == "error":
            problems.append(f"invalid state: {issue.file}"
                            + (f" [{issue.locator}]" if issue.locator else "")
                            + f": {issue.message}")
    return problems


# --------------------------------------------------------------------------- generation

def _prev_n() -> int:
    return int(backends.load_config().get("retrieval", {}).get("previous_chapters", 2))


def _history_dir(run_dir, cond: str):
    return run_dir / "_histories" / cond


def _read_history(run_dir, cond: str, chapter: int, n: int, tgt: str) -> list[tuple[int, str]]:
    """The previous N translated chapters from one condition's OWN accumulated history."""
    d = _history_dir(run_dir, cond)
    out: list[tuple[int, str]] = []
    for prev in range(max(1, chapter - n), chapter):
        p = d / f"{context.chapter_id(prev)}_{tgt}.md"
        if p.exists():
            out.append((prev, p.read_text(encoding="utf-8")))
    return out


def _write_history(run_dir, cond: str, chapter: int, tgt: str, text: str) -> None:
    d = _history_dir(run_dir, cond)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{context.chapter_id(chapter)}_{tgt}.md").write_text(text, encoding="utf-8")


def generate_chapter(bid: str, chapter: int, backend, run_id: str, seed: str,
                     mode: str = "independent") -> dict:
    """Generate A/B/C candidates for one chapter, write blinded outputs, return the blinding map.

    Histories are per-condition. In the default `independent` mode, B retrieves and accumulates only
    B's prior outputs and C only C's, so the run is a true end-to-end comparison of two systems
    (mistakes propagate within each). In the optional `shared_c` mode, B and C share Condition C's
    history (a controlled per-chapter ablation of structured memory, window held constant). A is
    stateless in both. Call chapters in order.
    """
    novel = _use_state_novel(bid)
    prev_n = _prev_n()
    tgt = context.target_language(novel)
    system = translate.build_system_prompt(novel, prev_n)
    run_dir = local_root(bid) / "runs" / run_id

    outputs: dict[str, str] = {}
    for cond, flags in CONDITIONS.items():
        prev = None
        if flags["include_previous"]:
            window_cond = "C" if (mode == "shared_c" and cond in ("B", "C")) else cond
            prev = _read_history(run_dir, window_cond, chapter, prev_n, tgt)
        # Chapter-bounded knowledge: canonical context/TM for chapter i excludes anything first
        # seen at or after i, so a fact learned in a later chapter can never leak backwards.
        user = context.assemble_translation_context(
            novel, chapter, prev_n, previous=prev, context_max_chapter=chapter, **flags)
        tag = f"benchmark/{bid}/{run_id}/{context.chapter_id(chapter)}/{cond}"
        outputs[cond] = backend.complete(system, user, tag=tag).rstrip() + "\n"

    # Accumulate histories. C always keeps its own; B keeps its own only in independent mode
    # (in shared_c it reads C's). A is stateless and keeps none.
    _write_history(run_dir, "C", chapter, tgt, outputs["C"])
    if mode == "independent":
        _write_history(run_dir, "B", chapter, tgt, outputs["B"])

    # Blind: shuffle conditions onto neutral labels; store the mapping separately from candidates.
    rng = random.Random(f"{seed}:{chapter}")
    labels = ["1", "2", "3"]
    conds = list(CONDITIONS)
    rng.shuffle(conds)
    label_to_cond = dict(zip(labels, conds))

    run_dir = local_root(bid) / "runs" / run_id
    ch_dir = run_dir / context.chapter_id(chapter)
    ch_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "_blinding").mkdir(parents=True, exist_ok=True)

    deterministic = {}
    for label, cond in label_to_cond.items():
        (ch_dir / f"candidate_{label}.md").write_text(outputs[cond], encoding="utf-8")
        deterministic[label] = deterministic_scores(outputs[cond])

    (run_dir / "_blinding" / f"{context.chapter_id(chapter)}.json").write_text(
        json.dumps(label_to_cond, indent=2), encoding="utf-8")
    (ch_dir / "deterministic.yaml").write_text(
        yaml.safe_dump(deterministic, allow_unicode=True, sort_keys=True), encoding="utf-8")
    _write_eval_template(ch_dir / "eval_blank.yaml", chapter, labels)
    return label_to_cond


def generate(bid: str, chapters: list[int], backend_name: str | None, run_id: str, seed: str,
             mode: str = "independent") -> None:
    problems = check_local(bid, chapters)
    if problems:
        raise FileNotFoundError("benchmark corpus not ready:\n  - " + "\n  - ".join(problems))
    backend = backends.get_backend(backend_name, backends.load_config())
    for ch in chapters:
        print(f"[benchmark] generating {context.chapter_id(ch)} (A/B/C, mode={mode}) "
              f"via '{backend.name}'...")
        generate_chapter(bid, ch, backend, run_id, seed, mode=mode)
    print(f"[benchmark] done. Candidates under {context.display_path(local_root(bid) / 'runs' / run_id)}")


# --------------------------------------------------------------------------- C state-update bridge

def propose(bid: str, run_id: str, chapter: int, backend_name: str | None) -> int:
    """Run context extraction for Condition C's translation of one chapter (the C state-update step).

    Feeds the original source chapter + Condition C's translation for that run + the existing
    canonical C state through prompts/context_update.md (reusing build_context), and writes a
    proposal to state/context/_proposals/chNNNNN.yaml. It NEVER touches state/context/*.yaml,
    translation_memory/phrases.jsonl, or the reference translation; a human reviews and applies.
    """
    novel = _use_state_novel(bid)
    tgt = context.target_language(novel)
    run_dir = local_root(bid) / "runs" / run_id
    c_translation = _history_dir(run_dir, "C") / f"{context.chapter_id(chapter)}_{tgt}.md"
    if not c_translation.exists():
        raise FileNotFoundError(
            f"no Condition C translation for chapter {chapter} in run '{run_id}' "
            f"(expected {context.display_path(c_translation)}). Generate the chapter first.")
    return build_context.run(novel, chapter, backend_name, translation_path=c_translation)


# --------------------------------------------------------------------------- deterministic eval

def deterministic_scores(text: str) -> dict:
    """Objective, model-free checks on one candidate (terminology + formatting)."""
    avoid_pairs = list(consistency_check._iter_avoid_pairs(STATE_NOVEL))
    findings = consistency_check.check_text(text, "candidate", avoid_pairs)
    banned = [{"banned": f.banned, "preferred": f.preferred} for f in findings]
    h1 = [ln for ln in text.splitlines() if ln.startswith("# ")]
    has_fm = text.lstrip().startswith("---")
    return {
        "banned_variant_count": len(banned),
        "banned_variants": banned,
        "has_front_matter": has_fm,
        "h1_count": len(h1),
        "formatting_valid": bool(has_fm and len(h1) == 1),
    }


def _write_eval_template(path, chapter: int, labels: list[str]) -> None:
    lines = [
        f"# Blind evaluation - chapter {chapter}.",
        "# Score each candidate 1-5 (5 = best). For hallucination_or_embellishment, 5 = no",
        "# unsupported additions. Leave a score null if not applicable. Do NOT try to guess which",
        "# system produced which candidate. Read candidate_<label>.md alongside this file.",
        "candidates:",
    ]
    for label in labels:
        lines.append(f'  "{label}":')
        for dim in EVAL_DIMENSIONS:
            lines.append(f"    {dim}: null")
        lines.append('    comments: ""')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- analysis / unblind

def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 3) if xs else None


def analyze_run(bid: str, run_id: str) -> dict:
    """Unblind and aggregate per-condition means (human dimensions + deterministic)."""
    run_dir = local_root(bid) / "runs" / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"no such run: {context.display_path(run_dir)}")

    human = {c: {d: [] for d in EVAL_DIMENSIONS} for c in CONDITIONS}
    det = {c: {"banned_variant_count": [], "formatting_valid": []} for c in CONDITIONS}
    chapters_scored = 0

    for ch_dir in sorted(run_dir.glob("ch*")):
        chap = ch_dir.name
        blinding = json.loads((run_dir / "_blinding" / f"{chap}.json").read_text(encoding="utf-8"))
        det_data = yaml.safe_load((ch_dir / "deterministic.yaml").read_text(encoding="utf-8")) or {}
        filled_path = ch_dir / "eval_filled.yaml"
        filled = (yaml.safe_load(filled_path.read_text(encoding="utf-8"))
                  if filled_path.exists() else None)
        if filled:
            chapters_scored += 1

        for label, cond in blinding.items():
            d = det_data.get(label, {})
            det[cond]["banned_variant_count"].append(d.get("banned_variant_count"))
            det[cond]["formatting_valid"].append(1 if d.get("formatting_valid") else 0)
            if filled:
                scores = (filled.get("candidates", {}) or {}).get(label, {}) or {}
                for dim in EVAL_DIMENSIONS:
                    human[cond][dim].append(scores.get(dim))

    aggregate = {
        "benchmark": bid,
        "run": run_id,
        "chapters_with_human_scores": chapters_scored,
        "conditions": {
            cond: {
                "human": {dim: _mean(human[cond][dim]) for dim in EVAL_DIMENSIONS},
                "deterministic": {
                    "mean_banned_variants": _mean(det[cond]["banned_variant_count"]),
                    "formatting_valid_rate": _mean(det[cond]["formatting_valid"]),
                },
            }
            for cond in CONDITIONS
        },
    }
    (run_dir / "analysis.yaml").write_text(
        yaml.safe_dump(aggregate, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return aggregate


# --------------------------------------------------------------------------- CLI

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Wenmai translation benchmark (A/B/C conditions).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="verify the local corpus is present")
    p_check.add_argument("--benchmark", required=True)
    p_check.add_argument("--chapters", default=None)

    p_gen = sub.add_parser("generate", help="generate A/B/C candidates")
    p_gen.add_argument("--benchmark", required=True)
    p_gen.add_argument("--chapters", required=True)
    p_gen.add_argument("--backend", default=None)
    p_gen.add_argument("--run", default=None)
    p_gen.add_argument("--seed", default="wenmai")
    p_gen.add_argument("--mode", default="independent", choices=("independent", "shared_c"),
                       help="independent (default): B and C keep separate histories (end-to-end "
                            "comparison). shared_c: B and C share C's history (per-chapter ablation).")

    p_prop = sub.add_parser("propose", help="extract a Condition C context proposal for review")
    p_prop.add_argument("--benchmark", required=True)
    p_prop.add_argument("--run", required=True)
    p_prop.add_argument("--chapter", type=int, required=True)
    p_prop.add_argument("--backend", default=None)

    p_an = sub.add_parser("analyze", help="unblind and aggregate results")
    p_an.add_argument("--benchmark", required=True)
    p_an.add_argument("--run", required=True)

    args = ap.parse_args()
    try:
        if args.cmd == "check":
            manifest = load_manifest(args.benchmark)
            chapters = (parse_chapters(args.chapters) if args.chapters
                        else list(range(1, int(manifest.get("chapters", 0)) + 1)) or [1])
            problems = check_local(args.benchmark, chapters)
            if problems:
                print(f"[benchmark] {args.benchmark}: NOT ready")
                for p in problems:
                    print(f"  - {p}")
                return 1
            print(f"[benchmark] {args.benchmark}: local corpus present for chapters {chapters}.")
            return 0
        if args.cmd == "generate":
            load_manifest(args.benchmark)
            run_id = args.run or datetime.now().strftime("%Y%m%d-%H%M%S")
            generate(args.benchmark, parse_chapters(args.chapters), args.backend, run_id,
                     args.seed, mode=args.mode)
            return 0
        if args.cmd == "propose":
            load_manifest(args.benchmark)
            return propose(args.benchmark, args.run, args.chapter, args.backend)
        if args.cmd == "analyze":
            load_manifest(args.benchmark)
            agg = analyze_run(args.benchmark, args.run)
            print(yaml.safe_dump(agg, allow_unicode=True, sort_keys=False))
            return 0
    except (FileNotFoundError, ValueError, RuntimeError) as err:
        print(f"[error] {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

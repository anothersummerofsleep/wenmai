# Benchmarks

A controlled way to test Wenmai's core thesis on real long-form fiction: **does structured
persistent narrative memory improve translation beyond giving a capable model a rolling window of
recent chapters?**

The public repo holds only benchmark **code** (`scripts/benchmark.py`), **manifests**
(`benchmarks/<id>/manifest.yaml`, metadata only), and eventual **aggregate result summaries**.
Copyrighted corpus text (source chapters, the official reference translation, and generated
candidate translations) lives under `.local/benchmarks/<id>/` and is git-ignored. Nothing here
scrapes or downloads anything; you supply the local files through your own legitimate access.

## Conditions

For each chapter, three candidates are generated with the SAME backend/model/settings and the SAME
assembler. Only the included context differs:

| Condition | Rolling window (prev N chapters) | Canonical `context/*.yaml` | Translation memory |
|-----------|:--------------------------------:|:--------------------------:|:------------------:|
| **A** chapter-only    | no  | no  | no  |
| **B** rolling-context | yes | no  | no  |
| **C** full Wenmai     | yes | yes | yes |

All three always get the core prompt, the source-language overlay, the style guide, and the source
chapter. The key comparisons:

- **A vs C** - does context-aware translation beat chapter-isolated translation at all?
- **B vs C** - does structured persistent memory add value *beyond* a rolling context window? This
  is the important one, and the benchmark is deliberately built so it can come out negative.

## The shared rolling window (a deliberate methodology choice)

B and C receive the *same* previous-chapter window: **Condition C's own accumulated translated
output**. Because the window text is identical for B and C, the only difference between them is the
structured context. That isolates the variable cleanly.

Trade-off, stated plainly: since C's history was produced with structured context, B is reading a
window that indirectly benefited from structure. So B is not a fully standalone "rolling-only
product"; it is an ablation that answers "at chapter *i*, holding the recent window identical, does
adding structured memory change the output?" If you instead want B to accumulate its own
rolling-only history, that is a different (also valid) experiment; this harness does not do it yet.
See "Known methodological risks" below.

## Sequential accumulation

Chapters run in order. Condition C's output for each chapter is written into the state novel's
`translated/` dir, so it becomes part of the window for the next chapter. Canonical `context/*.yaml`
and `translation_memory/phrases.jsonl` for the state novel are **curated by you** as you read (V1
keeps context extraction human-reviewed; the benchmark does not auto-mutate canonical state). This
is what lets you watch whether C's advantage grows as more chapters (and more accumulated state)
accrue.

## Local layout (git-ignored)

```
.local/benchmarks/<id>/
  state/                         a normal Wenmai novel
    novel.yaml                   source_language / target_language (required)
    style_guide.md               target prose voice
    source/    ch0001_zh.txt ...  (you supply)
    context/   *.yaml            (you curate as you read)
    translation_memory/phrases.jsonl
    translated/ ch0001_en.md ... (C's accumulating outputs; created by the harness)
  reference/   ch0001_en.md ...  official translation (eval only, NEVER prompted)
  runs/<run_id>/
    ch0001/
      candidate_1.md candidate_2.md candidate_3.md   (blinded)
      deterministic.yaml     (objective checks per candidate)
      eval_blank.yaml        (copy to eval_filled.yaml and score)
    _blinding/ch0001.json    (label -> condition; kept out of the candidate view)
    analysis.yaml            (written by `analyze`, after unblinding)
```

## Blind evaluation

Candidates are presented as `candidate_1/2/3` with a per-chapter randomized mapping stored
separately under `runs/<run_id>/_blinding/`. Score `eval_filled.yaml` without opening the blinding
file. `analyze` unblinds and aggregates per-condition means. The reference translation is there to
help you investigate decisions after scoring; it is **not** ground truth, and lexical similarity to
it (BLEU/ROUGE) is deliberately **not** an evaluation metric - there are many valid translations of
the same passage, and Wenmai should not optimize toward reproducing one.

## Evaluation dimensions

Human scores, 1-5 (5 = best; for `hallucination_or_embellishment`, 5 = no unsupported additions):
`faithfulness`, `contextual_correctness`, `terminology_consistency`, `character_voice_consistency`,
`english_prose_quality`, `wordplay_preservation`, `annotation_precision`, `annotation_restraint`,
`hallucination_or_embellishment`.

Deterministic (model-free, computed automatically per candidate): banned terminology-variant count,
and formatting validity. These support the terminology and formatting dimensions objectively; the
literary dimensions stay human. An LLM-as-judge may be added later alongside human review, with an
inspectable prompt and no pretense of being objective truth.

## Commands

```bash
python scripts/benchmark.py check    --benchmark lotm --chapters 1-10
python scripts/benchmark.py generate --benchmark lotm --chapters 1-10 --run r1
python scripts/benchmark.py analyze  --benchmark lotm --run r1
```

`generate` errors clearly if any required local file is missing. Use the same backend across a run
so no condition gets a more capable model than another.

## Known methodological risks

- **Shared window from C** (above): B indirectly benefits from structure-informed history.
- **Curated context is not free of the treatment**: if you write canonical context by reading the
  official translation, C can inherit the reference's interpretations. Prefer curating context from
  the source (and your own reading), not from the reference.
- **Small N**: 10 chapters is enough to observe trends, not to make strong statistical claims.
- **Judge bias**: keep evaluation blind; do not assume Wenmai should win. A null or negative B-vs-C
  result is a real, useful finding about the architecture.

## Non-goals

No scraping or downloaders, no committing of any chapter prose, no LLM-judge-as-truth, no
optimization toward the reference wording, and no scaling to hundreds of chapters. This layer exists
to test the V1 thesis, not to expand the architecture.

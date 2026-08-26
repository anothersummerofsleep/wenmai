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

## Histories: independent by default

The primary research question is an **end-to-end** comparison between a rolling-context translator
and Wenmai, including how decisions and mistakes propagate over time. So the default mode is
`independent`:

- **B** accumulates and retrieves **only B's** prior translations.
- **C** accumulates and retrieves **only C's** prior translations (plus its curated canonical
  context and translation memory).
- **A** is stateless.

Each condition therefore lives with its own history and its own compounding mistakes, which is what
a real deployment of either system would do. `A vs C` asks whether context helps at all; `B vs C`
asks whether structured memory beats a plain rolling window, end to end.

### Optional `shared_c` mode (controlled ablation)

`--mode shared_c` gives B and C the *same* window - Condition C's history - so the only difference
between them at each chapter is the structured context. This is a tighter per-chapter ablation, but
B is then reading a window that indirectly benefited from structure, so it is not a standalone
rolling-only system. Use it to probe a single chapter; use the default `independent` for the real
experiment.

## Sequential accumulation and C's state-update protocol

Chapters run in order. Each condition's output is written to its own history
(`runs/<run_id>/_histories/<cond>/`) and becomes that condition's window for the next chapter.

Condition C additionally accumulates **canonical state**, human-reviewed:

```
source chapter + C's translation + existing C state
  -> extraction proposal (scripts/build_context.py)
  -> HUMAN review
  -> accepted entries (each tagged first_seen: chNNNNN) into state/context/*.yaml and
     state/translation_memory/phrases.jsonl
  -> used when translating the next chapter
```

The harness accumulates C's translated history automatically; it does **not** auto-mutate canonical
context or translation memory (V1 keeps that human-reviewed). This is what lets you watch whether
C's advantage grows as more chapters, and more accumulated state, accrue.

## Chapter-bounded knowledge (hard invariant)

A fact learned in chapter N must never influence generation of any chapter `< N`, even after it
becomes canonical context. The harness enforces this structurally on both channels that carry
knowledge into a chapter's prompt:

- **Rolling window**: only chapters strictly before the current one are ever included.
- **Canonical context + translation memory**: when generating chapter *i*, any record whose
  `first_seen` chapter is `>= i` is pruned (`context.load_context_records(..., max_chapter=i)`), so
  a later-learned fact cannot leak backwards, even if you curated it into the store already, and
  even if you re-generate an earlier chapter.

For this guarantee to hold, **every curated context record and translation-memory entry must carry a
`first_seen: chNNNNN`** marking the chapter it was first learned. The extraction proposal fills this
in; keep it when you accept an entry. An entry with no `first_seen` cannot be chapter-bounded and
will be visible to all chapters, so do not omit it. (The source chapter itself is always in the
prompt, so chapter *i* still sees everything its own source states; bounding only governs the
*accumulated* store.)

## The reference translation is eval-only (hard rule)

The official English translation must **never** participate in context generation, state curation,
translation prompting, or style-guide construction. It is consulted **only after blind scoring**,
for post-hoc human comparison. Do not curate `state/context/*.yaml` from it (curate from the source
and your own reading). It is not ground truth, and lexical similarity to it (BLEU/ROUGE) is
deliberately not an evaluation metric.

## Local layout (git-ignored)

```
.local/benchmarks/<id>/
  state/                         a normal Wenmai novel
    novel.yaml                   source_language / target_language (required)
    style_guide.md               target prose voice
    source/    ch00001_zh.txt ...  (you supply)
    context/   *.yaml            (you curate as you read; C's canonical state)
    translation_memory/phrases.jsonl
  reference/   ch00001_en.md ...  official translation (eval only, NEVER prompted)
  runs/<run_id>/
    _histories/<A|B|C>/ch00001_en.md ...  per-condition accumulating output (A keeps none)
    ch00001/
      candidate_1.md candidate_2.md candidate_3.md   (blinded)
      deterministic.yaml     (objective checks per candidate)
      eval_blank.yaml        (copy to eval_filled.yaml and score)
    _blinding/ch00001.json    (label -> condition; kept out of the candidate view)
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
python scripts/benchmark.py generate --benchmark lotm --chapters 1-10 --run r1   # independent (default)
python scripts/benchmark.py generate --benchmark lotm --chapters 1-10 --run r1 --mode shared_c
python scripts/benchmark.py analyze  --benchmark lotm --run r1
```

`generate` errors clearly if any required local file is missing. Use the same backend across a run
so no condition gets a more capable model than another. Between chapters, review Condition C's
extraction proposals and apply accepted entries to `state/context/` and
`state/translation_memory/` (the C state-update protocol above).

## Known methodological risks

- **Mode choice**: `independent` (default) is the real end-to-end comparison; `shared_c` is a
  tighter ablation where B reads C's structure-informed history and so is not standalone.
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

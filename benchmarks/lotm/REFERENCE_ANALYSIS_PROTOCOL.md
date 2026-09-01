# LOTM reference-analysis protocol (frozen before reference exposure)

**Status: frozen.** This document fixes the rules for the post-hoc official-reference analysis
**before** any official English translation text has been inspected. It is committed and pushed
prior to opening the reference so the analytical commitments are timestamped ahead of exposure.

- Run: `lotm-opus48-v1` (`claude-opus-4-8`, `claude_code_stateless`, `independent` mode).
- Blind phase: complete and frozen through `ch00010`. Final blind checkpoint published in
  [`results/lotm-opus48-v1_ch00001-ch00010.md`](results/lotm-opus48-v1_ch00001-ch00010.md).
- **At time of this freeze, the official English reference has NOT been inspected.** Its contents
  have not been read, summarized, hashed through a content-reading pipeline, or otherwise loaded.
  The reference will be opened only in a later command, after this protocol is committed and pushed.

## Purpose

The official English translation is an **after-the-fact published reference**, not a gold-standard
answer key. It is used for descriptive comparison only. It must never be used to retroactively change
the blind benchmark, and matching the publication is not itself a measure of quality.

## Frozen-artifact rule

Reference analysis may **never** alter any of the following. All are frozen:

- candidate translations;
- blind evaluator scores;
- blind rankings;
- candidate-to-condition mappings;
- deterministic outcomes;
- canonical context (characters, terminology, locations, factions, timeline);
- translation memory (12 records, unchanged; no chapter-10 additions);
- reviewed curation;
- the already-published blind-phase interpretation and its result files.

Two direction-of-inference guards:

- If a candidate differs from the official translation, that does **not** automatically make the
  candidate wrong.
- If the official translation differs from our frozen canonical choice, that does **not**
  retroactively make our choice wrong.

## Source remains primary

For any semantic judgment:

- **Chinese source = primary evidence.**
- **Official English = published comparison reference.**

The official translation may itself paraphrase, localize, compress, expand, interpret, or choose
stylistically different wording. Therefore `candidate != official` must **not** be equated with
`candidate incorrect` without checking the Chinese source. Every semantic call returns to the source
before a difference is classified.

## Reference-analysis questions (four frozen tracks)

### A. Terminology / reference agreement

Compare A/B/C and the official translation on recurring translated items:

- proper names;
- locations;
- organizations;
- titles;
- supernatural terminology;
- repeated technical / worldbuilding terms;
- recurring phrase translations.

Measure agreement **descriptively**. Do not reward official-match merely because it matches the
publication; report agreement rates as observations, not scores.

### B. Semantic divergence review

Identify meaningful cases where A/B/C differ from one another, where candidates differ from the
official translation, or where the official translation differs substantially from the
literal/source-supported reading. For each interesting case, **return to the Chinese source** before
judging. Classify differences where useful, without assuming any side is correct in advance:

- equivalent alternative
- stylistic difference
- terminology choice
- compression
- expansion
- clarification
- source-fidelity issue
- unsupported embellishment
- official adaptation

### C. Longitudinal consistency

Compare recurring translation decisions across chapters 1-10 for the official English, A, B, and C.
Questions:

- Does the official translation itself remain internally consistent across the ten chapters?
- Where does A drift?
- Where does B drift?
- Where does C preserve its frozen decisions?
- Where does C consistently choose a different but source-defensible convention from the official?
- Are there places where the official changes terminology over these ten chapters?

This track is central because the benchmark's core hypothesis concerns translation-state continuity.

### D. Literary / voice comparison

Qualitatively and descriptively compare character voice, comic register, wordplay, sentence rhythm,
localization, explanatory additions, cultural adaptation, and prose compression/expansion. Keep it
descriptive; do **not** retroactively award benchmark points.

## Quantitative metrics

Do **not** use BLEU, ROUGE, or generic string similarity as a primary benchmark conclusion. If any
lexical metric is computed at all, it is labeled a **supplementary diagnostic**, never a headline.

Prefer interpretable measures:

- recurring-term reference agreement rate
- proper-name agreement
- consistent-choice rate
- terminology drift count
- within-condition recurrence consistency

Denominators are not left to post-hoc judgment. They are fixed by the pre-reference comparison
universe defined next, before the reference is opened.

## Pre-reference comparison universe

All quantitative terminology/consistency analyses use a **source-driven item universe fixed before
the official English is opened**. The reference translation itself must **never** be used to decide
which terms/items enter the quantitative sample. The universe is built only from the frozen Chinese
Chapters 1-10 plus the frozen human-reviewed canonical state and translation memory.

Inclusion rule. Include a translated item when **both** hold:

1. it is represented in the frozen reviewed canonical terminology / entity / location / faction /
   name state, or in the frozen translation memory; **and**
2. its source identity has **at least two genuine occurrence opportunities** across Chapters 1-10.

Aliases / source variants that the frozen canonical state already identifies as the same
entity/item may be grouped. One-off items (fewer than two occurrence opportunities) are **excluded**
from recurrence-consistency metrics. Timeline events are excluded (narrative beats, not recurring
translated lexical items). **Do not add items merely because the official translation later makes them
interesting.**

### Freeze the inventory before reference access

A local, machine-readable inventory is generated from the frozen inputs, before any reference access,
by the deterministic generator [`../../scripts/build_reference_inventory.py`](../../scripts/build_reference_inventory.py)
and written to (git-ignored, source-derived):

```
.local/benchmarks/lotm/reference_analysis/pre_reference_inventory.csv
```

Each row carries enough to reproduce the denominator: `item_id`, `category`, `source_key`,
`keys_grouped`, `english`, `first_seen`, `occurrence_count`, `occurrence_chapters`. The raw inventory
stays local. Its existence-before-exposure is proved publicly by
[`reference_analysis/PRE_REFERENCE_MANIFEST.md`](reference_analysis/PRE_REFERENCE_MANIFEST.md), which
records the inventory item count, category counts, the SHA-256 of the frozen CSV, the inclusion rule,
and generation timestamp/commit provenance. The official English is not inspected while generating it.

## Metric definitions (frozen)

The principal descriptive metrics are fixed here, before reference access.

### Within-condition recurrence consistency

For each pre-registered recurring item:

```
consistent = the condition uses one materially equivalent translation decision
             across all genuine recurrence opportunities
```

Report `consistent items / eligible recurring items` for A, B, C, and later the official translation.
**Purely grammatical inflection does not constitute a changed translation decision** (e.g. plural or
possessive of the same rendered name is the same decision); only a materially distinct rendering
counts as a change.

### Terminology drift count

Defined as the **number of eligible recurring items for which a condition uses more than one
materially distinct translation decision across Chapters 1-10.** This is an **item count**, not a
count of every individual variant occurrence.

### Official-reference agreement

Once the reference is opened, compare each condition against the official translation **only over the
already frozen item universe**. Report agreement descriptively. **Official-match is not correctness.**
Where exact surface wording differs but both choices appear source-defensible, classify that
**separately** rather than forcing it into an error category.

### Proper-name agreement

Use the **proper-name / entity subset of the same pre-registered universe** (the character, faction,
and location items). Do **not** create a separate post-reference hand-selected name list.

### Qualitative examples

Track B / D examples selected because they are "interesting" are **illustrative qualitative cases**,
unless an explicit exhaustive selection procedure is used. Counts drawn from hand-selected
qualitative examples must **not** be presented as prevalence estimates; only the pre-registered
universe yields prevalence.

## Reference provenance / alignment rule

Before any semantic analysis begins in the later command, in order:

1. copy/place the official reference into the designated git-ignored reference area
   (`.local/benchmarks/lotm/reference/`);
2. record byte SHA-256 provenance of each reference file;
3. verify Chapter 1-10 alignment;
4. create a chapter-mapping manifest;
5. **stop** if chapters are missing or structurally ambiguous, rather than silently realigning them.

Hashing raw bytes for provenance is permitted before content inspection, provided it does not render
the text into model context.

## Condition C boundary

The official translation must **never** be merged into Wenmai canonical state or translation memory
for this completed run. If the official English uses a familiar published term while frozen C uses a
different, source-defensible term: record the difference, analyze it, and **do not mutate** the
completed experimental state.

## Public-output separation

Reference-phase outputs are kept visibly separate from the frozen blind-phase report. Do **not**
rewrite [`results/lotm-opus48-v1_ch00001-ch00010.md`](results/lotm-opus48-v1_ch00001-ch00010.md)
(the frozen final blind-phase checkpoint) into a reference-aware report. Post-hoc public results go
under a separate namespace:

```
benchmarks/lotm/reference_analysis/
```

Raw / reference copyrighted prose remains **local and git-ignored** (`.local/`). Any public
reference-analysis report uses only: aggregate statistics, short terminology examples, tightly
limited quotations where legally and methodologically appropriate, and paraphrased observations.
No chapter-length source, reference, or candidate text is published.

## Leakage / provenance boundary

This protocol is committed **before** the reference contents are opened. Recorded at time of protocol
freeze: **the official English reference has not yet been inspected.** The next reference-reading
command runs only after this protocol commit is pushed. The designated reference location in the repo
is the git-ignored directory `.local/benchmarks/lotm/reference/` (empty at freeze time).

## Statistical caution (retained)

- One novel / corpus; Chinese to English only.
- One generation model / backend (`claude-opus-4-8`, `claude_code_stateless`).
- Nine informative chapters; ordinal, model-assisted evaluations; a single run.
- Model-weight familiarity with LOTM cannot be ruled out.
- Condition C includes human review (this measures the full reviewed-memory workflow).
- No claim of universal superiority and no claim of statistical significance.

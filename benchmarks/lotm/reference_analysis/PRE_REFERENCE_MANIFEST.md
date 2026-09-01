# LOTM pre-reference comparison-universe manifest

Public-safe provenance for the quantitative comparison universe used in the reference-analysis phase.
It records that the item universe (the denominator for all quantitative terminology/consistency
analyses) was **fixed before the official English reference was opened**. No source, reference, or
candidate prose appears here: only counts, category tallies, the inclusion rule, and a checksum.

- **Run:** `lotm-opus48-v1` (`claude-opus-4-8`, `claude_code_stateless`, `independent`).
- **Frozen inventory (local, git-ignored):**
  `.local/benchmarks/lotm/reference_analysis/pre_reference_inventory.csv`
- **Generator (public, deterministic):**
  [`scripts/build_reference_inventory.py`](../../../scripts/build_reference_inventory.py)
- **At manifest time the official English reference remained uninspected.** The designated reference
  directory `.local/benchmarks/lotm/reference/` was empty.

## Inclusion rule (source-driven; reference never consulted)

An item enters the universe only when **both** hold:

1. it is represented in the frozen human-reviewed canonical terminology / entity / location /
   faction / name state, **or** in the frozen translation memory; **and**
2. its source identity has **>= 2 genuine occurrence opportunities** across the frozen Chinese
   Chapters 1-10.

Chinese-script aliases the canonical state already groups under one entity are grouped for counting;
Latin-script aliases are display-only and not counted. One-off items (< 2 occurrences) are excluded.
Timeline events are excluded (narrative beats, not recurring translated lexical items). The official
English translation is **never** used to decide membership.

## Frozen inventory summary

| Field | Value |
|---|---|
| Inventory item count | **77** |
| character | 11 |
| faction | 8 |
| location | 15 |
| terminology | 41 |
| tm_phrase | 2 |
| Proper-name / entity subset (character + faction + location) | 34 |
| Candidate items considered (pre-threshold) | 158 |
| Excluded as one-off (< 2 occurrences) | 81 |

**SHA-256 of the frozen inventory CSV:**

```
4f5f2abbfbdb54fd9754a0a646acf4a01d04b488ea32c1e491f499e25c0e6b32
```

Reproduce with:

```
python scripts/build_reference_inventory.py \
  --state .local/benchmarks/lotm/state \
  --out   .local/benchmarks/lotm/reference_analysis/pre_reference_inventory.csv \
  --chapters 10
```

The generator is deterministic: the same frozen inputs reproduce a byte-identical CSV and the SHA-256
above.

## Provenance

| Field | Value |
|---|---|
| Generated (UTC) | 2026-09-01T06:50:26Z |
| Parent commit at generation | `bb678c3f196d44ceeee9e98274400a6c9afc392b` (reference-analysis protocol freeze) |
| Frozen canonical state mtime (context/*.yaml) | 2026-08-31T23:44:42Z |
| Frozen translation memory mtime (phrases.jsonl) | 2026-08-31T18:36:57Z; 12 records |
| Chapters covered | 1-10 (frozen Chinese source) |
| Official reference inspected at generation? | No (reference directory empty) |

This manifest is committed **before** the reference is opened, so the pre-registered denominator is
timestamped ahead of reference exposure. The raw inventory stays under `.local/` because it is
source-derived; this manifest is the public-safe proof that it existed first.

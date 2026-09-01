# Run Wenmai on your own novel

Wenmai works chapter by chapter. The translation itself uses three passes, but the long-form memory
comes from the review loop *between* chapters: translate, extract proposed durable state,
human-review it, then let the next chapter inherit those accepted decisions.

This is the same structural persistent-memory workflow represented by **Condition C** in Wenmai's
benchmark. It does **not** mean a new run will reproduce the benchmark's exact generated prose. You
reproduce the workflow and the treatment, not deterministic output strings.

```
chapter N source
    -> [1] retrieve: style guide + reviewed canonical context + translation memory + previous chapters
    -> [2] translate + annotate
    -> [3] terminology consistency check
    -> review the translation
    -> extract a context proposal from source + finished translation + prior canon
    -> human review
    -> accept only supported, durable state / TM
    -> validate state
    -> chapter N+1
```

---

## 1. What you need

- Python and this repo's dependencies.
- Your own **legitimately obtained** source text. No official or reference translation is needed.
- An LLM backend (below).
- The currently tested production language path is **Chinese to English** (`zh -> en`).
- Your source and generated novel files stay **local and git-ignored** by default (see `.gitignore`),
  so cloning and running never commits anyone's copyrighted work.

Two normal backend choices (set in `config.yaml`, or override with `--backend`):

- **`claude_code`** (default): human-in-the-loop file handoff. No API key. Each pass writes a prompt
  file and waits; you fill a response file and re-run.
- **`anthropic`**: direct API execution. Requires the `ANTHROPIC_API_KEY` environment variable.

A third backend, `claude_code_stateless`, also exists. It runs each call as a fresh, stateless
`claude -p` process and is mainly useful for controlled, reproducible model calls (it is what the
benchmark used). Beginners do not need it.

## 2. Install

```bash
python -m pip install -r requirements.txt
cp config.example.yaml config.yaml
```

`config.yaml` is optional (defaults come from `config.example.yaml`), but create it before a real
project. The fields you actually care about:

```yaml
backend: claude_code        # or: anthropic
retrieval:
  previous_chapters: 2      # how many previous translated chapters to include as context
anthropic:
  model: claude-opus-4-8    # only used by the anthropic backend; key comes from ANTHROPIC_API_KEY
```

## 3. Create the novel directory

```
novels/<your-novel>/
  novel.yaml
  style_guide.md
  source/
  translated/
  context/
  translation_memory/
```

Source chapters are named by the source language; translations by the target language:

```
source/ch00001_zh.txt
source/ch00002_zh.txt
translated/ch00001_en.md
```

A minimal `novel.yaml`:

```yaml
title_source: ...
title_english: ...
slug: my-novel
source_language: zh
target_language: en
genre: ...
style_guide: style_guide.md
status: active
```

Additional metadata is optional unless the code requires it. `novels/sample-novel/` is a schema and
formatting **example** to read, not something to copy wholesale into a real novel: do not inherit its
populated context files.

## 4. Write the style guide

`style_guide.md` should establish your prose voice and conventions:

- target prose voice
- names / transliteration policy
- dialogue conventions
- tense and person
- punctuation conventions
- annotation philosophy (when and how to gloss)
- localization vs literalism preference

Keep it practical, not exhaustive. See `novels/sample-novel/style_guide.md` for an example.

## 5. Start with empty or genuinely known context

A fresh novel does **not** need a giant encyclopedia before Chapter 1. Begin with empty `context/`
and an empty `translation_memory/phrases.jsonl`, and let Wenmai accumulate knowledge naturally as you
review each chapter.

If you seed any state by hand, include only what is legitimately known **before** the chapter where
it becomes available, and give every durable record a `first_seen`:

```yaml
first_seen: ch00001
```

Translation-memory records need a canonical `first_seen` too. Then validate:

```bash
python scripts/validate.py --novel <your-novel> --require-first-seen
```

Why this matters: `first_seen` is what prevents knowledge learned later in the story from leaking
backward when an earlier chapter is translated or regenerated. The pipeline uses it to bound what
each chapter can see (chapter *i* sees only records with `first_seen` before *i*).

## 6. Add Chapter 1

Put only the chapter text here (no translation):

```
novels/<your-novel>/source/ch00001_zh.txt
```

## 7. Translate Chapter 1

```bash
python scripts/translate.py --novel <your-novel> --chapter 1
```

What happens:

```
Pass 1  retrieve context   (Python, mechanical) -> assemble the prompt
Pass 2  translate + annotate (LLM, via backend)  -> produce translated/chNNNNN_en.md
Pass 3  consistency check    (Python, mechanical) -> flag terminology drift
```

For Chapter 1 there is little or no prior context. That is expected.

## 8. The `claude_code` handoff (default backend)

On the first run, `claude_code` writes the assembled prompt and stops. It prints the two paths:

1. Read the prompt: `.runs/<your-novel>/ch00001/translate.prompt.md`
2. Write the completion to: `.runs/<your-novel>/ch00001/translate.response.md`
3. Re-run the **same** command:

```bash
python scripts/translate.py --novel <your-novel> --chapter 1
```

The second run consumes the response, writes `translated/ch00001_en.md`, and runs the consistency
check. Context extraction (next steps) uses the same prompt/response/re-run pattern under the
`context_update` tag: `.runs/<your-novel>/ch00001/context_update.prompt.md` and
`.runs/<your-novel>/ch00001/context_update.response.md`.

## 9. Review the finished translation

Read `translated/ch00001_en.md` before you rely on it. Check meaning, names, terminology, voice,
annotations, unsupported additions, and any terminology-drift warnings from pass 3. The consistency
check is narrow and mechanical: a clean result does **not** prove the translation is good.

## 10. Extract proposed memory

```bash
python scripts/build_context.py --novel <your-novel> --chapter 1
```

This reads the original source + the finished translation + prior canonical context, and writes:

```
context/_proposals/ch00001.yaml
```

It does **not** change durable state.

```
PROPOSAL  !=  CANONICAL STATE
```

## 11. Human-review the proposal

This is the core Wenmai step. Generally **accept**:

- recurring character identity and aliases
- durable relationships actually supported by the text
- recurring locations
- factions / institutions
- stable terminology decisions
- persistent supernatural / technical concepts
- durable timeline facts
- recurring idioms / jokes / phrases worth translation memory

Generally **reject or rewrite**:

- guesses
- future-story or model-prior knowledge not in this chapter's source
- facts not actually established by the source
- accidental interpretation presented as fact
- a narrator's or character's belief collapsed into objective truth
- a deliberate lie converted into a fact
- ephemeral scene details with no future value
- one-off words promoted to terminology without reason
- duplicate entries
- overly broad worldbuilding claims
- premature "recurring motif" claims after a single occurrence

Epistemic care matters:

```
"Character X believes Y"  is not the durable fact  "Y is true"
"Character X claims Y"     may be a lie
```

Keep durable state to what the story has actually and reliably established so far.

## 12. Apply accepted state by hand

There is no automatic merge. Copy accepted entries into the matching files:

```
characters        -> context/characters.yaml
terminology       -> context/terminology.yaml
locations         -> context/locations.yaml
factions          -> context/factions.yaml
timeline          -> context/timeline.yaml
other categories  -> a suitable context/*.yaml
translation_memory -> translation_memory/phrases.jsonl   (one JSON object per line)
```

The system is open-ended: custom files such as `magic_system.yaml`, `honorifics.yaml`, or
`cultivation_system.yaml` are loaded automatically. Preserve `first_seen: chNNNNN` on every accepted
durable record.

## 13. Validate

```bash
python scripts/validate.py --novel <your-novel> --require-first-seen
```

Then optionally check terminology drift across what you have so far:

```bash
python scripts/consistency_check.py --novel <your-novel>
```

`validate.py` checks the structure of your persistent state (and, with `--require-first-seen`, that
every durable record carries a chapter). `consistency_check.py` flags where a translation used a
banned/old spelling instead of the canonical terminology. Fix errors before continuing.

The per-chapter consistency check (`--chapter N`, and Pass 3 of `translate.py`) uses the terminology
state that was available before that chapter (`first_seen < N`). Running `consistency_check.py`
without `--chapter` is instead a retroactive audit against your current canonical state.

## 14. Translate Chapter 2

Add `source/ch00002_zh.txt`, then:

```bash
python scripts/translate.py --novel <your-novel> --chapter 2
```

Chapter 2 now receives:

```
style guide
+ accepted Chapter 1 canonical state
+ accepted translation memory
+ previous translated chapter(s)
+ Chapter 2 source
```

This is where persistent memory begins to matter. Then repeat the loop:
translate -> review -> extract -> review proposal -> apply accepted state -> validate -> next chapter.

## 15. The everyday loop

```
1.  Add source/chNNNNN_zh.txt
2.  python scripts/translate.py --novel <novel> --chapter N
3.  Complete the handoff if using claude_code; re-run the same command
4.  Review translated/chNNNNN_en.md
5.  Resolve important consistency warnings
6.  python scripts/build_context.py --novel <novel> --chapter N
7.  Complete the handoff if needed; re-run the same command
8.  Review context/_proposals/chNNNNN.yaml
9.  Apply accepted canonical / TM entries by hand
10. python scripts/validate.py --novel <novel> --require-first-seen
11. Move to N+1
```

## 16. What gives Wenmai its long-form behavior

The three-pass translator alone is not the whole system. The long-form treatment is the combination:

```
rolling translated history
+ reviewed canonical state
+ translation memory
+ chapter-bounded first_seen provenance
+ repeated human curation
```

That combination is the structural workflow tested as benchmark Condition C. It shapes how future
chapters are translated; it does not guarantee reproduction of any specific past output.

## 17. Regenerating an old chapter

Normal translation is chapter-bounded. If you re-run chapter 5 after translating through chapter 50:

```bash
python scripts/translate.py --novel <your-novel> --chapter 5 --force
```

`--force` regenerates the translation, but canonical / TM records with `first_seen >= ch00005` are
excluded from the prompt, so future-story state cannot leak backward. Two cautions:

- the model call itself is nondeterministic unless your backend / model / settings make it
  deterministic, so the new text will differ from the old;
- `--force` overwrites the existing translation. Version your work (for example commit it in your own
  private repo) before using it.

## 18. What Wenmai does NOT automate in v1

- accepting proposals
- merging accepted state into the canonical files
- literary proofreading
- deciding whether an extracted claim is actually true
- git commits / PRs
- full evaluation of translation quality

The human-review boundary is intentional: reviewed memory is the point.

## 19. Troubleshooting

- **Missing source chapter** - check the exact filename, e.g. `source/ch00007_zh.txt` (five digits,
  correct language suffix).
- **`claude_code` is waiting on a response** - fill the shown `.response.md`, then re-run the same
  command.
- **Translation already exists** - review it, or re-run with `--force` deliberately.
- **Validator says `first_seen` missing** - add the true chapter where that durable fact or term was
  first learned.
- **Consistency check flags an old spelling** - inspect `context/terminology.yaml` and decide whether
  the translation or the canonical decision should change.
- **My context files are getting huge** - only keep durable information that will matter later. Wenmai
  is curated memory, not a transcript of every event.

## 20. Benchmark connection (optional)

Condition C in the [benchmark](benchmarks/README.md) used the same structural ingredients: a
condition's own rolling history + human-reviewed canonical context + translation memory. The
benchmark exists to test that architecture. Normal users do not need to run A/B/C; they just follow
the loop above.

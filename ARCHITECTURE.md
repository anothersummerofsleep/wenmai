# Architecture

Wenmai is a **multilingual context-aware translation framework**. V1 implements **Chinese to
English**, but the core is deliberately language-neutral so that adding a language pair (Korean to
English is the expected next one) is additive rather than a rewrite.

This document names the seam between the two, and the small set of extension points. It is
intentionally light: there is no plugin framework, no language class hierarchy, no registry. Just
config-driven behaviour and a couple of conventions.

## Two layers

**Language-neutral core** (works the same for any source/target pair):
- Narrative memory and terminology: the `context/*.yaml` records and `translation_memory/`.
- Retrieval and prompt assembly: `scripts/context.py`.
- Translation orchestration and backends: `scripts/translate.py`, `scripts/backends.py`.
- Consistency / drift checking: `scripts/consistency_check.py`.
- Context extraction: `scripts/build_context.py`, `prompts/context_update.md`.
- The core translation prompt: `prompts/translate.md`.

**Language-specific layer** (its own linguistics, kept out of the core):
- `prompts/languages/<source_language>.md` — the source-language guidance overlay (chengyu,
  homophones, classical references, naming conventions for `zh`; honorifics, speech levels, kinship
  address, hanja for a future `ko`). Appended to the core prompt at runtime when it exists.
- Optional novel/genre context files (e.g. `cultivation_system.yaml`) — loaded automatically
  because the core reads *whatever* `*.yaml` a novel places in `context/`.

### Why the split has to hold (a standing constraint)

This boundary is a design constraint on all future work, not a formality. Different source languages
carry meaning through different machinery, and that machinery must not accrete in the shared core.

Korean is the worked example. Adding Korean to English will bring concerns Chinese does not have:
honorifics and speech levels (존댓말 / 반말), kinship-based forms of address, and Sino-Korean (hanja)
vocabulary whose nuance parallels but does not equal Chinese. All of that belongs in
`prompts/languages/ko.md` and, where a category genuinely needs structured data, in ko-specific
`context/*.yaml` files a novel opts into. None of it belongs in `context.py`, `translate.py`,
`consistency_check.py`, `build_context.py`, or the record schema.

The test for any change: **if it encodes how one specific source language works, it goes in the
language layer.** If adding a language would require editing the core or the schema, that is a leak
in the boundary to be fixed, not a feature to accept.

## Extension points (the whole list)

1. **`source_language` / `target_language` in `novel.yaml`.** These drive the source and translated
   filename suffixes (`ch0001_<src>.txt` -> `ch0001_<tgt>.md`) and select the prompt overlay. No
   filename or language is hardcoded in the scripts; see `context.source_path`,
   `context.translated_path`, `context.list_translated_chapters`.
2. **`prompts/languages/<lang>.md`.** Drop in a file named for a source language to add its
   linguistic guidance. Absent overlay is fine (the core prompt still runs).
3. **`context/*.yaml` is open-ended.** The core loads every YAML present (generic files first, then
   any extras alphabetically), so a novel can add its own context categories with no code change.
4. **Schema is source-neutral.** Records use `source:` for the original-language token (not
   `chinese:`) and `english` / `preferred` for the canonical rendering. The drift checker finds any
   dict carrying an `avoid:` list, regardless of file, nesting, or genre.

## Adding a language pair later (sketch, not yet implemented)

To add, say, Korean to English:
1. Give the novel `source_language: ko` in its `novel.yaml`; name source files `ch0001_ko.txt`.
2. Write `prompts/languages/ko.md` with Korean-specific annotation triggers and naming rules.
3. Seed the same `context/*.yaml` shapes (they are already language-neutral); add ko-specific
   context files if the genre needs them.

No changes to `context.py`, `translate.py`, `consistency_check.py`, or the schema should be required.
If one is, that is the signal a Chinese assumption leaked into the core and should be pushed back out
to the language layer.

## Non-goals for now

- No abstract `Language` classes, plugin discovery, or per-language Python modules. Prompts plus
  config are enough until a language genuinely needs code (e.g. script-specific tokenization), at
  which point the seam above is where it goes.

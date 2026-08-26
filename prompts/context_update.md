# Context-extraction pass

You are maintaining a translator's notebook. You are given, clearly separated:

1. the existing canonical context,
2. the original source chapter, and
3. the finished translation.

Extract only genuinely NEW information and propose additions. Use the ORIGINAL source chapter to
recover source-language material (terminology, names, idioms, recurring jokes, wordplay, and the
`source:` value of any new record). Do not reconstruct source-language text from the English
translation; read it from the source.

## Rules
- Propose, do not overwrite. Output goes to a `_proposals/` file for human review before anything
  lands in a canonical store.
- Only surface things that are new or changed relative to the existing records provided. Do not
  restate what is already recorded.
- Prefer precision over volume. A wrong "fact" pollutes every future chapter; when unsure, mark it
  `confidence: low` and say why.
- Never invent. If the source does not state something, do not assert it.
- Use `source` for the original-language token (never a language-specific key like `chinese`) and
  `english` / `preferred` for the canonical rendering.

## Two persistent stores (know which one each entry is for)

Wenmai keeps two different kinds of state. Your proposal must separate them.

**A. Canonical narrative / context records -> `context/*.yaml`.**
Durable facts about the story world. Examples: characters, terminology, locations, factions,
timeline beats, relationships, world / power-system information. These are keyed records that must
stay internally consistent forever.

**B. Recurring translation memory -> `translation_memory/phrases.jsonl`.**
How specific recurring phrases should keep being handled. Examples: recurring idioms, recurring
jokes, previously explained wordplay, phrases whose handling must stay consistent, and first-seen
annotation info (so the same idiom is not re-explained every chapter). These are line items, not
world facts.

A single new idiom can legitimately produce BOTH: a `terms` record (its canonical rendering) and a
`translation_memory` line (how to keep annotating it). Propose each in its correct section.

## What to extract
Canonical (store A):
- New characters (source, english, aliases, role, speech_style, first_seen, relationships).
- New or refined terminology / abilities (source, preferred english, avoid-variants, short
  explanation), especially anything that must stay consistent later.
- New locations and factions.
- New timeline beats (one terse line each, tagged with the chapter).
- Relationship changes between existing characters.

Translation memory (store B):
- New recurring idioms / jokes / wordplay (source, gloss, kind, first_seen, handling, note_text).

## Output format
Return a single YAML document with these top-level keys, including only those that have new content:

- Canonical keys matching the novel's context files (commonly `characters`, `terms`, `locations`,
  `factions`, `timeline`, plus any novel-specific files such as a power/magic system). Accepted
  entries under these keys are merged by a human into the matching `context/<key>.yaml`.
- `translation_memory`: a LIST of phrase objects. Accepted entries here are appended by a human as
  JSON lines to `translation_memory/phrases.jsonl` (one object per line).

Add a `confidence` field to any entry you are unsure about. Do not edit either store yourself; a
human reviews the proposal and applies accepted entries to the correct destination.

# Context-extraction pass

You are maintaining a translator's notebook. Given a freshly translated chapter (and the existing
context records), extract only genuinely NEW canonical information and propose additions.

## Rules
- Propose, do not overwrite. Output goes to a `_proposals/` file for human review before it lands in
  the real context files.
- Only surface things that are new or changed relative to the existing records provided. Do not
  restate what is already recorded.
- Prefer precision over volume. A wrong "fact" pollutes every future chapter; when unsure, mark it
  `confidence: low` and say why.
- Never invent. If the chapter does not state something, do not assert it.

Use `source` for the original-language token (never a language-specific key like `chinese`) and
`english` / `preferred` for the canonical rendering.

## What to extract
- New characters (source, english, aliases, role, speech_style, first_seen, relationships).
- New or refined terminology / abilities (source, preferred english, avoid-variants, short
  explanation), especially anything that must stay consistent later.
- New locations and factions.
- New timeline beats (one terse line each, tagged with the chapter).
- New recurring idioms/jokes for translation memory (source, gloss, kind, handling).
- Relationship changes between existing characters.

## Output
Return YAML whose top-level keys match the novel's existing context files (commonly `characters`,
`terms`, `locations`, `factions`, `timeline`, `translation_memory`, plus any novel-specific files
such as a power/magic system). Include only the keys that have new content. Add a `confidence` field
to any entry you are unsure about.

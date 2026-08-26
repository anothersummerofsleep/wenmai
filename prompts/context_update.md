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

## What to extract
- New characters (chinese, english, aliases, role, speech_style, first_seen, relationships).
- New or refined terminology / techniques / realms (chinese, preferred english, avoid-variants,
  short explanation), especially anything that must stay consistent later.
- New locations and factions.
- New timeline beats (one terse line each, tagged with the chapter).
- New recurring idioms/jokes for translation memory (phrase, gloss, kind, handling).
- Relationship changes between existing characters.

## Output
Return YAML with top-level keys matching the context files
(`characters`, `terms`, `locations`, `factions`, `cultivation_system`, `timeline`,
`translation_memory`). Include only the keys that have new content. Add a `confidence` field to any
entry you are unsure about.

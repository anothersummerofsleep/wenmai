# Style guide: Asking the Way at Azure Cloud

The agreed English voice for this novel. The translator follows it on every chapter.

## Prose voice
- Clear, grounded narration. Let the setting carry the atmosphere; do not over-decorate.
- Past tense, third person.
- Short-to-medium sentences. Break run-ons rather than stacking clauses.
- Keep the register a touch formal for elders and cultivators; looser for young disciples.

## Names and honorifics
- Personal names: romanized pinyin, no tone marks (Li Yun, not Lǐ Yún). Do not meaning-translate a
  personal name unless a character record says to.
- Honorifics render into English forms, kept consistent:
  - 师兄 -> Senior Brother, 师姐 -> Senior Sister
  - 师弟 -> Junior Brother, 师妹 -> Junior Sister
  - 长老 -> Elder, 掌门 -> Sect Master
- Landmarks and sect names are meaning-translated (Azure Cloud Peak, Azure Cloud Sect), not
  romanized, unless a location/faction record says otherwise.

## Cultivation terms
- Romanize load-bearing terms that have no clean English equal: qi, Dao. Keep them lowercase unless
  part of a proper name.
- Realm and technique names are locked on first appearance via the context files. Never re-coin one.

## Translator's notes
- Bracketed, inline, immediately after the phrase they explain.
- Two forms:
  - `[a short plain-English gloss]` for an idiom or hidden meaning.
  - `[Wordplay: ...]` on its own line for puns and deliberate double meanings.
- Add a note only when a trigger fires (see prompts/translate.md). Silence is the default.
- Never explain the same recurring idiom twice; a first-appearance note is enough (translation
  memory tracks which phrases were already annotated).

## Formatting
- One `# Chapter N: Title` heading per file, plus the YAML front matter block.
- Preserve paragraph breaks from the source; do not merge dialogue into narration.

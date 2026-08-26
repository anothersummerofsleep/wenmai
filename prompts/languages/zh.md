# Chinese source guidance (zh)

Source-language linguistics for Chinese-to-English translation. This overlay is appended to the
core translation prompt when a novel's `source_language` is `zh`. It holds the Chinese-specific
concerns that should NOT live in the language-neutral core.

## Extra annotation triggers (Chinese-specific)
- **成语 / chengyu and set idioms** whose four-character or literal form loses the point (e.g. 老狐狸
  "old fox" = shrewd and cunning, not literally aged).
- **Homophones and tonal wordplay**: characters chosen for sound (names, puns, taboo avoidance,
  lucky/unlucky numbers like 4 vs 死).
- **Classical and literary allusions**: lines echoing poetry, Journey to the West, the Analects,
  chengyu with a story behind them.
- **Double meanings in single characters** (e.g. 气 = qi/energy, but also temper/anger/cockiness).
- **Cultivation / xianxia-wuxia terminology** where the English risks flattening a distinction the
  Chinese keeps (realms, dao concepts, sect ranks). Defer to the novel's context files for the
  locked rendering.

## Naming conventions
- Personal names: pinyin without tone marks unless a character record says otherwise. Family name
  precedes given name in Chinese; keep the order the style guide specifies.
- Do not meaning-translate a personal name (e.g. do not turn 峰 into "Peak") unless a character
  record explicitly asks for it.
- Honorifics and kinship-as-address (师兄, 师姐, 长老, 掌门, 前辈) follow the style guide's honorific
  table; render consistently, and generally do not annotate common ones.

## Romanization
- Keep load-bearing terms that have no clean English equivalent romanized (qi, dao), lowercase
  unless part of a proper name. The context files are the authority on which terms stay romanized.

## Restraint
These triggers widen what *may* deserve a note; they do not lower the bar. Silence is still the
default. Never re-explain a phrase the translation memory shows was already annotated.

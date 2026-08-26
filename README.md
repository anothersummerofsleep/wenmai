# Wenmai / 文脉

**Translate the words. Preserve the thread.**

*A context-aware long-form translation framework for webnovels, starting with Chinese-to-English
translation.*

Wenmai is an open-source framework for context-aware long-form webnovel translation. Its scope is
multilingual by design; its first supported path is Chinese to English.

Webnovels can span hundreds or thousands of chapters. Understanding a single sentence may depend on
events, relationships, terminology, jokes, titles, or translation choices established hundreds of
chapters earlier. Wenmai is designed around that problem.

Rather than translating each chapter in isolation, Wenmai maintains persistent knowledge of the
story, including characters, aliases, relationships, factions, locations, terminology, abilities,
historical events, recurring jokes, and established translation decisions.

Its goal is not simply to produce fluent English. It is to preserve the meaning carried between the
lines.

When wordplay, idioms, homophones, cultural references, names, deliberate ambiguity, or other
linguistic details cannot survive naturally in translation, Wenmai can preserve readable prose while
providing concise contextual explanations where they genuinely matter.

Chinese-to-English is Wenmai's first supported translation path. The underlying architecture is
intended to support additional source languages over time, with language-specific linguistic
intelligence separated from the shared translation, context, memory, retrieval, consistency, and
evaluation systems.

The aim is to combine the consistency of a maintained translation project with the contextual
awareness of a human translator who has actually read the story.

See [MISSION.md](MISSION.md) for the fuller mission.

## Core principles

- **Context before translation.** Chapters should be translated with relevant narrative and
  linguistic history, not as isolated text.
- **Consistency across long-running stories.** Names, titles, techniques, locations, ranks,
  factions, relationships, and recurring terminology should remain coherent across hundreds or
  thousands of chapters.
- **Meaning over literalism.** English should read naturally without silently discarding information
  carried by the source language.
- **Explain what cannot be translated.** Wordplay, idioms, cultural references, double meanings, and
  other significant linguistic details can be preserved through concise annotations when necessary.
- **Language-aware, not language-bound.** Wenmai begins with Chinese-to-English translation, while
  keeping language-specific linguistic concerns separate from the core translation framework.
- **Human-reviewable by design.** Translation decisions, terminology changes, contextual knowledge,
  annotations, and chapter revisions should remain inspectable and version-controlled.

Wenmai treats translation not as sentence substitution, but as the preservation of a story's 文脉,
the thread of meaning and continuity running through the work.

**It is a tool, not a content repo.** Clone it, run it on your own machine, and point it at your
own novels. Your novels and translations live under `novels/` and are git-ignored by default, so
they stay local to you and never get committed or shared. The only novel that ships with the repo
is the invented `sample-novel` demo. Bring your own LLM access (either backend, see below).

## The annotation idea

The translator adds an inline note only when a literal rendering would silently drop information a
native reader would catch. Examples:

> He really was a 老狐狸, an "old fox" [a Chinese expression for someone extremely shrewd and
> experienced, not a literal comment on age].

> "You certainly have a lot of qi."
> [Wordplay: 气 can mean "qi/energy" but also "anger" or "temper." The speaker is deliberately
> playing on both.]

And, most of the time, nothing:

> Senior Brother Zhang entered the hall.

Triggers for a note: idioms whose literal form loses meaning, homophones, name jokes, internet
slang, poetry or classical references, scene-critical cultural references, puns, deliberate double
meanings, and terms where the natural English equivalent hides something the source made obvious.
See `prompts/translate.md` for the full rule.

## Repo layout

```
novels/<novel>/
  source/         ch0001_<src>.txt, ...                (immutable source; suffix = source_language)
  translated/     ch0001_<tgt>.md, ...                 (output; suffix = target_language; one PR/chapter)
  context/        characters.yaml terminology.yaml locations.yaml factions.yaml timeline.yaml
                  (+ any novel-specific files, e.g. cultivation_system.yaml, honorifics.yaml)
  translation_memory/phrases.jsonl                     (recurring idioms/jokes, first-seen refs)
  novel.yaml      per-novel config (source_language, target_language, title, prose style pointer)
  style_guide.md  the agreed target-language prose voice for this novel
prompts/          translate.md (language-neutral core), context_update.md, review.md
  languages/      zh.md, ...   (source-language linguistic overlays; ko planned)
scripts/          translate.py build_context.py consistency_check.py backends.py context.py
.github/workflows-example/translate.yml   (CI stub; move into .github/workflows/ to enable)
```

Everything a novel needs to know about its languages lives in `novel.yaml` as `source_language` /
`target_language`. The core loads whatever `*.yaml` a novel puts in `context/`, so genre- or
language-specific files can be added without a code change. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Pipeline (v1 = three passes)

```
Source (zh)  ->  [1] context retrieval  ->  [2] translate + annotate  ->  [3] consistency check  ->  Target (en)
                  (Python, mechanical)       (LLM)                         (Python, mechanical)
```

Source and target are whatever the novel declares; v1 ships and is tested for `zh -> en`.

Later this grows toward the full seven passes (semantic analysis, literary edit, context
extraction as separate stages, knowledge-graph retrieval). See "Roadmap" below.

## Backends (pluggable)

The LLM call is behind one interface (`scripts/backends.py`), so the same pipeline runs two ways:

- **`claude_code`** (default): no API key, no per-token billing. The script assembles the full
  prompt into `.runs/<novel>/<chapter>/<pass>.prompt.md`, and you (via Claude Code) write the
  answer to `<pass>.response.md`, then re-run to continue. Good for careful, reviewed translation.
- **`anthropic`**: calls the Claude API directly for unattended and CI runs. Needs
  `ANTHROPIC_API_KEY`. Enables the GitHub Actions auto-PR flow.

Pick the backend in `config.yaml` (copy from `config.example.yaml`) or with `--backend`.

## Quick start

```bash
python -m pip install -r requirements.txt
cp config.example.yaml config.yaml          # then edit if using the anthropic backend

# Translate one chapter (default claude_code backend = file handoff)
python scripts/translate.py --novel sample-novel --chapter 1

# Check terminology drift across everything already translated
python scripts/consistency_check.py --novel sample-novel

# Propose new context entries from a finished chapter (writes proposals for review)
python scripts/build_context.py --novel sample-novel --chapter 1
```

`novels/sample-novel/` ships as a tiny invented demo so every step runs end to end.

### Adding your own novel

```bash
mkdir -p novels/<your-novel>/{source,translated,context,translation_memory}
# add source/ch0001_zh.txt ... , then seed context/*.yaml and style_guide.md
# (copy sample-novel's files as templates)
python scripts/translate.py --novel <your-novel> --chapter 1
```

Everything under `novels/<your-novel>/` is git-ignored, so it stays on your machine. To version your
own translations in a private fork, remove the `novels/*` lines from `.gitignore` (or add a
`!novels/<your-novel>` exception).

## Why GitHub

Each chapter arrives as a pull request, so terminology changes, added notes, and new context
entries all show up as reviewable diffs. If you rename a term 600 chapters in, git history and
search make it feasible to find and fix every prior occurrence.

## Roadmap

- v1 (this): repo + Markdown chapters + YAML context + pluggable script + three-pass flow, for
  Chinese to English. The core is kept language-neutral so the next language pair is additive.
- Next: split translation into semantic / prose / literary-edit passes; automatic context
  extraction on merge; GitHub Actions auto-PRs on the `anthropic` backend.
- Later: additional source languages (Korean to English is the expected next pair, added as a
  `prompts/languages/ko.md` overlay plus any ko-specific context files, with no core rewrite); a
  small novel knowledge graph for retrieval; chapter ingestion from raw dumps; a reader interface.

## License

The tool (scripts, prompts, schema, and the invented `sample-novel`) is released under the
[MIT License](LICENSE). Use it, fork it, build on it.

## A note on rights

This project is translation *tooling*. It does not host, bundle, or distribute any copyrighted novel
content, and the maintainers are not responsible for what anyone translates with it. Web-novel
source text is copyrighted by its authors and publishers. You are responsible for how you obtain
source chapters and what you do with the output, including any redistribution. Keep your own novels
and translations local (that is the default; see "It is a tool, not a content repo" above). The
shipped `sample-novel` is fully invented for this repo.

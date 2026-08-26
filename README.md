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
intelligence separated from the shared systems for translation, context, memory, retrieval, and
consistency. (A dedicated evaluation system is planned, not yet built; see Status below.)

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
  source/         ch00001_<src>.txt, ...                (immutable source; suffix = source_language)
  translated/     ch00001_<tgt>.md, ...                 (output; suffix = target_language; one PR/chapter)
  context/        characters.yaml terminology.yaml locations.yaml factions.yaml timeline.yaml
                  (+ any novel-specific files, e.g. cultivation_system.yaml, honorifics.yaml)
  translation_memory/phrases.jsonl                     (recurring idioms/jokes, first-seen refs)
  novel.yaml      per-novel config (source_language, target_language, title, prose style pointer)
  style_guide.md  the agreed target-language prose voice for this novel
prompts/          translate.md (language-neutral core), context_update.md, review.md
  languages/      zh.md, ...   (source-language linguistic overlays; ko planned)
scripts/          translate.py build_context.py consistency_check.py validate.py
                  benchmark.py backends.py context.py
benchmarks/       <id>/manifest.yaml (metadata only), README.md, results/   (public; no prose)
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

A backend is only about how and where the model is called (transport and provider), never about
language. The call is behind one interface (`scripts/backends.py`), so the same pipeline runs two
ways:

- **`claude_code`** (default): no API key, no per-token billing. The script assembles the full
  prompt into `.runs/<novel>/<chapter>/<pass>.prompt.md`, and you (via Claude Code) write the
  answer to `<pass>.response.md`, then re-run to continue. Good for careful, reviewed translation.
- **`anthropic`**: calls the Claude API directly for unattended runs. Needs `ANTHROPIC_API_KEY`.
  This is what a future CI workflow would use.

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
# add source/ch00001_zh.txt ... , then seed context/*.yaml and style_guide.md
# (copy sample-novel's files as templates)
python scripts/translate.py --novel <your-novel> --chapter 1
```

Everything under `novels/<your-novel>/` is git-ignored, so it stays on your machine. To version your
own translations in a private fork, remove the `novels/*` lines from `.gitignore` (or add a
`!novels/<your-novel>` exception).

## Chapter file convention

Source and translated chapters are named `ch<NNNNN>_<language>.txt` / `.md`, where `<NNNNN>` is a
zero-padded 5-digit chapter number and `<language>` is the novel's `source_language` /
`target_language`:

```
source/ch00001_zh.txt   translated/ch00001_en.md
source/ch00002_zh.txt   translated/ch00002_en.md
```

The pipeline resolves chapters by this exact pattern (no arbitrary filename ingestion).
`scripts/validate.py` flags files that look like chapters but do not match.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest

# Validate a novel's persistent state (YAML/JSONL validity, language config,
# malformed avoid/fields, translation-memory lines, duplicate canonical entries):
python scripts/validate.py --novel sample-novel
```

The suite covers language configuration and validation, context loading, translation continuity,
consistency checking, the Claude Code handoff backend, and an end-to-end pipeline run on the bundled
`sample-novel` using a fake backend (no API calls). It tests behaviour, not implementation details.

## Why GitHub

Wenmai is designed so chapter translations and context changes can be reviewed as Git diffs and, in
future automated workflows, surfaced as pull requests. Today you run the scripts locally and commit
the results yourself; the diffs still show every terminology change, added note, and new context
entry. If you rename a term 600 chapters in, git history and search make it feasible to find and fix
every prior occurrence.

## Benchmarks

A controlled A/B/C benchmark tests whether structured persistent memory beats a plain rolling
context window, on real long-form fiction. The harness (`scripts/benchmark.py`) and manifests are
public; all corpus text (source, official reference, generated candidates) stays local and
git-ignored. See [benchmarks/README.md](benchmarks/README.md) for conditions, blinding, evaluation
dimensions, and methodology caveats.

## Status: implemented vs planned

Implemented in v1 (this repo, tested for `zh -> en`):
- Three-pass flow: context retrieval, LLM translate + annotate, terminology-drift consistency check.
- Per-novel context records, translation memory, and language-neutral core with a `zh` overlay.
- Pluggable backends (`claude_code` handoff, `anthropic` API).
- Context-extraction pass that proposes reviewable additions (never auto-applied).
- State validator (`scripts/validate.py`).
- A/B/C benchmark harness (`scripts/benchmark.py`) with blinding and deterministic + human eval.

Planned, NOT yet built:
- A dedicated evaluation system (automated scoring beyond the benchmark's deterministic checks;
  human review and the benchmark harness exist, but there is no standalone eval pipeline yet).
- Automated GitHub Actions that translate on push and open pull requests (the workflow in
  `.github/workflows-example/` is a disabled stub, not an active pipeline).
- Split semantic / literary-edit passes; knowledge-graph or embedding retrieval; automatic merging
  of accepted proposals; additional source languages.

## Roadmap

- v1 (this): repo + Markdown chapters + YAML context + pluggable script + three-pass flow, for
  Chinese to English. The core is kept language-neutral so the next language pair is additive.
- Next: split translation into semantic / prose / literary-edit passes; automatic context
  extraction on merge; a real GitHub Actions workflow (on the `anthropic` backend) that opens PRs.
- Later: a dedicated evaluation system; additional source languages (Korean to English is the
  expected next pair, added as a `prompts/languages/ko.md` overlay plus any ko-specific context
  files, with no core rewrite); a small novel knowledge graph for retrieval; chapter ingestion from
  raw dumps; a reader interface.

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

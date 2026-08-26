# Wenmai · 文脉

**Context-aware Chinese-to-English webnovel translation with terminology consistency, narrative
memory, and inline wordplay explanations.**

> 文脉 (wénmài): the literary thread of meaning and continuity that runs through a text. This tool
> tries to keep that thread intact across an entire novel, not just one chapter at a time.

A version-controlled fan-translation pipeline for web novels. It treats a novel as a
long-running translation project with a persistent **translator's notebook**, not a stack of
isolated chapter jobs. The goal is *good fan translation with translator intelligence*, not raw
machine translation: it keeps context across hundreds of chapters, enforces consistent
terminology, and annotates wordplay in brackets only when a note actually earns its place.

Source language for v1 is Chinese (`zh`). The structure is built so Korean (`ko`) slots in later
without a rewrite.

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
  source/         ch0001_zh.txt, ch0002_zh.txt, ...   (immutable source)
  translated/     ch0001_en.md, ...                    (output; one PR per chapter)
  context/        characters.yaml terminology.yaml locations.yaml
                  factions.yaml cultivation_system.yaml timeline.yaml
  translation_memory/phrases.jsonl                     (recurring idioms/jokes, first-seen refs)
  novel.yaml      per-novel config (source language, title, prose style pointer)
  style_guide.md  the agreed English prose voice for this novel
prompts/          translate.md, context_update.md, review.md
scripts/          translate.py build_context.py consistency_check.py backends.py context.py
.github/workflows/translate.yml   (CI stub, disabled until API backend is chosen)
```

## Pipeline (v1 = three passes)

```
Chinese  ->  [1] context retrieval  ->  [2] translate + annotate  ->  [3] consistency check  ->  English
              (Python, mechanical)       (LLM)                         (Python, mechanical)
```

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

- v1 (this): repo + Markdown chapters + YAML context + pluggable script + three-pass flow.
- Next: split translation into semantic / prose / literary-edit passes; automatic context
  extraction on merge; GitHub Actions auto-PRs on the `anthropic` backend.
- Later: a small novel knowledge graph (entities and relations) for retrieval; chapter ingestion
  from raw dumps; a reader interface; Korean source support.

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

"""Context loading is open-ended and ignores internal/underscore files."""
from scripts import context


CHARACTERS = "characters:\n  hero:\n    source: 主角\n    english: Hero\n"
HONORIFICS = "honorifics:\n  hyung:\n    english: older brother\n"


def test_generic_context_files_load(make_novel):
    novel = make_novel(contexts={"characters.yaml": CHARACTERS})
    records = context.load_context_records(novel)
    assert "characters" in records
    assert "Hero" in records


def test_arbitrary_context_file_discovered_without_code_change(make_novel):
    novel = make_novel(contexts={"characters.yaml": CHARACTERS, "honorifics.yaml": HONORIFICS})
    names = [p.name for p in context.context_files(novel)]
    assert "honorifics.yaml" in names
    assert "honorifics" in context.load_context_records(novel)


def test_underscore_prefixed_files_not_loaded(make_novel):
    novel = make_novel(contexts={
        "characters.yaml": CHARACTERS,
        "_draft.yaml": "characters:\n  ghost:\n    english: ShouldNotLoad\n",
    })
    names = [p.name for p in context.context_files(novel)]
    assert "_draft.yaml" not in names
    assert "ShouldNotLoad" not in context.load_context_records(novel)


def test_context_records_are_chapter_bounded(make_novel):
    novel = make_novel(contexts={"characters.yaml": (
        "characters:\n"
        "  early:\n    english: EarlyFact\n    first_seen: ch00001\n"
        "  later:\n    english: LaterFact\n    first_seen: ch00003\n"
    )})
    bounded = context.load_context_records(novel, max_chapter=2)
    assert "EarlyFact" in bounded and "LaterFact" not in bounded
    # Unbounded (normal pipeline) still sees everything.
    both = context.load_context_records(novel)
    assert "EarlyFact" in both and "LaterFact" in both


def test_chapter_bounding_prunes_nested_records(make_novel):
    novel = make_novel(contexts={"cultivation_system.yaml": (
        "realms:\n"
        "  - english: R1\n    first_seen: ch00001\n"
        "  - english: R2\n    first_seen: ch00005\n"
    )})
    bounded = context.load_context_records(novel, max_chapter=3)
    assert "R1" in bounded and "R2" not in bounded


def test_translation_memory_is_chapter_bounded(make_novel):
    novel = make_novel(phrases=[
        '{"source": "甲", "gloss": "early-phrase", "first_seen": "ch00001"}',
        '{"source": "乙", "gloss": "late-phrase", "first_seen": "ch00004"}',
    ])
    bounded = context.load_translation_memory(novel, max_chapter=3)
    assert "early-phrase" in bounded and "late-phrase" not in bounded


def test_preferred_files_sort_before_extras(make_novel):
    novel = make_novel(contexts={
        "cultivation_system.yaml": "concepts: {}\n",  # extra/genre file
        "characters.yaml": CHARACTERS,                 # preferred, must come first
    })
    names = [p.name for p in context.context_files(novel)]
    assert names.index("characters.yaml") < names.index("cultivation_system.yaml")

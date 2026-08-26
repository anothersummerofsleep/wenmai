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


def test_preferred_files_sort_before_extras(make_novel):
    novel = make_novel(contexts={
        "cultivation_system.yaml": "concepts: {}\n",  # extra/genre file
        "characters.yaml": CHARACTERS,                 # preferred, must come first
    })
    names = [p.name for p in context.context_files(novel)]
    assert names.index("characters.yaml") < names.index("cultivation_system.yaml")

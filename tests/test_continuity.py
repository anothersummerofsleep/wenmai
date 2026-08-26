"""Previous-chapter resolution uses the target language and never pulls future chapters."""
from scripts import context


def test_previous_translations_use_target_language(make_novel):
    novel = make_novel(
        config={"source_language": "zh", "target_language": "fr"},
        translations={1: "un", 2: "deux", 3: "trois"},
    )
    # Files were written as ch000N_fr.md; resolution must find them via target_language.
    prevs = context.previous_translations(novel, chapter=3, n=2)
    assert [n for n, _ in prevs] == [1, 2]
    assert [t for _, t in prevs] == ["un", "deux"]


def test_only_previous_not_future(make_novel):
    novel = make_novel(translations={1: "a", 2: "b", 3: "c"})
    prevs = context.previous_translations(novel, chapter=2, n=5)
    assert [n for n, _ in prevs] == [1]  # ch3 (future) excluded even with a large window


def test_list_translated_chapters_sorted(make_novel):
    novel = make_novel(translations={2: "b", 1: "a", 3: "c"})
    names = [p.name for p in context.list_translated_chapters(novel)]
    assert names == ["ch0001_en.md", "ch0002_en.md", "ch0003_en.md"]


def test_translation_memory_loaded_when_present(make_novel):
    line = '{"source": "老狐狸", "gloss": "old fox"}'
    novel = make_novel(phrases=[line])
    assert "old fox" in context.load_translation_memory(novel)


def test_translation_memory_absent_returns_empty(make_novel):
    novel = make_novel()  # no phrases file
    assert context.load_translation_memory(novel) == ""

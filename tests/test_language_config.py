"""Language configuration must be explicit and validated; no silent zh->en fallback."""
import pytest

from scripts import context, translate


def test_reads_explicit_languages(make_novel):
    novel = make_novel(config={"source_language": "zh", "target_language": "en"})
    assert context.source_language(novel) == "zh"
    assert context.target_language(novel) == "en"


def test_source_path_derives_from_source_language(make_novel):
    novel = make_novel(config={"source_language": "ko", "target_language": "en"})
    assert context.source_path(novel, 1).name == "ch0001_ko.txt"


def test_translated_path_derives_from_target_language(make_novel):
    novel = make_novel(config={"source_language": "zh", "target_language": "fr"})
    assert context.translated_path(novel, 7).name == "ch0007_fr.md"


def test_missing_novel_yaml_raises(make_novel):
    novel = make_novel(config=None)  # no novel.yaml written
    with pytest.raises(context.ConfigError):
        context.source_language(novel)


def test_missing_source_language_raises(make_novel):
    novel = make_novel(config={"target_language": "en"})
    with pytest.raises(context.ConfigError):
        context.source_language(novel)


def test_empty_target_language_raises(make_novel):
    novel = make_novel(config={"source_language": "zh", "target_language": "  "})
    with pytest.raises(context.ConfigError):
        context.target_language(novel)


def test_malformed_language_raises(make_novel):
    novel = make_novel(config={"source_language": ["zh"], "target_language": "en"})
    with pytest.raises(context.ConfigError):
        context.source_language(novel)


def test_zh_overlay_is_loaded():
    overlay = context.load_language_prompt("zh")
    assert overlay.strip()
    assert "chengyu" in overlay.lower()


def test_language_without_overlay_still_runs_core_prompt(make_novel):
    # 'xx' has no prompts/languages/xx.md; the core prompt must still assemble.
    novel = make_novel(config={"source_language": "xx", "target_language": "en"})
    assert context.load_language_prompt("xx") == ""
    system = translate.build_system_prompt(novel, prev_n=2)
    assert "# Source-language guidance (xx)" not in system  # no overlay block appended
    assert "translator" in system.lower()                   # core prompt present


def test_zh_overlay_is_appended_to_system_prompt(make_novel):
    novel = make_novel(config={"source_language": "zh", "target_language": "en"})
    system = translate.build_system_prompt(novel, prev_n=2)
    assert "Source-language guidance (zh)" in system
    assert "{SOURCE_LANGUAGE}" not in system and "{TARGET_LANGUAGE}" not in system

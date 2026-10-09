"""Opt-in consistency settings: checking `source/` documents and inclusive first_seen bounding.

Invented same-language (en -> en) workspaces only. Source and translated copies are given
DIFFERENT text so each test proves which document the checker actually read.
"""
from __future__ import annotations

import socket
import subprocess
import sys

import pytest

from scripts import backends, consistency_check, context, translate

EN = {"source_language": "en", "target_language": "en"}
SOURCE_MODE = {**EN, "consistency": {"documents": "source"}}
SOURCE_INCLUSIVE = {**EN, "consistency": {"documents": "source", "first_seen": "inclusive"}}

CANON = (
    "characters:\n"
    "  mara:\n    english: Mara Vell\n    avoid: [Marra Vell, Mara Vel]\n    first_seen: ch00001\n"
    "  oren:\n    english: Oren Hale\n    avoid: [Oran Hale]\n    first_seen: ch00002\n"
    "  later:\n    english: Ilsa Grey\n    avoid: [Ilsa Gray]\n    first_seen: ch00003\n"
)


def _ws(make_novel, config, *, sources=None, translations=None):
    return make_novel(config=config, sources=sources or {}, translations=translations or {},
                      contexts={"characters.yaml": CANON})


def _banned(findings):
    return sorted((f.chapter_file, f.banned) for f in findings)


# --------------------------------------------------------------------------- defaults unchanged

def test_default_reads_translated_and_is_exclusive(make_novel):
    novel = _ws(make_novel, EN,
                sources={1: "Marra Vell in the source only.", 2: "Oran Hale in the source only."},
                translations={1: "Marra Vell, translated.", 2: "Mara Vel and Oran Hale, translated."})
    assert consistency_check.settings(novel) == ("translated", "exclusive")
    # ch1: the ch1 rule is not active in its own chapter (first_seen < 1 is false).
    assert consistency_check.check_novel(novel, 1) == []
    # ch2: the ch1 rule applies, the ch2 rule does not; source text is never read.
    assert _banned(consistency_check.check_novel(novel, 2)) == [("ch00002_en.md", "Mara Vel")]
    # Whole-workspace audit: full canon, translated files only.
    assert _banned(consistency_check.check_novel(novel)) == [
        ("ch00001_en.md", "Marra Vell"), ("ch00002_en.md", "Mara Vel"), ("ch00002_en.md", "Oran Hale")]


def test_explicit_translated_exclusive_equals_default(make_novel):
    explicit = {**EN, "consistency": {"documents": "translated", "first_seen": "exclusive"}}
    a = _ws(make_novel, EN, translations={2: "Mara Vel and Oran Hale."})
    b = make_novel("explicit", config=explicit, translations={2: "Mara Vel and Oran Hale."},
                   contexts={"characters.yaml": CANON})
    for ch in (None, 1, 2):
        assert _banned(consistency_check.check_novel(a, ch)) == _banned(consistency_check.check_novel(b, ch))


# --------------------------------------------------------------------------- source documents

def test_source_mode_reads_source_not_translated_copies(make_novel):
    novel = _ws(make_novel, SOURCE_MODE,
                sources={2: "Mara Vel walked in."},
                translations={2: "Ilsa Gray in the translated copy only."})
    assert _banned(consistency_check.check_novel(novel, 2)) == [("ch00002_en.txt", "Mara Vel")]
    assert _banned(consistency_check.check_novel(novel)) == [("ch00002_en.txt", "Mara Vel")]


def test_source_mode_whole_workspace_lists_source_chapters_in_order(make_novel):
    novel = _ws(make_novel, SOURCE_MODE,
                sources={2: "Oran Hale.", 1: "Marra Vell.", 10: "Ilsa Gray."})
    assert [f.chapter_file for f in consistency_check.check_novel(novel)] == [
        "ch00001_en.txt", "ch00002_en.txt", "ch00010_en.txt"]


def test_source_mode_missing_chapter_is_no_findings(make_novel):
    novel = _ws(make_novel, SOURCE_MODE, sources={1: "Mara Vell."})
    assert consistency_check.check_novel(novel, 7) == []  # same as translated mode


# --------------------------------------------------------------------------- inclusive first_seen

def test_inclusive_detects_error_in_the_establishing_chapter(make_novel):
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={1: "Marra Vell walked the shore."})
    assert _banned(consistency_check.check_novel(novel, 1)) == [("ch00001_en.txt", "Marra Vell")]


def test_exclusive_source_mode_misses_establishing_chapter(make_novel):
    novel = _ws(make_novel, SOURCE_MODE, sources={1: "Marra Vell walked the shore."})
    assert consistency_check.check_novel(novel, 1) == []  # documented exclusive behaviour


def test_inclusive_still_excludes_later_rules(make_novel):
    novel = _ws(make_novel, SOURCE_INCLUSIVE,
                sources={2: "Oran Hale met Ilsa Gray."})
    # ch2 rule applies in ch2 (inclusive); the ch3 rule does not yet.
    assert _banned(consistency_check.check_novel(novel, 2)) == [("ch00002_en.txt", "Oran Hale")]


def test_inclusive_whole_workspace_uses_full_canon(make_novel):
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={1: "Ilsa Gray appears early."})
    assert _banned(consistency_check.check_novel(novel)) == [("ch00001_en.txt", "Ilsa Gray")]


def test_inclusive_works_with_translated_documents(make_novel):
    config = {**EN, "consistency": {"first_seen": "inclusive"}}
    novel = _ws(make_novel, config, translations={1: "Marra Vell."})
    assert _banned(consistency_check.check_novel(novel, 1)) == [("ch00001_en.md", "Marra Vell")]


# --------------------------------------------------------------------------- matching preserved

def test_matching_rules_preserved_in_source_mode(make_novel):
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={
        1: "marra vell waved.\nMarra Vell's coat.\nMara Vellum is someone else.\nMara Vell is right."})
    hits = consistency_check.check_novel(novel, 1)
    # Case-insensitive, word-bounded: possessive matches, a longer word does not.
    assert [(f.line_no, f.banned) for f in hits] == [(1, "Marra Vell"), (2, "Marra Vell")]


# --------------------------------------------------------------------------- retrieval untouched

def test_retrieval_bounding_unaffected_by_inclusive_setting(make_novel):
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={1: "x"})
    records = context.load_context_records(novel, max_chapter=1)
    assert "Mara Vell" not in records  # shared retrieval stays first_seen < chapter


def test_translate_pass3_pinned_to_translation_contract(make_novel, monkeypatch, capsys):
    # Source contains a banned variant and the ch1 rule would apply inclusively; pass 3 must still
    # check only the translation, exclusively, so it reports clean.
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={1: "Marra Vell in the source."})

    class Fake:
        name = "fake"

        def complete(self, system, user, *, tag):
            return "---\nchapter: 1\n---\n\n# Chapter 1\n\nMarra Vell, translated.\n"

    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: Fake())
    assert translate.run(novel, 1, None, force=True) == 0
    assert "[pass 3] OK - no terminology drift." in capsys.readouterr().out


# --------------------------------------------------------------------------- config errors + CLI

@pytest.mark.parametrize("block", ["source", {"documents": "manuscript"}, {"first_seen": "yes"}])
def test_invalid_settings_raise_config_error(make_novel, block):
    novel = _ws(make_novel, {**EN, "consistency": block}, sources={1: "x"})
    with pytest.raises(context.ConfigError):
        consistency_check.check_novel(novel, 1)


def test_cli_reports_config_error_cleanly(make_novel, monkeypatch, capsys):
    novel = _ws(make_novel, {**EN, "consistency": {"documents": "manuscript"}}, sources={1: "x"})
    monkeypatch.setattr(sys, "argv", ["consistency_check.py", "--novel", novel])
    assert consistency_check.main() == 2
    assert capsys.readouterr().out.startswith("[error] ")


def test_cli_source_mode_makes_no_external_calls(make_novel, monkeypatch, capsys):
    def blocked(*a, **k):
        raise AssertionError("consistency check must not start processes or open sockets")

    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    novel = _ws(make_novel, SOURCE_INCLUSIVE, sources={1: "Marra Vell."})
    monkeypatch.setattr(sys, "argv", ["consistency_check.py", "--novel", novel, "--chapter", "1"])
    assert consistency_check.main() == 1
    out = capsys.readouterr().out
    assert "ch00001_en.txt:1  'Marra Vell' -> use 'Mara Vell'" in out  # output format unchanged

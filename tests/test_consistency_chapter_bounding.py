"""Per-chapter consistency checks are chapter-bounded by first_seen.

`consistency_check.check_novel(novel, N)` (also Pass 3 of translate.py) must apply only terminology
`avoid` rules whose record has first_seen < N, so regenerating an early chapter is never flagged by a
rule that did not exist yet. The standalone whole-novel check (no chapter) keeps using the full
current canonical state as a retroactive audit.
"""
from __future__ import annotations

import pytest

from scripts import backends, consistency_check, translate


def _term(first_seen: str) -> str:
    return (
        "terms:\n"
        "  widget:\n"
        "    source: 甲\n"
        "    preferred: Widget\n"
        f"    first_seen: {first_seen}\n"
        "    avoid:\n"
        "      - Gadget\n"
    )


def test_prior_rule_is_applied(make_novel):
    novel = make_novel(
        contexts={"terminology.yaml": _term("ch00002")},
        translations={5: "He held the Gadget."},
    )
    findings = consistency_check.check_novel(novel, 5)
    assert [f.banned for f in findings] == ["Gadget"]  # first_seen ch00002 < 5 -> active


def test_same_chapter_rule_is_not_applied(make_novel):
    novel = make_novel(
        contexts={"terminology.yaml": _term("ch00005")},
        translations={5: "He held the Gadget."},
    )
    assert consistency_check.check_novel(novel, 5) == []  # first_seen ch00005 == 5 -> inactive


def test_future_rule_is_not_applied(make_novel):
    novel = make_novel(
        contexts={"terminology.yaml": _term("ch00010")},
        translations={5: "He held the Gadget."},
    )
    assert consistency_check.check_novel(novel, 5) == []  # first_seen ch00010 > 5 -> inactive


def test_whole_novel_check_uses_full_current_state(make_novel):
    # No --chapter: retroactive audit against the CURRENT state, ignoring first_seen bounding.
    novel = make_novel(
        contexts={"terminology.yaml": _term("ch00010")},
        translations={5: "He held the Gadget."},
    )
    findings = consistency_check.check_novel(novel)
    assert [f.banned for f in findings] == ["Gadget"]


def test_translate_pass3_ignores_future_rule(make_novel, monkeypatch):
    novel = make_novel(
        contexts={"terminology.yaml": _term("ch00010")},
        sources={5: "source five"},
    )

    class CaptureBackend(backends.LLMBackend):
        name = "capture"

        def complete(self, system, user, *, tag):
            return "# Chapter 5\n\nHe held the Gadget.\n"

    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: CaptureBackend())
    assert translate.run(novel, 5, "capture", force=True) == 0

    # Pass 3 (chapter-bounded) must not flag the future ch00010 rule...
    assert consistency_check.check_novel(novel, 5) == []
    # ...but the rule does exist: a whole-novel audit still catches it.
    assert [f.banned for f in consistency_check.check_novel(novel)] == ["Gadget"]

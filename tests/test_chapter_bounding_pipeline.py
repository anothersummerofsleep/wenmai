"""Normal-pipeline chapter-bounding parity.

The benchmark bounds canonical state / translation memory so translating chapter i only sees durable
records with first_seen < i. These tests prove the NORMAL pipeline (scripts/translate.py and
scripts/build_context.py) now applies the same boundary, by capturing the exact prompt each script
hands to the backend.

Invariant: chapter i sees first_seen < i (e.g. chapter 1 sees no ch00001+ record; chapter 3 sees
ch00001/ch00002 but not ch00003+). The current source chapter and previous translated chapters are
unaffected.
"""
from __future__ import annotations

import pytest

from scripts import backends, build_context, context, translate

CHARACTERS = """\
characters:
- source: 甲
  english: AlphaName
  first_seen: ch00001
- source: 乙
  english: BetaName
  first_seen: ch00002
- source: 丙
  english: GammaName
  first_seen: ch00003
- source: 戊
  english: EpsilonName
  first_seen: ch00005
"""

PHRASES = [
    '{"source": "P1", "gloss": "phrase-one-PONE", "first_seen": "ch00001"}',
    '{"source": "P3", "gloss": "phrase-three-PTHREE", "first_seen": "ch00003"}',
]


class CaptureBackend(backends.LLMBackend):
    """Records the (system, user) it is asked to complete; returns a fixed translation."""
    name = "capture"

    def __init__(self):
        self.system = None
        self.user = None

    def complete(self, system: str, user: str, *, tag: str) -> str:
        self.system, self.user = system, user
        return "# Captured\n\nplaceholder translation body.\n"


@pytest.fixture
def bounded_novel(make_novel, monkeypatch):
    slug = make_novel(
        "bnd",
        sources={1: "src one", 2: "src two", 3: "MARKER_CH3 body three",
                 4: "src four", 5: "src five"},
        translations={1: "TRANS_CH1 body", 2: "TRANS_CH2 body",
                      3: "OLD_TRANS_CH3 body", 4: "TRANS_CH4 body"},
        contexts={"characters.yaml": CHARACTERS},
        phrases=PHRASES,
    )
    cap = CaptureBackend()
    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: cap)
    return slug, cap


def test_translation_includes_records_first_seen_before_chapter(bounded_novel):
    slug, cap = bounded_novel
    assert translate.run(slug, 3, "capture", force=True) == 0
    assert "AlphaName" in cap.user      # first_seen ch00001 < 3
    assert "BetaName" in cap.user       # first_seen ch00002 < 3


def test_translation_excludes_records_first_seen_at_or_after_chapter(bounded_novel):
    slug, cap = bounded_novel
    translate.run(slug, 3, "capture", force=True)
    assert "GammaName" not in cap.user   # first_seen ch00003 == 3, excluded
    assert "EpsilonName" not in cap.user  # first_seen ch00005 > 3, excluded


def test_translation_memory_obeys_the_same_rule(bounded_novel):
    slug, cap = bounded_novel
    translate.run(slug, 3, "capture", force=True)
    assert "phrase-one-PONE" in cap.user      # ch00001 < 3
    assert "phrase-three-PTHREE" not in cap.user  # ch00003 == 3, excluded


def test_previous_translated_chapters_still_load(bounded_novel):
    slug, cap = bounded_novel
    translate.run(slug, 3, "capture", force=True)
    # previous_chapters default is 2 -> chapters 1 and 2
    assert "TRANS_CH2 body" in cap.user


def test_current_source_chapter_is_fully_present(bounded_novel):
    slug, cap = bounded_novel
    translate.run(slug, 3, "capture", force=True)
    assert "MARKER_CH3 body three" in cap.user


def test_extraction_sees_prior_canon_only_but_full_source_and_translation(bounded_novel):
    slug, cap = bounded_novel
    assert build_context.run(slug, 3, "capture") == 0
    # prior canon bounded to first_seen < 3
    assert "AlphaName" in cap.user and "BetaName" in cap.user
    assert "GammaName" not in cap.user and "EpsilonName" not in cap.user
    # full source + finished translation for chapter 3 are the new evidence
    assert "MARKER_CH3 body three" in cap.user
    assert "OLD_TRANS_CH3 body" in cap.user


def test_retranslating_an_older_chapter_cannot_leak_later_state(bounded_novel):
    slug, cap = bounded_novel
    # Retranslate chapter 2 after ch00003 / ch00005 state exists on disk.
    translate.run(slug, 2, "capture", force=True)
    assert "AlphaName" in cap.user        # ch00001 < 2, visible
    assert "BetaName" not in cap.user     # ch00002 == 2, excluded
    assert "GammaName" not in cap.user    # ch00003 > 2, no backward leak
    assert "EpsilonName" not in cap.user  # ch00005 > 2, no backward leak

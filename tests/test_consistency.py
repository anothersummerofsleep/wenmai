"""Terminology-drift detection: banned variants, nested structures, and script-aware matching."""
from scripts import consistency_check


TERMS = (
    "terms:\n"
    "  qi:\n"
    "    source: 气\n"
    "    preferred: qi\n"
    "    avoid:\n"
    "      - chi\n"
)

# Nested + open-ended: a genre file with a list and a deeper mapping, both carrying `avoid`.
NESTED = (
    "realms:\n"
    "  - source: 炼气\n"
    "    english: Qi Refining\n"
    "    avoid:\n"
    "      - Qi Condensation\n"
    "concepts:\n"
    "  foo:\n"
    "    english: Foo\n"
    "    avoid:\n"
    "      - Bar\n"
)

# Non-ASCII banned variant (a wrong rendering of a place name).
LOCATIONS = (
    "locations:\n"
    "  peak:\n"
    "    source: 青云峰\n"
    "    english: Azure Cloud Peak\n"
    "    avoid:\n"
    "      - 青雲峰\n"
)


def test_detects_banned_variant_and_reports_preferred(make_novel):
    novel = make_novel(
        contexts={"terminology.yaml": TERMS},
        translations={1: "The pure chi swirled around him."},
    )
    findings = consistency_check.check_novel(novel, 1)
    assert len(findings) == 1
    assert findings[0].banned == "chi"
    assert findings[0].preferred == "qi"


def test_ascii_uses_word_boundary_not_substring(make_novel):
    # 'chi' inside 'chirping' must NOT match; a standalone 'chi' must.
    novel = make_novel(
        contexts={"terminology.yaml": TERMS},
        translations={1: "the chirping of birds", 2: "a wisp of chi remained"},
    )
    all_findings = consistency_check.check_novel(novel)
    hit_files = {f.chapter_file for f in all_findings}
    assert "ch00002_en.md" in hit_files
    assert "ch00001_en.md" not in hit_files


def test_nested_open_ended_structures(make_novel):
    novel = make_novel(
        contexts={"cultivation_system.yaml": NESTED},
        translations={1: "He used Qi Condensation, then invoked Bar."},
    )
    banned = {f.banned for f in consistency_check.check_novel(novel, 1)}
    assert banned == {"Qi Condensation", "Bar"}


def test_non_ascii_substring_match(make_novel):
    novel = make_novel(
        contexts={"locations.yaml": LOCATIONS},
        translations={1: "他望向青雲峰。"},
    )
    findings = consistency_check.check_novel(novel, 1)
    assert len(findings) == 1
    assert findings[0].banned == "青雲峰"
    assert findings[0].preferred == "Azure Cloud Peak"


def test_clean_translation_has_no_findings(make_novel):
    novel = make_novel(
        contexts={"terminology.yaml": TERMS},
        translations={1: "His qi flowed smoothly."},
    )
    assert consistency_check.check_novel(novel, 1) == []

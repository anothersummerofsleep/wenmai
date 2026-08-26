"""Light state validator: structural checks, not a rigid schema."""
from scripts import validate


def _messages(issues, severity=None):
    return [i for i in issues if severity is None or i.severity == severity]


def test_clean_novel_has_no_issues(make_novel):
    novel = make_novel(contexts={
        "terminology.yaml": "terms:\n  qi:\n    source: 气\n    preferred: qi\n    avoid:\n      - chi\n",
    })
    assert validate.validate_novel(novel) == []


def test_invalid_yaml_is_an_error(make_novel):
    novel = make_novel(contexts={"characters.yaml": "characters:\n  - [unbalanced\n"})
    errs = _messages(validate.validate_novel(novel), "error")
    assert any("context/characters.yaml" in e.file for e in errs)


def test_malformed_avoid_is_an_error(make_novel):
    novel = make_novel(contexts={"terminology.yaml": "terms:\n  qi:\n    preferred: qi\n    avoid: chi\n"})
    errs = _messages(validate.validate_novel(novel), "error")
    assert any("avoid" in e.message for e in errs)


def test_wrong_type_preferred_is_a_warning(make_novel):
    novel = make_novel(contexts={"terminology.yaml": "terms:\n  qi:\n    preferred:\n      - qi\n"})
    warns = _messages(validate.validate_novel(novel), "warning")
    assert any("preferred" in w.message for w in warns)


def test_duplicate_canonical_is_a_warning(make_novel):
    novel = make_novel(contexts={
        "terminology.yaml": "terms:\n  a:\n    preferred: Qi\n  b:\n    preferred: Qi\n",
    })
    warns = _messages(validate.validate_novel(novel), "warning")
    assert any("duplicate" in w.message.lower() or "conflict" in w.message.lower() for w in warns)


def test_missing_language_config_is_an_error(make_novel):
    novel = make_novel(config={"target_language": "en"})  # no source_language
    errs = _messages(validate.validate_novel(novel), "error")
    assert any("source_language" in e.message for e in errs)


def test_invalid_jsonl_line_is_an_error(make_novel):
    novel = make_novel(phrases=["not json", '{"source": "x"}'])
    errs = _messages(validate.validate_novel(novel), "error")
    assert any("line 1" in e.locator and "JSON" in e.message for e in errs)


def test_translation_memory_missing_source_is_an_error(make_novel):
    novel = make_novel(phrases=['{"gloss": "old fox"}'])
    errs = _messages(validate.validate_novel(novel), "error")
    assert any("source" in e.message for e in errs)


def test_require_first_seen_flags_missing_record(make_novel):
    novel = make_novel(contexts={"characters.yaml": "characters:\n  a:\n    english: A\n"})
    strict = validate.validate_novel(novel, require_first_seen=True)
    assert any("first_seen" in i.message and i.severity == "error" for i in strict)
    # Lenient (default) does not require it, so general novels stay unaffected.
    assert not any("first_seen" in i.message for i in validate.validate_novel(novel))


def test_require_first_seen_flags_unparsable(make_novel):
    novel = make_novel(contexts={
        "characters.yaml": "characters:\n  a:\n    english: A\n    first_seen: soon\n"})
    strict = validate.validate_novel(novel, require_first_seen=True)
    assert any("first_seen" in i.message and i.severity == "error" for i in strict)


def test_require_first_seen_rejects_parsable_but_non_canonical(make_novel):
    # Values the lenient parser could read (integer 7, 'ch1') are still rejected: benchmark
    # state must use the canonical serialized form chNNNNN exactly.
    novel = make_novel(contexts={
        "characters.yaml": ("characters:\n"
                            "  a:\n    english: A\n    first_seen: 7\n"
                            "  b:\n    english: B\n    first_seen: ch1\n")})
    strict = validate.validate_novel(novel, require_first_seen=True)
    flagged = [i for i in strict if "first_seen" in i.message and i.severity == "error"]
    assert len(flagged) == 2


def test_require_first_seen_accepts_tagged_records(make_novel):
    novel = make_novel(
        contexts={"characters.yaml":
                  "characters:\n  a:\n    english: A\n    first_seen: ch00001\n"},
        phrases=['{"source": "x", "gloss": "y", "first_seen": "ch00002"}'],
    )
    strict = validate.validate_novel(novel, require_first_seen=True)
    assert not any("first_seen" in i.message for i in strict)


def test_nonconforming_chapter_filename_is_a_warning(make_novel, novels_dir):
    novel = make_novel(sources={1: "内容"})
    # Drop a mis-named chapter-ish file into source/.
    (novels_dir / novel / "source" / "chapter_one.txt").write_text("x", encoding="utf-8")
    warns = _messages(validate.validate_novel(novel), "warning")
    assert any("convention" in w.message for w in warns)

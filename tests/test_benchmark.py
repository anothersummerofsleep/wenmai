"""Benchmark harness: A/B/C conditions, blinding, deterministic eval, and unblinded analysis.

Uses an invented local corpus in a temp dir (never Lord of Mysteries, no network).
"""
import yaml
import pytest

from scripts import benchmark, backends, context


VALID_MD = "---\ntitle: x\n---\n\n# Chapter\n\nHis qi flowed steadily.\n"


class Recorder:
    """Fake backend: records every call, returns valid, drift-clean markdown."""
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system, user, *, tag):
        self.calls.append({"tag": tag, "system": system, "user": user})
        return VALID_MD


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """An invented benchmark corpus with a state novel; patches benchmark.local_root."""
    bid = "demo"
    root = tmp_path / "bench" / bid
    monkeypatch.setattr(benchmark, "local_root", lambda b: (tmp_path / "bench" / b))
    # generate() mutates context.NOVELS_DIR; patch it so pytest restores it afterwards.
    monkeypatch.setattr(context, "NOVELS_DIR", root)

    state = root / "state"
    (state / "source").mkdir(parents=True)
    (state / "context").mkdir(parents=True)
    (state / "translation_memory").mkdir(parents=True)
    (state / "novel.yaml").write_text(
        "source_language: zh\ntarget_language: en\ntitle_english: Demo\n", encoding="utf-8")
    (state / "style_guide.md").write_text("Voice: plain past tense.\n", encoding="utf-8")
    (state / "source" / "ch0001_zh.txt").write_text("第一章 内容", encoding="utf-8")
    (state / "source" / "ch0002_zh.txt").write_text("第二章 内容", encoding="utf-8")
    (state / "context" / "terminology.yaml").write_text(
        "terms:\n  qi:\n    source: 气\n    preferred: qi\n    avoid:\n      - chi\n", encoding="utf-8")
    (state / "translation_memory" / "phrases.jsonl").write_text(
        '{"source": "老狐狸", "gloss": "old fox"}\n', encoding="utf-8")
    return bid


def test_check_local_flags_missing_source(bench):
    problems = benchmark.check_local(bench, [1, 2, 3])
    assert any("chapter 3" in p for p in problems)  # only ch1,ch2 supplied
    assert not any("chapter 1" in p for p in problems)


def test_generate_creates_blinded_candidates(bench):
    rec = Recorder()
    mapping = benchmark.generate_chapter(bench, 1, rec, run_id="r1", seed="s")
    assert set(mapping.values()) == {"A", "B", "C"}  # all three conditions present
    assert sorted(mapping.keys()) == ["1", "2", "3"]  # neutral labels

    ch_dir = benchmark.local_root(bench) / "runs" / "r1" / "ch0001"
    for label in ("1", "2", "3"):
        assert (ch_dir / f"candidate_{label}.md").exists()
    assert (ch_dir / "deterministic.yaml").exists()
    assert (ch_dir / "eval_blank.yaml").exists()
    # Blinding is stored separately, out of the candidate view directory.
    assert (benchmark.local_root(bench) / "runs" / "r1" / "_blinding" / "ch0001.json").exists()
    assert not (ch_dir / "blinding.json").exists()


def test_conditions_include_the_right_context(bench):
    # Generate ch1 (writes C's output), then ch2 so a rolling window exists.
    rec = Recorder()
    benchmark.generate_chapter(bench, 1, rec, run_id="r1", seed="s")
    benchmark.generate_chapter(bench, 2, rec, run_id="r1", seed="s")

    def user_for(chapter, cond):
        tag = f"benchmark/{bench}/r1/ch{chapter:04d}/{cond}"
        return next(c["user"] for c in rec.calls if c["tag"] == tag)

    # Chapter 2 users:
    a2, b2, c2 = user_for(2, "A"), user_for(2, "B"), user_for(2, "C")
    # A: no previous, no canonical context, no translation memory.
    assert "Previous translated chapters" not in a2
    assert "Canonical context records" not in a2
    assert "Translation memory" not in a2
    # B: rolling window yes, structured context no.
    assert "Previous translated chapters" in b2
    assert "Canonical context records" not in b2
    # C: everything.
    assert "Previous translated chapters" in c2
    assert "Canonical context records" in c2
    assert "Translation memory" in c2
    # Shared window: C's chapter-1 output was written back and is visible to both B and C.
    assert (benchmark.local_root(bench) / "state" / "translated" / "ch0001_en.md").exists()


def test_deterministic_scores_detect_banned_variant(bench):
    benchmark._use_state_novel(bench)  # point context at the state novel so avoid-lists load
    scores = benchmark.deterministic_scores("---\n---\n# C\n\nThe chi surged.")
    assert scores["banned_variant_count"] == 1
    assert scores["banned_variants"][0]["preferred"] == "qi"
    clean = benchmark.deterministic_scores(VALID_MD)
    assert clean["banned_variant_count"] == 0
    assert clean["formatting_valid"] is True


def test_analyze_unblinds_and_aggregates(bench):
    rec = Recorder()
    mapping = benchmark.generate_chapter(bench, 1, rec, run_id="r1", seed="s")  # label -> condition

    # Write a filled human eval so each condition gets a known, distinct score.
    by_condition = {"A": 1, "B": 3, "C": 5}
    candidates = {}
    for label, cond in mapping.items():
        entry = {dim: by_condition[cond] for dim in benchmark.EVAL_DIMENSIONS}
        entry["comments"] = ""
        candidates[label] = entry
    ch_dir = benchmark.local_root(bench) / "runs" / "r1" / "ch0001"
    (ch_dir / "eval_filled.yaml").write_text(
        yaml.safe_dump({"candidates": candidates}, allow_unicode=True), encoding="utf-8")

    agg = benchmark.analyze_run(bench, "r1")
    assert agg["chapters_with_human_scores"] == 1
    assert agg["conditions"]["A"]["human"]["faithfulness"] == 1
    assert agg["conditions"]["B"]["human"]["faithfulness"] == 3
    assert agg["conditions"]["C"]["human"]["faithfulness"] == 5
    # Deterministic aggregate present too.
    assert agg["conditions"]["C"]["deterministic"]["formatting_valid_rate"] == 1.0


def test_generate_errors_when_corpus_missing(bench, monkeypatch):
    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: Recorder())
    with pytest.raises(FileNotFoundError):
        benchmark.generate(bench, [1, 2, 3], None, run_id="r1", seed="s")  # ch3 missing

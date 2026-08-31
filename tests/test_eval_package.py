"""Portable blind-evaluation package (eval_package/): chapter-qualified, byte-identical, blind-safe.

The authoritative run artifacts keep their generic, chapter-scoped basenames; this derived package
gives an evaluator collision-proof filenames plus a checksum manifest, and must never leak the
condition mapping or any non-evaluator artifact. Invented corpus in a temp dir, no network.
"""
import json

import pytest

from scripts import benchmark, backends, context


VALID_MD = "---\ntitle: x\n---\n\n# Chapter\n\nHis qi flowed steadily.\n"

PACKAGE_BASENAMES = {
    "candidate_1.md", "candidate_2.md", "candidate_3.md",
    "deterministic.yaml", "eval_blank.yaml",
}


class Recorder:
    """Fake backend: valid, drift-clean markdown; records calls so we can assert none happen."""
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system, user, *, tag):
        self.calls.append(tag)
        return VALID_MD


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """An invented benchmark corpus with a state novel; patches benchmark.local_root."""
    bid = "demo"
    root = tmp_path / "bench" / bid
    monkeypatch.setattr(benchmark, "local_root", lambda b: (tmp_path / "bench" / b))
    monkeypatch.setattr(benchmark, "load_manifest",
                        lambda b: {"language_pair": {"source": "zh", "target": "en"}, "chapters": 10})
    monkeypatch.setattr(context, "NOVELS_DIR", root)

    state = root / "state"
    (state / "source").mkdir(parents=True)
    (state / "context").mkdir(parents=True)
    (state / "translation_memory").mkdir(parents=True)
    (state / "novel.yaml").write_text(
        "source_language: zh\ntarget_language: en\ntitle_english: Demo\n", encoding="utf-8")
    (state / "style_guide.md").write_text("Voice: plain past tense.\n", encoding="utf-8")
    (state / "source" / "ch00001_zh.txt").write_text("第一章 内容", encoding="utf-8")
    (state / "source" / "ch00002_zh.txt").write_text("第二章 内容", encoding="utf-8")
    (state / "context" / "terminology.yaml").write_text(
        "terms:\n  qi:\n    source: 气\n    preferred: qi\n    avoid:\n      - chi\n", encoding="utf-8")
    (state / "translation_memory" / "phrases.jsonl").write_text(
        '{"source": "老狐狸", "gloss": "old fox"}\n', encoding="utf-8")
    return bid


def _pkg_dir(bench, chapter, run="r1"):
    return benchmark.local_root(bench) / "runs" / run / context.chapter_id(chapter) / "eval_package"


def _ch_dir(bench, chapter, run="r1"):
    return benchmark.local_root(bench) / "runs" / run / context.chapter_id(chapter)


def test_generate_auto_creates_package_with_chapter_qualified_names(bench):
    # Proof 1 (chapter-qualified names) and 12 (generate auto-creates the package).
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    pkg = _pkg_dir(bench, 1)
    assert pkg.is_dir()
    expected = {f"ch00001_{n}" for n in (
        "zh.txt", "candidate_1.md", "candidate_2.md", "candidate_3.md",
        "deterministic.yaml", "eval_blank.yaml", "eval_manifest.json")}
    assert {p.name for p in pkg.iterdir()} == expected
    # Every basename carries the chapter number; none is a bare generic name.
    assert all(name.startswith("ch00001_") for name in expected)
    assert not (PACKAGE_BASENAMES & {p.name for p in pkg.iterdir()})


def test_chapter1_and_chapter2_basenames_cannot_collide(bench):
    # Proof 2: different chapters produce disjoint basenames, safe to co-locate after upload.
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    benchmark.generate_chapter(bench, 2, Recorder(), run_id="r1", seed="s")
    names1 = {p.name for p in _pkg_dir(bench, 1).iterdir()}
    names2 = {p.name for p in _pkg_dir(bench, 2).iterdir()}
    assert names1.isdisjoint(names2)


def test_exported_files_are_byte_identical_to_authoritative_sources(bench):
    # Proofs 3, 4, 5: source, candidates, deterministic and eval_blank copied byte-for-byte.
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    pkg, ch = _pkg_dir(bench, 1), _ch_dir(bench, 1)
    src = benchmark.local_root(bench) / "state" / "source" / "ch00001_zh.txt"
    assert (pkg / "ch00001_zh.txt").read_bytes() == src.read_bytes()
    for label in ("1", "2", "3"):
        assert (pkg / f"ch00001_candidate_{label}.md").read_bytes() == \
               (ch / f"candidate_{label}.md").read_bytes()
    assert (pkg / "ch00001_deterministic.yaml").read_bytes() == (ch / "deterministic.yaml").read_bytes()
    assert (pkg / "ch00001_eval_blank.yaml").read_bytes() == (ch / "eval_blank.yaml").read_bytes()


def test_manifest_sha256_matches_exported_bytes(bench):
    # Proof 6: every manifest checksum matches the exported file's bytes.
    import hashlib
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    pkg = _pkg_dir(bench, 1)
    manifest = json.loads((pkg / "ch00001_eval_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {
        "ch00001_zh.txt", "ch00001_candidate_1.md", "ch00001_candidate_2.md",
        "ch00001_candidate_3.md", "ch00001_deterministic.yaml", "ch00001_eval_blank.yaml"}
    for name, meta in manifest["files"].items():
        assert meta["sha256"] == hashlib.sha256((pkg / name).read_bytes()).hexdigest()


def test_manifest_carries_no_condition_mapping(bench):
    # Proof 7: manifest is blind-safe — no candidate->condition mapping or blinding language.
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    text = (_pkg_dir(bench, 1) / "ch00001_eval_manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert set(manifest) == {"benchmark", "run", "chapter", "source_language",
                             "target_language", "files"}
    lowered = text.lower()
    for banned in ("condition", "blinding", "_blinding", "mapping", "history", "reference"):
        assert banned not in lowered
    # No manifest value is a bare condition label (A/B/C).
    def leaves(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                yield from leaves(v)
        else:
            yield obj
    assert not any(v in ("A", "B", "C") for v in leaves(manifest))


def test_package_excludes_blinding_filled_and_other_artifacts(bench):
    # Proofs 8, 9, 10: _blinding, eval_filled.yaml, and any history/reference/state/proposal file
    # are never copied into the package (allowlist copy: only the six content files + manifest).
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    ch = _ch_dir(bench, 1)
    # Simulate scored + stray artifacts sitting beside the candidates.
    (ch / "eval_filled.yaml").write_text("candidates: {}\n", encoding="utf-8")
    (ch / "analysis.yaml").write_text("x: 1\n", encoding="utf-8")
    benchmark.export_eval_package(bench, 1, "r1")  # re-export with the stray files present
    names = {p.name for p in _pkg_dir(bench, 1).iterdir()}
    assert "eval_filled.yaml" not in names and "ch00001_eval_filled.yaml" not in names
    assert "analysis.yaml" not in names
    assert not any("blinding" in n for n in names)
    assert not any(n.endswith(".json") and n != "ch00001_eval_manifest.json" for n in names)
    # The blinding map still lives only in its own directory, untouched.
    assert (benchmark.local_root(bench) / "runs" / "r1" / "_blinding" / "ch00001.json").exists()


def test_export_eval_recreates_package_without_model_calls(bench, monkeypatch):
    # Proof 11: export-eval works retroactively on an already-generated chapter and calls no model.
    benchmark.generate_chapter(bench, 1, Recorder(), run_id="r1", seed="s")
    import shutil as _sh
    _sh.rmtree(_pkg_dir(bench, 1))  # drop the auto-created package
    # Any attempt to obtain a backend (i.e. a model call path) must fail the test.
    monkeypatch.setattr(backends, "get_backend",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model calls")))
    pkg = benchmark.export_eval_package(bench, 1, "r1")
    assert pkg.is_dir()
    assert (pkg / "ch00001_candidate_1.md").exists()


def test_export_eval_fails_clearly_when_chapter_not_generated(bench):
    # export-eval must error (not silently succeed) if an authoritative artifact is missing.
    with pytest.raises(FileNotFoundError):
        benchmark.export_eval_package(bench, 1, "r1")  # nothing generated yet

"""End-to-end V1 path on the bundled sample-novel, with a fake backend (no real API call)."""
from scripts import translate, backends, context, consistency_check


FAKE_TRANSLATION = (
    "---\n"
    "chapter: 1\n"
    "title_english: The Old Fox\n"
    "---\n\n"
    "# Chapter 1: The Old Fox\n\n"
    "Senior Brother Zhang entered the hall. His qi was steady.\n"
)


def test_translate_pipeline_end_to_end(sample_novel_copy, monkeypatch):
    novel = sample_novel_copy

    # Start from a clean slate so we exercise generation, not the --skip path.
    out = context.translated_path(novel, 1)
    out.unlink()

    class FakeBackend:
        name = "fake"

        def complete(self, system, user, *, tag):
            # The real assembled prompt must carry the zh overlay and source text.
            assert "Source-language guidance (zh)" in system
            assert "老狐狸" in user  # source chapter reached the prompt
            return FAKE_TRANSLATION

    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: FakeBackend())

    rc = translate.run(novel, 1, None, force=True)
    assert rc == 0
    assert out.exists()
    assert "Chapter 1" in out.read_text(encoding="utf-8")

    # Pass 3 (consistency) should be clean on this neutral output.
    assert consistency_check.check_novel(novel, 1) == []

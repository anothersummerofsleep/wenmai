"""Context extraction receives the ORIGINAL source chapter and the finished translation."""
from scripts import build_context, backends


def test_extraction_prompt_includes_source_and_translation(make_novel, monkeypatch):
    captured = {}

    class FakeBackend:
        name = "fake"

        def complete(self, system, user, *, tag):
            captured["user"] = user
            captured["system"] = system
            return "characters: {}\n"

    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: FakeBackend())

    novel = make_novel(
        sources={1: "原文内容 ABC"},
        translations={1: "# Chapter 1\n\nHello there."},
        contexts={"characters.yaml": "characters: {}\n"},
    )
    rc = build_context.run(novel, 1, None)
    assert rc == 0

    user = captured["user"]
    assert "## Existing canonical context" in user
    assert "## Original source chapter" in user
    assert "原文内容 ABC" in user            # source recovered from source, not English
    assert "## Finished translation" in user
    assert "Hello there." in user

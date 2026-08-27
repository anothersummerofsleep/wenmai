"""Context extraction receives the ORIGINAL source chapter and the finished translation."""
import pytest

from scripts import build_context, backends


# --- proposal-only outer-fence normalization (never applied to translation candidates) ---------

def test_strip_single_outer_fence_yaml():
    text = "```yaml\ncharacters:\n  - source: X\n```"
    assert build_context.strip_single_outer_fence(text) == "characters:\n  - source: X"


def test_strip_single_outer_fence_yml_and_bare():
    assert build_context.strip_single_outer_fence("```yml\na: 1\n```") == "a: 1"
    assert build_context.strip_single_outer_fence("```\na: 1\n```") == "a: 1"


def test_strip_fence_tolerates_surrounding_whitespace():
    assert build_context.strip_single_outer_fence("\n\n```yaml\na: 1\n```\n\n") == "a: 1"


@pytest.mark.parametrize("text", [
    "a: 1\nb: 2",                              # plain YAML, no fence
    "```markdown\na: 1\n```",                  # markdown label: not stripped (candidate-style)
    "prefix\n```yaml\na: 1\n```",              # surrounding content before the block
    "```yaml\na: 1\n```\ntrailing",            # surrounding content after the block
    "```yaml\na: 1\n```\n```yaml\nb: 2\n```",  # two blocks: not a single outer fence
])
def test_strip_fence_leaves_non_single_fenced_unchanged(text):
    assert build_context.strip_single_outer_fence(text) == text


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

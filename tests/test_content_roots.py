"""External content-root resolution, identifier/tag safety, collision policy, safe display,
the runtime-artifact isolation guard, and the benchmark scoped override.

Everything here uses invented, generic workspaces in temp dirs (no real content, no network).
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path, PureWindowsPath

import pytest

from scripts import backends, config, context


def _workspace(root: Path, name: str) -> Path:
    """Create a minimal workspace directory `name` under `root` and return it."""
    d = root / name
    (d / "source").mkdir(parents=True)
    return d


@pytest.fixture
def clean_env(monkeypatch):
    """Control precedence explicitly: no ambient env var, no ambient config.yaml."""
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    monkeypatch.setattr(config, "load_config", lambda: {})


# --------------------------------------------------------------------------- precedence

def test_default_root_used_when_nothing_configured(tmp_path, monkeypatch, clean_env):
    novels = tmp_path / "novels"
    _workspace(novels, "demo")
    monkeypatch.setattr(context, "NOVELS_DIR", novels)
    assert context.novel_dir("demo") == novels / "demo"


def test_config_roots_used_over_default(tmp_path, monkeypatch):
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    external = tmp_path / "external"
    _workspace(external, "demo")
    monkeypatch.setattr(context, "NOVELS_DIR", tmp_path / "novels")
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": [str(external)]})
    assert context.novel_dir("demo") == external / "demo"


def test_env_overrides_config_and_default(tmp_path, monkeypatch):
    cfg_root = tmp_path / "cfg"
    env_root = tmp_path / "env"
    _workspace(cfg_root, "demo")
    _workspace(env_root, "demo")
    monkeypatch.setattr(context, "NOVELS_DIR", tmp_path / "novels")
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": [str(cfg_root)]})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, str(env_root))
    assert context.novel_dir("demo") == env_root / "demo"


def test_empty_env_var_is_treated_as_unset(tmp_path, monkeypatch):
    external = tmp_path / "external"
    _workspace(external, "demo")
    monkeypatch.setattr(context, "NOVELS_DIR", tmp_path / "novels")
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": [str(external)]})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, "   ")  # whitespace only -> unset
    assert context.novel_dir("demo") == external / "demo"


def test_relative_config_root_anchored_to_repo_root(monkeypatch):
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": ["some/rel"]})
    roots = config.resolve_content_roots([config.REPO_ROOT / "novels"])
    assert roots == [config.REPO_ROOT / "some" / "rel"]


def test_env_list_splits_on_os_pathsep(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, f"{a}{os.pathsep}{b}")
    assert config.resolve_content_roots([tmp_path / "novels"]) == [a, b]


def test_windows_drive_path_is_lexically_absolute():
    # Host-agnostic lexical check (WM-10): a drive-letter path is absolute on Windows, so it
    # would never be re-anchored under the repo root there.
    assert PureWindowsPath(r"C:\workspaces\demo").is_absolute()


def test_roots_are_deduplicated_preserving_order(tmp_path, monkeypatch):
    a = tmp_path / "a"
    a.mkdir()
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, f"{a}{os.pathsep}{a}")
    assert config.resolve_content_roots([tmp_path / "novels"]) == [a]


# --------------------------------------------------------------------------- malformed config

def test_malformed_config_values_raise_config_error(monkeypatch):
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    for bad in ({"content_roots": "notalist"}, {"content_roots": []}, {"content_roots": [""]}):
        monkeypatch.setattr(config, "load_config", lambda b=bad: b)
        with pytest.raises(config.ConfigError):
            config.resolve_content_roots([config.REPO_ROOT / "novels"])


def test_env_with_only_separators_raises(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, os.pathsep + os.pathsep)
    with pytest.raises(config.ConfigError):
        config.resolve_content_roots([config.REPO_ROOT / "novels"])


def test_invalid_conflict_policy_raises(monkeypatch):
    with pytest.raises(config.ConfigError):
        config.conflict_policy({config.CONFLICT_KEY: "nonsense"})


# --------------------------------------------------------------------------- identifier safety

@pytest.mark.parametrize("bad", ["", "   ", ".", "..", "a/b", "a\\b", "/abs", "../x", "a/../b"])
def test_identifier_rejects_unsafe_values(bad):
    with pytest.raises(ValueError):
        config.validate_segment(bad, kind="workspace identifier")


def test_novel_dir_rejects_traversal_identifier(tmp_path, monkeypatch, clean_env):
    monkeypatch.setattr(context, "NOVELS_DIR", tmp_path / "novels")
    with pytest.raises(ValueError):
        context.novel_dir("../secret")


def test_symlinked_escape_is_not_resolved(tmp_path, monkeypatch, clean_env):
    root = tmp_path / "novels"
    root.mkdir()
    outside = tmp_path / "outside"
    (outside / "source").mkdir(parents=True)
    try:
        (root / "demo").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    monkeypatch.setattr(context, "NOVELS_DIR", root)
    with pytest.raises(FileNotFoundError):
        context.novel_dir("demo")  # resolves outside its root -> rejected


# --------------------------------------------------------------------------- collisions

def test_collision_errors_with_root_labels_not_absolute_paths(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    _workspace(a, "demo")
    _workspace(b, "demo")
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, f"{a}{os.pathsep}{b}")
    with pytest.raises(ValueError) as exc:
        context.novel_dir("demo")
    msg = str(exc.value)
    assert "content_roots[0]" in msg and "content_roots[1]" in msg
    assert str(a) not in msg and str(b) not in msg  # no absolute paths leaked


def test_collision_first_policy_uses_first_and_warns(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    _workspace(a, "demo")
    _workspace(b, "demo")
    monkeypatch.setattr(config, "load_config",
                        lambda: {config.CONFLICT_KEY: "first"})
    monkeypatch.setenv(config.CONTENT_ROOTS_ENV, f"{a}{os.pathsep}{b}")
    with pytest.warns(config.ContentRootWarning):
        assert context.novel_dir("demo") == a / "demo"


def test_not_found_lists_searched_roots(tmp_path, monkeypatch, clean_env):
    monkeypatch.setattr(context, "NOVELS_DIR", tmp_path / "novels")
    (tmp_path / "novels").mkdir()
    with pytest.raises(FileNotFoundError) as exc:
        context.novel_dir("missing")
    assert "content_roots[0]" in str(exc.value)


# --------------------------------------------------------------------------- safe display

def test_safe_display_shows_in_root_portion_only(tmp_path):
    root = tmp_path / "ext"
    target = root / "demo" / "source"
    assert config.safe_display(target, [root]) == str(Path("demo") / "source")


def test_safe_display_unknown_path_uses_marker(tmp_path):
    secret = tmp_path / "very-secret-name"
    shown = config.safe_display(secret, [tmp_path / "novels"])
    assert shown == "<external-path>"
    assert "very-secret-name" not in shown


# --------------------------------------------------------------------------- tag containment

def test_safe_join_accepts_nested_tag(tmp_path):
    base = tmp_path / "runs"
    assert config.safe_join(base, "novel/ch00001/translate") == base / "novel" / "ch00001" / "translate"


@pytest.mark.parametrize("bad", ["../escape", "/abs/tag", "a/../../b", "a\\b", "C:/x"])
def test_safe_join_rejects_escape(tmp_path, bad):
    with pytest.raises(ValueError):
        config.safe_join(tmp_path / "runs", bad)


def test_handoff_tag_cannot_escape_runs_dir(tmp_path):
    backend = backends.ClaudeCodeBackend(runs_dir=str(tmp_path / "runs"))
    with pytest.raises(ValueError):
        backend.complete("SYS", "USER", tag="../escape")
    assert not (tmp_path / "escape.prompt.md").exists()


# --------------------------------------------------------------------------- isolation guard

def test_guard_warns_external_root_with_in_repo_runs_dir(tmp_path):
    with pytest.warns(config.ContentRootWarning):
        config.warn_if_artifacts_leak_into_repo([tmp_path / "external"], config.REPO_ROOT / ".runs")


def test_guard_silent_when_runs_dir_external(tmp_path, recwarn):
    config.warn_if_artifacts_leak_into_repo([tmp_path / "external"], tmp_path / "runs")
    assert not any(isinstance(w.message, config.ContentRootWarning) for w in recwarn.list)


def test_guard_silent_when_no_runs_dir(recwarn):
    config.warn_if_artifacts_leak_into_repo([config.REPO_ROOT / "novels"], None)
    assert not any(isinstance(w.message, config.ContentRootWarning) for w in recwarn.list)


# --------------------------------------------------------------------------- backend wiring

def test_get_backend_uses_absolute_configured_runs_dir(tmp_path):
    out = tmp_path / "out"
    backend = backends.get_backend("claude_code", {"claude_code": {"runs_dir": str(out)}})
    with pytest.raises(backends.PendingHandoff) as exc:
        backend.complete("SYS", "USER", tag="demo/ch00001/translate")
    assert (out / "demo" / "ch00001" / "translate.prompt.md").exists()
    assert str(out) not in str(exc.value)  # handoff message is redacted, no absolute path


def test_backends_load_config_is_shared_alias(monkeypatch):
    monkeypatch.undo()  # drop the conftest isolation wrapper so the real function is compared
    assert backends.load_config is config.load_config


# --------------------------------------------------------------------------- scoped override

def test_use_content_root_scoped_and_restored(tmp_path):
    before = context.content_roots()
    with context.use_content_root(tmp_path / "bench"):
        assert context.content_roots() == [tmp_path / "bench"]
        with context.use_content_root(tmp_path / "inner"):
            assert context.content_roots() == [tmp_path / "inner"]
        assert context.content_roots() == [tmp_path / "bench"]
    assert context.content_roots() == before


def test_override_outranks_configured_roots(tmp_path, monkeypatch):
    configured = tmp_path / "configured"
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": [str(configured)]})
    monkeypatch.delenv(config.CONTENT_ROOTS_ENV, raising=False)
    bench = tmp_path / "bench"
    with context.use_content_root(bench):
        assert context.content_roots() == [bench]
    assert context.content_roots() == [configured]


def test_override_restored_on_exception(tmp_path):
    before = context.content_roots()
    with pytest.raises(RuntimeError):
        with context.use_content_root(tmp_path / "bench"):
            raise RuntimeError("boom")
    assert context.content_roots() == before


# --------------------------------------------------------------------------- ambient isolation (tests)

def test_ambient_config_roots_do_not_redirect_legacy_fixtures(tmp_path, monkeypatch, make_novel,
                                                              novels_dir):
    # A local config.yaml that configures content_roots must not pull fixture-based tests away
    # from their temp root. Simulate one by pointing the real loader at a temp "repo".
    fake_repo = tmp_path / "repo"
    decoy = tmp_path / "decoy"
    _workspace(decoy, "novel")
    fake_repo.mkdir()
    (fake_repo / "config.yaml").write_text(
        f"content_roots:\n  - {decoy.as_posix()}\ncontent_roots_on_conflict: first\n"
        "retrieval:\n  previous_chapters: 3\n", encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", fake_repo)

    slug = make_novel()
    assert context.novel_dir(slug) == novels_dir / slug
    cfg = config.load_config()
    assert "content_roots" not in cfg and config.CONFLICT_KEY not in cfg
    assert cfg["retrieval"]["previous_chapters"] == 3  # only root-selection keys are dropped


def _tree_digest(root: Path) -> dict:
    import hashlib
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_ambient_env_root_does_not_redirect_legacy_suite(tmp_path):
    # End to end: run real legacy tests in a child pytest with WENMAI_CONTENT_ROOTS pointing at an
    # external root that holds a decoy copy of the sample workspace. Isolation means they pass and
    # neither the decoy nor the tracked sample is touched.
    import shutil
    import subprocess
    import sys

    sample = context.REPO_ROOT / "novels" / "sample-novel"
    external = tmp_path / "external"
    shutil.copytree(sample, external / "sample-novel")
    before_decoy, before_sample = _tree_digest(external), _tree_digest(sample)

    env = dict(os.environ, **{config.CONTENT_ROOTS_ENV: str(external)})
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_smoke.py", "tests/test_context_loading.py"],
        cwd=context.REPO_ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert _tree_digest(external) == before_decoy
    assert _tree_digest(sample) == before_sample


# --------------------------------------------------------------------------- error redaction

def _external_workspace(tmp_path, monkeypatch, name="demo"):
    root = tmp_path / "private-external-root"
    ws = _workspace(root, name)
    (ws / "context").mkdir()
    (ws / "novel.yaml").write_text("source_language: zh\ntarget_language: en\n", encoding="utf-8")
    monkeypatch.setattr(config, "load_config", lambda: {"content_roots": [str(root)]})
    return root, ws


def test_missing_source_error_redacts_external_root(tmp_path, monkeypatch):
    root, _ = _external_workspace(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError) as exc:
        context.read_source("demo", 1)
    msg = str(exc.value)
    assert str(root) not in msg and "private-external-root" not in msg
    assert str(Path("demo") / "source" / "ch00001_zh.txt") in msg  # still diagnosable


def test_malformed_novel_yaml_error_redacts_path_and_content(tmp_path, monkeypatch):
    _, ws = _external_workspace(tmp_path, monkeypatch)
    (ws / "novel.yaml").write_text("source_language: zh\ntitle: [PRIVATE-MARKER\n", encoding="utf-8")
    with pytest.raises(context.ConfigError) as exc:
        context.load_novel_config("demo")
    msg = str(exc.value)
    assert "private-external-root" not in msg and "PRIVATE-MARKER" not in msg
    assert "novel.yaml" in msg and "line " in msg
    # The parser's own exception (which quotes the line and names the file) is not chained.
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_malformed_context_yaml_error_redacts_path_and_content(tmp_path, monkeypatch):
    _, ws = _external_workspace(tmp_path, monkeypatch)
    (ws / "context" / "glossary.yaml").write_text("terms: [PRIVATE-MARKER\n", encoding="utf-8")
    for load in (lambda: context.load_context_records("demo", max_chapter=2),
                 lambda: context.load_context_data("demo")):
        with pytest.raises(context.ConfigError) as exc:
            load()
        msg = str(exc.value)
        assert "private-external-root" not in msg and "PRIVATE-MARKER" not in msg
        assert "glossary.yaml" in msg


# --------------------------------------------------------------------------- guard ordering

class _RecordingBackend:
    """Reports a runs_dir (as the claude_code backend does) but persists nothing."""
    name = "fake"

    def __init__(self, runs_dir):
        self.runs_dir = runs_dir
        self.calls = []

    def complete(self, system, user, *, tag):
        self.calls.append(tag)
        return "characters: {}\n"


def _guarded_entrypoint(name, tmp_path, monkeypatch, runs_dir):
    """An external workspace with chapter 1 source + translation, and a recording backend."""
    from scripts import build_context, translate
    _, ws = _external_workspace(tmp_path, monkeypatch)
    (ws / "translated").mkdir()
    (ws / "source" / "ch00001_zh.txt").write_text("source text", encoding="utf-8")
    (ws / "translated" / "ch00001_en.md").write_text("# Chapter 1\n\nText.\n", encoding="utf-8")
    fake = _RecordingBackend(runs_dir)
    monkeypatch.setattr(backends, "get_backend", lambda *a, **k: fake)
    run = {"translate": lambda: translate.run("demo", 1, None, force=True),
           "build_context": lambda: build_context.run("demo", 1, None)}[name]
    return run, fake


@pytest.mark.parametrize("entrypoint", ["translate", "build_context"])
def test_guard_warns_before_any_prompt_is_handed_off(tmp_path, monkeypatch, entrypoint):
    run, fake = _guarded_entrypoint(entrypoint, tmp_path, monkeypatch, config.REPO_ROOT / ".runs")
    with warnings.catch_warnings():
        warnings.simplefilter("error", config.ContentRootWarning)
        with pytest.raises(config.ContentRootWarning):
            run()
    assert fake.calls == []  # raised before the backend received (and could persist) a prompt


@pytest.mark.parametrize("entrypoint", ["translate", "build_context"])
def test_guard_silent_with_external_runs_dir(tmp_path, monkeypatch, recwarn, entrypoint):
    run, fake = _guarded_entrypoint(entrypoint, tmp_path, monkeypatch, tmp_path / "runs")
    run()
    assert fake.calls
    assert not any(isinstance(w.message, config.ContentRootWarning) for w in recwarn.list)


# --------------------------------------------------------------------------- Windows aliasing

@pytest.mark.parametrize("bad", ["demo.", "demo ", "...", "demo. ", " . "])
def test_identifier_rejects_trailing_dot_or_space(bad):
    with pytest.raises(ValueError):
        config.validate_segment(bad, kind="workspace identifier")


@pytest.mark.parametrize("ok", ["demo", ".hidden", "v1.2-demo", "a b"])
def test_identifier_accepts_ordinary_names(ok):
    assert config.validate_segment(ok) == ok


def test_safe_join_rejects_trailing_dot_segment(tmp_path):
    with pytest.raises(ValueError):
        config.safe_join(tmp_path / "runs", "demo./ch00001/translate")


# --------------------------------------------------------------------------- junction containment
# Directory junctions need no administrator or Developer Mode privilege, so unlike the symlink
# test above these always run on Windows.

windows_only = pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")


def _make_junction(link: Path, target: Path) -> None:
    import _winapi
    _winapi.CreateJunction(str(target), str(link))


@windows_only
def test_junction_escape_is_not_resolved_as_workspace(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    root.mkdir()
    outside = tmp_path / "outside"
    (outside / "source").mkdir(parents=True)
    _make_junction(root / "demo", outside)
    assert (root / "demo" / "source").is_dir()  # the junction itself is live
    monkeypatch.setattr(context, "NOVELS_DIR", root)
    with pytest.raises(FileNotFoundError):
        context.novel_dir("demo")


@windows_only
def test_junction_inside_root_is_allowed(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    real = _workspace(root, "real")
    _make_junction(root / "alias", real)
    monkeypatch.setattr(context, "NOVELS_DIR", root)
    assert context.novel_dir("alias") == root / "alias"


@windows_only
def test_junction_escape_blocked_for_handoff_tag(tmp_path):
    runs, outside = tmp_path / "runs", tmp_path / "outside"
    runs.mkdir()
    outside.mkdir()
    _make_junction(runs / "demo", outside)
    backend = backends.ClaudeCodeBackend(runs_dir=str(runs))
    with pytest.raises(ValueError):
        backend.complete("SYS", "USER", tag="demo/ch00001/translate")
    assert list(outside.iterdir()) == []  # nothing written through the junction

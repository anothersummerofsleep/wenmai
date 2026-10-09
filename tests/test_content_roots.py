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


def test_backends_load_config_is_shared_alias():
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

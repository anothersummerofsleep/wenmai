"""Shared configuration loading, content-root resolution, and safe path display.

This is the lowest layer: it imports only the standard library and PyYAML, and imports
*nothing* from the rest of the package, so any module can import it without a cycle.

Two concerns live here because both the content layer (context.py) and the transport layer
(backends.py) need them and neither should depend on the other:

- Loading config.yaml (the single source of truth for runtime config).
- Resolving which directories a workspace may live in (`resolve_content_roots`), so content
  can live in an independently managed directory outside the repo without changing defaults.
- Rendering a path for a user-facing message without exposing an external absolute location
  (`safe_display`), plus the small validation/containment helpers that keep identifiers and
  handoff tags from escaping their root.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path, PurePath

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

CONTENT_ROOTS_ENV = "WENMAI_CONTENT_ROOTS"
CONFLICT_KEY = "content_roots_on_conflict"
CONFLICT_MODES = ("error", "first")


class ConfigError(ValueError):
    """config.yaml or the environment holds a malformed value."""


class ContentRootWarning(UserWarning):
    """A non-fatal content-root condition worth surfacing (shadowed workspace, artifact leak)."""


# --------------------------------------------------------------------------- config.yaml

def load_config() -> dict:
    """Load config.yaml if present, else config.example.yaml defaults, else {}.

    The top level must be a mapping; anything else is a configuration error rather than a
    surprise far downstream.
    """
    for name in ("config.yaml", "config.example.yaml"):
        path = REPO_ROOT / name
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigError(f"{name}: top-level configuration must be a mapping")
            return data
    return {}


def conflict_policy(config: dict | None = None) -> str:
    """How to treat a workspace identifier found under more than one root: 'error' (default)
    fails loud; 'first' uses the first root and warns."""
    cfg = load_config() if config is None else config
    value = cfg.get(CONFLICT_KEY, "error")
    if value not in CONFLICT_MODES:
        raise ConfigError(
            f"'{CONFLICT_KEY}' must be one of {CONFLICT_MODES}, got {value!r}")
    return value


# --------------------------------------------------------------------------- content roots

def _env_roots() -> list[str] | None:
    """Parse WENMAI_CONTENT_ROOTS. An unset or whitespace-only value means 'not configured'
    (None); a value that is present but yields no usable path is an error."""
    raw = os.environ.get(CONTENT_ROOTS_ENV)
    if raw is None or not raw.strip():
        return None
    entries = [part.strip() for part in raw.split(os.pathsep) if part.strip()]
    if not entries:
        raise ConfigError(
            f"{CONTENT_ROOTS_ENV} is set but contains no usable paths (only separators)")
    return entries


def _config_roots(config: dict) -> list[str] | None:
    if "content_roots" not in config:
        return None
    value = config["content_roots"]
    if not isinstance(value, list) or not value:
        raise ConfigError("config 'content_roots' must be a non-empty list of path strings")
    return value


def resolve_content_roots(default_roots) -> list[Path]:
    """The directories to search for a workspace, in priority order.

    Precedence: WENMAI_CONTENT_ROOTS env, then config.yaml 'content_roots', then
    `default_roots` (normally the bundled ./novels). Relative entries resolve against
    REPO_ROOT (stable, independent of the current working directory). Entries are
    de-duplicated by resolved path, order preserved.
    """
    raw = _env_roots()
    source = "WENMAI_CONTENT_ROOTS"
    if raw is None:
        raw = _config_roots(load_config())
        source = "config 'content_roots'"

    if raw is None:
        roots = [Path(r) for r in default_roots]
    else:
        roots = []
        for entry in raw:
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigError(f"{source}: every entry must be a non-empty path string")
            p = Path(entry.strip())
            roots.append(p if p.is_absolute() else (REPO_ROOT / p))

    seen: set[str] = set()
    unique: list[Path] = []
    for r in roots:
        key = _norm_key(r)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def warn_if_artifacts_leak_into_repo(roots, runs_dir) -> None:
    """Warn when content comes from an external root but handoff artifacts would be written
    inside the repository checkout. Call this BEFORE any prompt/artifact is written.

    `runs_dir` is the repo-writing backend's output directory, or None for backends that do
    not persist prompts to disk (the API and the stateless CLI backend).
    """
    if runs_dir is None:
        return
    if not is_within(runs_dir, REPO_ROOT):
        return  # artifacts already isolated outside the repo
    external = [i for i, r in enumerate(roots) if not is_within(r, REPO_ROOT)]
    if external:
        labels = ", ".join(f"content_roots[{i}]" for i in external)
        warnings.warn(
            f"content is being read from an external workspace root ({labels}), but handoff "
            "prompts will be written inside the repository checkout. Set claude_code.runs_dir "
            "to a path outside the repository to keep external content out of the checkout.",
            ContentRootWarning, stacklevel=2)


# --------------------------------------------------------------------------- path safety

def _norm_key(path) -> str:
    key = str(_safe_resolve(Path(path)))
    return key.lower() if os.name == "nt" else key


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path.absolute() if not path.is_absolute() else path


def is_within(path, base) -> bool:
    """True if `path` is `base` or lives under it, compared on resolved absolute forms."""
    try:
        _safe_resolve(Path(path)).relative_to(_safe_resolve(Path(base)))
        return True
    except ValueError:
        return False


def validate_segment(name: str, *, kind: str = "identifier") -> str:
    """Return `name` if it is a single, safe path segment, else raise ValueError.

    Rejects empty values, path separators, drive letters, absolute paths, and parent
    references, so an identifier can never escape the root it is joined to.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{kind} must be a non-empty string")
    p = PurePath(name)
    bad_sep = "/" in name or "\\" in name or ":" in name
    if os.sep in name or (os.altsep and os.altsep in name):
        bad_sep = True
    if bad_sep or p.is_absolute() or p.drive or name in (".", "..") or ".." in p.parts:
        raise ValueError(
            f"invalid {kind} {name!r}: must be a single path segment with no separators, "
            "drive, or parent references")
    return name


def safe_join(base, tag: str) -> Path:
    """Join a '/'-separated handoff `tag` onto `base`, validating each segment and asserting
    the result stays within `base`. Tags legitimately contain '/', so segments are checked
    individually rather than rejecting the whole tag."""
    base = Path(base)
    if not isinstance(tag, str) or not tag.strip():
        raise ValueError("handoff tag must be a non-empty string")
    if "\\" in tag or ":" in tag:
        raise ValueError(f"unsafe handoff tag {tag!r}: contains a drive or backslash separator")
    segments = [seg for seg in tag.split("/")]
    for seg in segments:
        if seg in ("", ".", ".."):
            raise ValueError(f"unsafe segment in handoff tag {tag!r}")
    target = base.joinpath(*segments)
    if not is_within(target, base):
        raise ValueError(f"handoff tag {tag!r} escapes its output root")
    return target


def safe_display(path, bases) -> str:
    """Render `path` relative to the first matching base, else a non-identifying marker.

    Never returns an absolute external path, and never falls back to a bare basename (which
    could itself be a sensitive workspace name). A path under a known root shows only its
    in-root portion; a path under none shows '<external-path>'.
    """
    p = Path(path)
    bases = list(bases)
    for base in bases:
        try:
            return str(p.relative_to(base))
        except (ValueError, TypeError):
            continue
    rp = _safe_resolve(p)
    for base in bases:
        try:
            return str(rp.relative_to(_safe_resolve(Path(base))))
        except (ValueError, TypeError):
            continue
    return "<external-path>"

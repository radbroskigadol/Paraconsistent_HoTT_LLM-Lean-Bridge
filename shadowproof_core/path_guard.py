from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class PathPolicyError(ValueError):
    """Raised when a caller-supplied path escapes configured safe roots."""


def allowed_roots() -> list[Path]:
    raw = os.environ.get("SHADOWPROOF_ALLOWED_FILE_ROOTS", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        parts = [os.getcwd()]
    roots: list[Path] = []
    for p in parts:
        roots.append(Path(p).expanduser().resolve())
    return roots


def _as_path(value: str | os.PathLike[str] | None, default: str | os.PathLike[str] | None = None) -> Path:
    chosen = default if value is None else value
    if chosen is None:
        raise PathPolicyError("missing path")
    text = str(chosen)
    if not text.strip():
        raise PathPolicyError("blank path is not allowed")
    return Path(text).expanduser()


def resolve_under_allowed_root(
    value: str | os.PathLike[str] | None,
    *,
    default: str | os.PathLike[str] | None = None,
    must_exist: bool = False,
    kind: str = "path",
) -> Path:
    """Resolve a caller-controlled path and require it to remain under a safe root.

    Relative paths are resolved against the current working directory.  Safe roots
    come from SHADOWPROOF_ALLOWED_FILE_ROOTS, comma-separated; by default only
    the process cwd is allowed.  This keeps CLI demos usable while preventing an
    HTTP/admin caller from using absolute paths such as /etc/passwd or /tmp/...
    when the service runs from its application/data root.
    """
    p = _as_path(value, default)
    resolved = (Path.cwd() / p).resolve() if not p.is_absolute() else p.resolve()
    roots = allowed_roots()
    if not any(_is_relative_to(resolved, root) for root in roots):
        allowed = ", ".join(str(r) for r in roots)
        raise PathPolicyError(f"{kind} {resolved} escapes allowed roots: {allowed}")
    if must_exist and not resolved.exists():
        raise PathPolicyError(f"{kind} does not exist: {resolved}")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

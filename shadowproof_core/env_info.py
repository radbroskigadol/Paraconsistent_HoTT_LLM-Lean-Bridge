from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class LeanEnvironmentInfo:
    lean_command: str
    lean_version: str | None = None
    lake_version: str | None = None
    lean_toolchain: str | None = None
    mathlib_revision: str | None = None
    project_manifest_hash: str | None = None
    lakefile_hash: str | None = None
    cwd: str | None = None
    available: bool = False
    diagnostics: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["diagnostics"] is None:
            d["diagnostics"] = []
        return d


def collect_env_info(lean_command: str | None = None, cwd: str | Path | None = None, timeout_seconds: int = 10) -> LeanEnvironmentInfo:
    lean_command = lean_command or os.environ.get("SHADOWPROOF_LEAN_CMD", "lake env lean")
    cwd_path = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    diagnostics: list[str] = []

    info = LeanEnvironmentInfo(
        lean_command=lean_command,
        cwd=str(cwd_path),
        diagnostics=diagnostics,
    )

    info.lean_version = run_version_command(shlex.split(lean_command) + ["--version"], cwd_path, timeout_seconds, diagnostics)
    info.lake_version = run_version_command(["lake", "--version"], cwd_path, timeout_seconds, diagnostics)

    toolchain = cwd_path / "lean-toolchain"
    if toolchain.exists():
        info.lean_toolchain = safe_read_text(toolchain).strip() or None

    manifest = cwd_path / "lake-manifest.json"
    if manifest.exists():
        info.project_manifest_hash = file_hash(manifest)
        info.mathlib_revision = extract_mathlib_revision(manifest)

    lakefile_toml = cwd_path / "lakefile.toml"
    lakefile_lean = cwd_path / "lakefile.lean"
    if lakefile_toml.exists():
        info.lakefile_hash = file_hash(lakefile_toml)
    elif lakefile_lean.exists():
        info.lakefile_hash = file_hash(lakefile_lean)

    info.available = bool(info.lean_version and "not found" not in info.lean_version.lower())
    return info


def run_version_command(cmd: list[str], cwd: Path, timeout_seconds: int, diagnostics: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as e:
        diagnostics.append(f"Could not run {' '.join(cmd)}: {e}")
        return None

    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        diagnostics.append(f"Version command failed ({' '.join(cmd)}): {text[:300]}")
    return text or None


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def extract_mathlib_revision(manifest_path: Path) -> str | None:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    packages = raw.get("packages", [])
    if isinstance(packages, dict):
        iterable = packages.values()
    elif isinstance(packages, list):
        iterable = packages
    else:
        iterable = []

    for pkg in iterable:
        if not isinstance(pkg, dict):
            continue
        name = str(pkg.get("name", "")).lower()
        url = str(pkg.get("url", "")).lower()
        if name == "mathlib" or "mathlib" in url:
            for key in ("rev", "revision", "commit", "gitRev", "inputRev"):
                if pkg.get(key):
                    return str(pkg[key])
    return None


def certificate_environment_payload(lean_command: str | None, cwd: str | Path | None, timeout_seconds: int = 10) -> dict[str, Any]:
    return collect_env_info(lean_command=lean_command, cwd=cwd, timeout_seconds=timeout_seconds).to_dict()

#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = [
    re.compile(r"dev-token:default", re.I),
    re.compile(r"postgresql://shadow:shadow@", re.I),
    re.compile(r"POSTGRES_PASSWORD:\s*shadow\b", re.I),
]
ALLOWLIST_PARTS = {
    "scripts/check_no_default_secrets.py",
    "tests/test_v25_6_release_artifact_clean.py",
    "PATCH_NOTES_V25_6.md",
}
SCAN_SUFFIXES = {".yml", ".yaml", ".toml", ".env", ".json", ".md", ".py", ".Dockerfile"}
SCAN_NAMES = {"Dockerfile", "docker-compose.yml", "api.Dockerfile", "lean-worker.Dockerfile"}
violations: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(ROOT).as_posix()
    if rel in ALLOWLIST_PARTS or ".git/" in rel or rel.startswith("shadowproof_core/artifacts/") or rel.startswith("build/") or rel.startswith("dist/"):
        continue
    if path.suffix not in SCAN_SUFFIXES and path.name not in SCAN_NAMES:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pat in BANNED:
        if pat.search(text):
            violations.append(f"{rel}: banned default secret pattern {pat.pattern!r}")
if violations:
    print("Default/development secret patterns found outside allowlisted test/docs paths:")
    for item in violations:
        print(" -", item)
    sys.exit(1)
print("No banned default-secret patterns found.")

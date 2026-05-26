#!/usr/bin/env python3
"""Deterministic local Lean stand-in for ShadowProof integration tests.

It accepts the same last-argument file shape used by ``lean``/``lake env lean``
and emits Lean-like stderr diagnostics for diagnostic-parser contract tests.
It is not a proof checker.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path


def theorem_name(code: str) -> str:
    m = re.search(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_']*)", code)
    return m.group(1) if m else "unknown_theorem"


def main() -> int:
    if len(sys.argv) < 2:
        print("mock_lean: missing input file", file=sys.stderr)
        return 2
    path = Path(sys.argv[-1])
    try:
        code = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"{path}:1:1: error: could not read file: {e}", file=sys.stderr)
        return 1

    if "SHADOWPROOF_MOCK_LEAN_TIMEOUT" in code:
        time.sleep(float(os.environ.get("SHADOWPROOF_MOCK_LEAN_TIMEOUT_SECONDS", "60")))
        return 124
    if "SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER" in code:
        print(f"{path}:3:10: error: unknown identifier 'missingLemma'", file=sys.stderr)
        return 1
    if "SHADOWPROOF_MOCK_LEAN_TYPE_MISMATCH" in code:
        print(f"{path}:3:10: error: type mismatch\n  rfl\nhas type\n  ?m = ?m\nbut is expected to have type\n  Nat.succ n = n", file=sys.stderr)
        return 1
    if "SHADOWPROOF_MOCK_LEAN_UNSOLVED_GOALS" in code:
        print(f"{path}:4:2: error: unsolved goals\ncase h\n⊢ True", file=sys.stderr)
        return 1
    if "SHADOWPROOF_MOCK_LEAN_MISSING_IMPORT" in code:
        print(f"{path}:1:8: error: unknown module prefix 'MissingModule'", file=sys.stderr)
        return 1

    name = theorem_name(code)
    print(f"{name} does not depend on any axioms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

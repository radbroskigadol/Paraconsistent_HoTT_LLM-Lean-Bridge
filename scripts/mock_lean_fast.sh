#!/usr/bin/env bash
# Deterministic fast Lean stand-in for synthetic validation metrics.
set -euo pipefail
if [[ "${1:-}" == "--version" ]]; then
  echo "Lean (mock) 4.0.0-synthetic"
  exit 0
fi
if [[ $# -lt 1 ]]; then
  echo "mock_lean_fast: missing input file" >&2
  exit 2
fi
path="${!#}"
if [[ ! -r "$path" ]]; then
  echo "$path:1:1: error: could not read file" >&2
  exit 1
fi
code="$(cat "$path")"
if grep -q "SHADOWPROOF_MOCK_LEAN_TIMEOUT" <<<"$code"; then
  sleep "${SHADOWPROOF_MOCK_LEAN_TIMEOUT_SECONDS:-60}"
  exit 124
fi
if grep -q "SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER" <<<"$code"; then
  echo "$path:3:10: error: unknown identifier 'missingLemma'" >&2
  exit 1
fi
if grep -q "SHADOWPROOF_MOCK_LEAN_TYPE_MISMATCH" <<<"$code"; then
  printf "%s:3:10: error: type mismatch\n  rfl\nhas type\n  ?m = ?m\nbut is expected to have type\n  Nat.succ n = n\n" "$path" >&2
  exit 1
fi
if grep -q "SHADOWPROOF_MOCK_LEAN_UNSOLVED_GOALS" <<<"$code"; then
  printf "%s:4:2: error: unsolved goals\ncase h\n⊢ True\n" "$path" >&2
  exit 1
fi
if grep -q "SHADOWPROOF_MOCK_LEAN_MISSING_IMPORT" <<<"$code"; then
  echo "$path:1:8: error: unknown module prefix 'MissingModule'" >&2
  exit 1
fi
name="$(grep -Eo '\b(theorem|lemma)[[:space:]]+[A-Za-z_][A-Za-z0-9_'"'"']*' "$path" | head -n 1 | awk '{print $2}')"
if [[ -z "${name:-}" ]]; then
  name="unknown_theorem"
fi
echo "$name does not depend on any axioms"
exit 0

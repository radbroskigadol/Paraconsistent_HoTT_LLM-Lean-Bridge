#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/artifacts/lean_transcripts}"
mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_DIR/demorgan_symmetry_${TS}.txt"
{
  echo "# ShadowProof Lean transcript"
  echo "timestamp_utc=$TS"
  echo "project=$ROOT/lean_project_template"
  echo
  cd "$ROOT/lean_project_template"
  echo "## lean --version"
  lean --version
  echo
  echo "## lake --version"
  lake --version
  echo
  echo "## lean-toolchain"
  cat lean-toolchain
  echo
  echo "## lake build"
  lake build
  echo
  echo "## sha256"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum ShadowProof.lean ShadowProof/DemorganSymmetry.lean lakefile.lean lake-manifest.json lean-toolchain
  else
    shasum -a 256 ShadowProof.lean ShadowProof/DemorganSymmetry.lean lakefile.lean lake-manifest.json lean-toolchain
  fi
} | tee "$OUT"
echo "transcript=$OUT"

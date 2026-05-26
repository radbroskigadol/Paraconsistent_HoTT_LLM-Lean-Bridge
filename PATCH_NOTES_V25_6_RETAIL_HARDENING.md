# Patch Notes — v25.6 Retail Hardening Addendum

This addendum records fixes applied during the retail-readiness audit of the v25.6 release artifact.

## Fixed

- Replaced regex-only Lean comment stripping in security preflight, theorem-lock fingerprint checks, and ShadowHoTT fingerprint obstruction checks with a delimiter-aware scanner.
  - Handles nested Lean block comments.
  - Preserves offsets and newlines.
  - Masks string/character literals so `/-` or `-/` inside strings cannot hide real `axiom`/`sorry` declarations.
- Replaced raw regex proof-body substitution in `repair.replace_body` with a delimiter-aware proof-body splitter.
  - Searches `:= by` and `#print axioms` anchors only outside comments and literals.
  - Returns `None` when no real proof anchor exists instead of rewriting accidental text.
- Added regression tests for string-delimiter hiding, nested comments, theorem-lock leakage, and fake proof anchors inside string literals/comments.

## Validation

- `python -m pytest tests/ -q` → `119 passed, 1 skipped`
- `python -m compileall -q shadowproof_core scripts tests` → pass
- `python scripts/ci_secret_scan.py` → pass
- `bash scripts/run_buyer_demo.sh` → pass
- `cd mcp && npm ci --ignore-scripts && npm run build` → pass; `npm audit` reports 0 vulnerabilities during install

## Claim boundary

This patch hardens the local release artifact. It still does not replace a third-party security review, a production no-network Lean worker, production-scale Lean build transcripts, or real customer eval corpora.

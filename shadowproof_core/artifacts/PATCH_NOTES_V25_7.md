# Patch Notes — v0.25.7 Parser-Safe Repair and Synthetic Validation Metrics

## Summary

v0.25.7 hardens two source-processing boundaries and adds a reproducible local synthetic validation trial. No live Lean kernel, frontier model, or network service is required for these changes.

## Fixed

1. **Security comment stripping**
   - Removed regex comment stripping from security preflight.
   - Added a delimiter-aware Lean scanner that handles nested block comments and does not treat comment markers inside strings as comments.
   - The theorem-lock comment stripping path now uses the same scanner.

2. **Repair body replacement**
   - Removed broad regex substitution from `repair.replace_body`.
   - Added a delimiter-aware `:= by` proof-body splitter.
   - The splitter preserves `#print axioms` trailers, ignores anchors inside comments/strings, and stops before following top-level declarations.

3. **Synthetic validation report**
   - Added a 30-case, 20-domain corpus covering accepted mock-Lean proofs, Lean-like rejections, security traps, and theorem-drift traps.
   - Added generated JSON and Markdown metrics reports with corpus and raw-eval hashes.

## Verified metrics

The generated report records:

- 30 / 30 cases passed expected statuses.
- 12 accepted under deterministic mock Lean.
- 6 Lean-like rejections routed to `needs_repair`.
- 12 security/theorem-drift traps.
- 0 false theorem-drift/security escapes.

## Commands

```bash
python -m compileall -q shadowproof_core tests scripts
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
PYTHONPATH=. python scripts/run_synthetic_validation_trial.py
```

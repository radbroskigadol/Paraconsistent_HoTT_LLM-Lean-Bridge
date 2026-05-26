# Threat model

Lean is a proof checker, but a deployment that accepts arbitrary Lean text from a model/user should still treat it as code.

## Risks

- unbounded elaboration time
- memory exhaustion
- accidental execution of IO/eval features
- custom axioms
- `sorry` leaking into accepted proofs
- theorem-statement drift
- import abuse
- logs exposing private proof text

## Required deployment controls

- container sandbox
- CPU and memory limits
- timeout per request
- no network inside checker container
- conservative import allowlist
- reject `sorry`, `axiom`, `unsafe`, `#eval`, `run_cmd`
- audit final proof with `#print axioms`
- return exact Lean theorem checked
- keep theorem fingerprint in the result


## v0.25.4 server-boundary controls

- `target.lean_command` is rejected in request payloads.
- Theorem-lock drift is an error by default.
- Admin/file-writing HTTP routes are disabled by default and separately token-gated.
- JSON Schema validation runs before HTTP/ASGI dispatch for all 84 concrete routes through exact, descriptor, family, or generic schema lookup.
- Caller-controlled paths for reads/writes/scans are constrained to `SHADOWPROOF_ALLOWED_FILE_ROOTS`.
- `auth_mode=disabled` is development-only.
- Quota mode comparisons are normalized before enforcement.

These controls reduce API abuse risk but do not replace a production Lean sandbox.

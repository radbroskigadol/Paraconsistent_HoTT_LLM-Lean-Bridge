# Lean environment

Recommended project setup:

```bash
lake +leanprover/lean4:stable new shadowproof_lean_env math
cd shadowproof_lean_env
lake update
```

Then run ShadowProof from inside that project or set `SHADOWPROOF_LEAN_CMD`.

```bash
export SHADOWPROOF_LEAN_CMD="lake env lean"
python -m shadowproof_core.cli validate examples/tool_requests/validate_group_assoc.json
```

For production, pin Lean and Mathlib versions in `lean-toolchain` and `lakefile.toml`.

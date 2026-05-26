# `lean_project_template/`

This is a minimal Lean 4 / Mathlib project that formalizes the De Morgan
order-two symmetry claim made by the runtime `shadowproof demorgan-symmetry`
report.

## What it proves

`ShadowProof/DemorganSymmetry.lean` defines `L = Bool × Bool` and the
coordinate-swap involution and then proves, in Lean:

1. The swap is involutive (`demorganSwap_involutive`).
2. As a function, it squares to the identity (`demorganSwap_sq_eq_id`).
3. `top` and `bottom` are exchanged; `both` and `neither` are fixed.
4. The swap is **not** designation-preserving
   (`demorganSwap_not_designation_preserving`).
5. The generated automorphism group is Z/2 (`aut_L_is_Z2`).

These are the same algebraic facts that the Python implementation in
`shadowproof_core/bilattice.py` produces at runtime via
`demorgan_order_two_report()` and that `bilattice_axiom_report()` cross-checks
on every `shadowproof_shadowhott_audit` call.

## Building

```bash
cd lean_project_template
lake exe cache get   # optional: fetch Mathlib cache when available
lake build           # build ShadowProof.DemorganSymmetry
```

A successful build is the Lean-side counterpart to the JSON report
returned by:

```bash
python -m shadowproof_core.cli demorgan-symmetry examples/tool_requests/demorgan_symmetry.json
```

Together they form a two-witness setup: the Python report is the
runtime-checkable side; this Lean file is the kernel-checked side.


## Pinning note

This template now ships `lean-toolchain` and `lake-manifest.json`. The package audit environment may not have Lean/lake installed, so these files are reproducibility inputs rather than a live build transcript. A buyer CI runner with Lean installed should execute `lake build` and preserve the transcript in release evidence.

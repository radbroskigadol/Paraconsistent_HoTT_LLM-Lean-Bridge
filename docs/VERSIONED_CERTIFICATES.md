# Versioned certificates

A Lean result is meaningful only relative to its environment.

v5 attempts to capture:

```text
Lean command
Lean version
Lake version
lean-toolchain content
lake-manifest hash
Mathlib revision when discoverable
lakefile hash
Lean code hash
theorem fingerprint hash
security policy
axiom report
elapsed ms
```

## Why this matters

Mathlib names, imports, theorem statements, and tactic behavior can change across versions. A certificate should therefore say:

```text
Lean accepted this theorem under this pinned environment.
```

not merely:

```text
Lean accepted this theorem.
```

## Axiom audit

Generated Lean files should include:

```lean
#print axioms theorem_name
```

If the axiom report includes `sorryAx`, the proof is incomplete.

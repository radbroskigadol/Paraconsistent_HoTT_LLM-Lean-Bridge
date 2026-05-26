# Frontier-model bridge design

For frontier models, ShadowProof should be a native tool bridge, not a small local model.

## Correct architecture

```text
Frontier model
  produces DraftProposal JSON

ShadowProof
  checks schema
  checks theorem fingerprint
  checks security
  runs Lean
  compiles compact repair prompt
  records outcome metrics

Lean
  validates exact formal theorem
```

## Why not laptop training?

A laptop model will not reliably know all of Mathlib, all domains of mathematics, and Lean elaboration behavior. Frontier models plus tool feedback are stronger.

The trainable/local part should be:

```text
retrieval ranking
repair-template ranking
diagnostic compression
eval telemetry
```

not a standalone proof model.

## Model-call contract

The model should receive:

```text
DraftProposal schema
compact diagnostics
theorem fingerprint
allowed repair actions
forbidden theorem mutations
```

The model should return:

```text
DraftProposal JSON only
```

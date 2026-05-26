# Patch Notes v0.25.8 — Audit-Idea Implementation Pass

v0.25.8 implements the audit recommendations that can be safely shipped inside the repository without pretending to solve environment-dependent GA blockers.

## Implemented now

### Expanded evaluation metrics

`shadowproof_core.eval_harness` now tracks:

- human-review escalation count;
- expected human-review escalation count;
- missed escalation count;
- unexpected escalation count;
- human-review escalation accuracy;
- acceptance rate;
- repair request rate;
- average and median estimated token load;
- p95 elapsed time;
- drift-trap escape rate.

Eval cases may specify:

```json
{
  "expect_human_review": true
}
```

or use a trap kind such as:

```text
no_glutty_j_trap
glutty_trap
human_review_trap
contradiction_trap
```

### Proof-lifecycle observability hooks

`shadowproof_core.observability` now includes pure lifecycle trace helpers:

- `make_proof_lifecycle_trace(...)`
- `metric_event_from_lifecycle(...)`

These expose draft/security/theorem-lock/Lean/bilattice/routing/escalation stages without adding a hard OpenTelemetry dependency. Deployments with OpenTelemetry can attach these as span attributes; local pilots can record them as JSON.

Prometheus and metrics reports now include human-review and bilattice-both counters.

### Retrieval dependency and LSH metadata hooks

`shadowproof_index_mathlib` now supports:

```json
{
  "build_dependency_graph": true,
  "lsh_bucket_bits": 16
}
```

The indexer adds lexical dependency metadata, declaration structure hashes, and LSH-style buckets. This is not a full Tree-Sitter or Lean elaborator index. It is a safe pilot hook that can later be replaced by richer GraphRAG / AST retrieval without changing the API shape.

### Documentation updates

New docs:

- `docs/EVAL_OBSERVABILITY_RETRIEVAL_V25_8.md`
- `PATCH_NOTES_V25_8.md`

Updated docs:

- `CHANGELOG.md`
- `SECURITY.md`
- `docs/acquisition/DILIGENCE_STATUS.md`

## Intentionally not implemented in-core

The audits recommend several high-value but environment-dependent items. These remain GA blockers or optional extensions:

- production gVisor/Firecracker Lean worker image;
- external penetration test;
- real frontier-provider adapters with streaming/tool-call semantics;
- large customer corpora;
- signed image provenance and SLSA pipeline;
- real Tree-Sitter/Lean-elaborator Mathlib graph index;
- neural GNN/DPO/KTO repair policy training;
- univalence/cubical/HIT extensions in the production core.

The production soundness boundary remains finite, auditable, and ShadowHoTT-governed.

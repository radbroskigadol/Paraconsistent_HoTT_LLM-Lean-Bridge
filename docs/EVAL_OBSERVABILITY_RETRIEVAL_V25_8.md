# v0.25.8 Eval, Observability, and Retrieval Enhancements

This document records the practical subset of audit recommendations implemented in v0.25.8.

## Why this update exists

The attached audits recommended three especially useful near-term improvements:

1. stronger eval metrics;
2. deeper proof-lifecycle instrumentation;
3. richer Mathlib/domain retrieval hooks.

v0.25.8 implements these without changing the core ShadowHoTT safety boundary and without claiming full production GA.

## Evaluation harness additions

`shadowproof_core.eval_harness` now reports more deployment-relevant metrics:

- `acceptance_rate`
- `repair_request_rate`
- `human_review_count`
- `expected_human_review_count`
- `human_review_escalation_accuracy`
- `missed_human_review_escalation_count`
- `unexpected_human_review_escalation_count`
- `avg_estimated_tokens`
- `median_estimated_tokens`
- `avg_elapsed_ms`
- `p95_elapsed_ms`
- `false_theorem_drift_escape_rate`

Eval cases can declare human-review expectations explicitly:

```json
{
  "case_id": "glutty_accepted_refuted",
  "kind": "no_glutty_j_trap",
  "expect_human_review": true
}
```

The harness also infers an expected escalation for the following trap kinds:

```text
human_review_trap
glutty_trap
no_glutty_j_trap
contradiction_trap
```

This directly supports the audit request for measuring human-review escalation accuracy, not merely accept/reject accuracy.

## Proof-lifecycle observability

The new lifecycle helpers are dependency-light and pure:

```python
from shadowproof_core.observability import make_proof_lifecycle_trace, metric_event_from_lifecycle
```

They expose the following stages:

```text
draft_received
security_preflight
theorem_lock
lean_validation
bilattice_evaluation
routing_decision
repair_context
escalation
```

The trace captures:

- request id;
- tool name;
- tool status;
- Lean status;
- bilattice truth/refutation/designation/label;
- human-review requirement;
- stage statuses.

The existing `shadowproof_trace_envelope` tool now returns a `proof_lifecycle` field when passed a response-like payload under `response`.

Metrics and Prometheus text output now include:

```text
shadowproof_human_review_required_total
shadowproof_bilattice_both_total
shadowproof_lifecycle_stage_events_total{stage="..."}
```

## Retrieval dependency and LSH hooks

`shadowproof_index_mathlib` now accepts:

```json
{
  "build_dependency_graph": true,
  "lsh_bucket_bits": 16
}
```

The generated JSONL records include:

- `dependencies`
- `lsh_bucket`
- `structure_hash`
- `normalized_ast_hint`

When `build_dependency_graph` is true, a sidecar file is emitted:

```text
<output>.dependency_graph.json
```

This file contains declaration nodes and lexical dependency/import edges.

## Boundary note

The retrieval hook is intentionally conservative. It does not claim Tree-Sitter, dense embeddings, Lean elaborator integration, or a production GraphRAG stack. It is an API-compatible stepping stone toward those systems.

## Still outstanding for GA

v0.25.8 does not remove these blockers:

- production-isolated Lean worker;
- external security review;
- real frontier-provider adapters;
- large customer eval corpora;
- production provenance/signing pipeline;
- deployment-specific incident response.

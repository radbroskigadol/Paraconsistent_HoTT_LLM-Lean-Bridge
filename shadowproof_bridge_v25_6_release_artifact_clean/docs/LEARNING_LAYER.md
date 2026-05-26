# Learning layer

ShadowProof v4 learns from Lean rejections without changing the trusted validator.

## What it learns

It learns repair logistics:

- which diagnostic kinds tend to occur together
- which repair strategy solved a prior failure
- which theorem family the repair belonged to
- which prompts are shorter and effective
- which patch kinds lead to acceptance

It does **not** learn new mathematical truth.

## Privacy modes

### `hash_only`

Default.

Stores:

```text
theorem_family
diagnostic_kinds
severity_counts
error_fingerprints
lean_code_hash
theorem_text_hash
repair_strategy
outcome
```

Does not store raw proof text.

### `redacted`

Stores a short redacted diagnostic excerpt.

### `raw_local`

Stores a short raw excerpt locally. Useful for private single-user development, not recommended for hosted multi-user deployment.

## Memory file

Default:

```text
.shadowproof_memory/rejections.jsonl
```

Override:

```bash
export SHADOWPROOF_MEMORY_PATH=/path/to/rejections.jsonl
```

or pass:

```json
{"memory_path": "/path/to/rejections.jsonl"}
```

## Repair suggestion ranking

Ranking combines:

1. deterministic templates,
2. theorem family,
3. diagnostic kind overlap,
4. prior successful strategy evidence,
5. expected token cost.

The goal is fewer wasted LLM repair turns.

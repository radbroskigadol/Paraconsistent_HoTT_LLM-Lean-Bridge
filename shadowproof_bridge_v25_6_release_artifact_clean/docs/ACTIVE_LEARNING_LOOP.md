# Active learning loop

## Basic loop

```text
DraftProposal
  -> validate_draft
  -> rejected / needs_repair
  -> compile_repair_prompt
  -> LLM revised DraftProposal
  -> validate_draft
  -> record_outcome
```

## Outcome labels

```text
rejected   proof failed and no useful progress
unchanged  new attempt failed in the same way
improved   new attempt changed diagnostic class or reduced goals
accepted   Lean accepted
```

## What to record

After each attempt, record:

```json
{
  "outcome": "accepted",
  "repair_strategy": "group_assoc_known_paths",
  "patch_kind": "replace_tactic",
  "theorem_fingerprint": {},
  "diagnostics": []
}
```

## Efficiency metric

Track:

```text
tokens per accepted proof
repair turns per accepted proof
diagnostic class transition
false theorem-drift escapes
```

## Best near-term target

The system should first learn:

- theorem-name substitutions,
- rewrite direction fixes,
- typeclass-mismatch explanations,
- when to ask for a local lemma,
- when to reject as theorem drift.

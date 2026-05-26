# ShadowProof protocol

## LLM-to-bridge sequence

```text
1. User gives informal theorem/proof.
2. Assistant calls `shadowproof_validate`.
3. Bridge creates draft Lean code and theorem fingerprint.
4. Bridge security-preflights Lean code.
5. Bridge runs Lean.
6. Bridge classifies diagnostics.
7. Bridge proposes guarded patches.
8. Bridge repeats until accepted, rejected, unpatchable, timeout, or max iterations.
9. Bridge returns structured JSON.
```

## DraftProposal shape for future LLM translator

A future LLM front end should emit:

```json
{
  "theorem_name": "my_theorem",
  "lean_code": "import Mathlib\n...",
  "theorem_fingerprint": {
    "objects": [],
    "assumptions": [],
    "conclusion": "",
    "forbidden_drift": []
  },
  "proof_graph": [
    {
      "id": "n1",
      "source_text": "...",
      "truth": {"claim": "..."},
      "falsity": {"counterconditions": []},
      "boundary": {"ambiguities": [], "missing_data": []}
    }
  ]
}
```

The bridge should then check that the emitted Lean code respects the fingerprint before running Lean.

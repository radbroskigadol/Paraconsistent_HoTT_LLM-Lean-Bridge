# Deployment sketch

## Minimal production topology

```text
OpenAI/MCP tool host
  -> ShadowProof HTTP/MCP server
      -> isolated Lean worker container
          -> pinned Lean + Mathlib project
```

## Sandbox requirements

Run Lean inside a container with:

- no network
- read-only Mathlib cache
- writable temp directory only
- CPU limit
- memory limit
- process limit
- request timeout
- per-request log cap

## Recommended service split

```text
shadowproof-api      receives tool calls and validates JSON
shadowproof-worker   runs Lean in sandbox
shadowproof-cache    caches successful theorem checks by code hash
```

## Caching key

Use:

```text
sha256(lean_version + mathlib_revision + lean_code + security_policy)
```

A proof accepted under one Mathlib version may fail under another.

## Certificate fields

A useful certificate should include:

```text
theorem_name
lean_status
axiom_report
lean_version
mathlib_revision
security_policy
code_hash
theorem_fingerprint_hash
```

v3 includes the theorem fingerprint hash. Lean/Mathlib version capture is left as the next implementation step.

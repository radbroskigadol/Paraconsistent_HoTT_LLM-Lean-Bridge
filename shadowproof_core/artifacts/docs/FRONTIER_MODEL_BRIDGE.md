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


## v0.25.6 configured egress guardrails

`frontier_http` remains a generic buyer-adapter shim. Callers select a configured `provider_id`; they cannot supply provider URLs, headers, or bearer tokens in the request body.

Configured provider URLs are checked in two stages:

1. Literal host checks reject localhost, `.local`, private, loopback, link-local, reserved, multicast, and unspecified IP targets.
2. DNS names are resolved with Python `socket.getaddrinfo`; every returned address must be public-routable under the same policy. NXDOMAIN, resolver failure, empty results, or unparsable addresses fail closed.

Responses are read through `SHADOWPROOF_MODEL_PROVIDER_RESPONSE_MAX_BYTES` before JSON parsing. Timeouts and retries remain bounded by the request schema and server-side clamps. Production deployments should replace the generic shim with provider-specific adapters for authentication, streaming, redaction, quota, and model-specific response contracts.

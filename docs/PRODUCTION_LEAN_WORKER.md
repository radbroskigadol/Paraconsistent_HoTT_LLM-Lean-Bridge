# Production Lean Worker Hardening Plan

The bundled `deploy/lean-worker.Dockerfile` is a demo stub. Production deployments
that execute untrusted Lean code should replace it with an isolated Lean/Mathlib
worker controlled by the acquiring company or deployment operator.

## Required controls

- Pin the Lean/Mathlib image by immutable digest.
- Run as a non-root user with `no-new-privileges` and all Linux capabilities dropped.
- Disable network egress for proof-checking jobs.
- Use a read-only root filesystem plus a per-request tmpfs workspace.
- Apply CPU, memory, process-count, file-size, and wall-clock limits.
- Kill the full process tree on timeout.
- Export only bounded certificate artifacts, diagnostics, stdout/stderr snippets, and
  version metadata.
- Preserve the Lean toolchain version, Mathlib revision, image digest, request hash,
  theorem fingerprint, and certificate hash in the returned artifact.
- Route all worker calls through `SHADOWPROOF_LEAN_WORKER_MODE=http`; do not expose the
  worker directly to public clients.

## Candidate deployment patterns

Acceptable isolation layers include Docker with strict cgroups/seccomp, gVisor,
Firecracker microVMs, or Kubernetes Jobs/Pods with network policy and resource quotas.
The Python package deliberately does not claim to enforce kernel-level isolation by
itself.

## Current package boundary

v0.25.6 provides the bridge-side API contract, diagnostics, theorem-lock behavior,
local simulation, and worker-stub interface. A real buyer pilot should replace the
stub worker with a pinned Lean/Mathlib image and attach captured kernel transcripts
as pilot evidence.

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any

from .models import Diagnostic, DiagnosticSeverity, ObstructionKind
from .path_guard import resolve_under_allowed_root


DEFAULT_MEMORY_DIR = ".shadowproof_memory"
DEFAULT_MEMORY_FILE = "rejections.jsonl"


@dataclass
class LearningConfig:
    memory_path: str | None = None
    privacy_mode: str = "hash_only"  # hash_only | redacted | raw_local
    max_records_to_scan: int = 5000
    max_message_chars: int = 420
    enabled: bool = True
    tenant_id: str | None = None  # if set, segregates memory by tenant


@dataclass
class RejectionRecord:
    timestamp: float
    request_id: str
    theorem_family: str
    diagnostic_kinds: list[str]
    severity_counts: dict[str, int]
    error_fingerprints: list[str]
    lean_code_hash: str | None = None
    theorem_text_hash: str | None = None
    patch_kind: str | None = None
    repair_strategy: str | None = None
    outcome: str = "rejected"  # rejected | improved | accepted | unchanged
    token_estimate_in: int | None = None
    token_estimate_out: int | None = None
    stored_excerpt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None  # NEW: prevent cross-tenant memory contamination


@dataclass
class RepairSuggestion:
    rank: int
    strategy: str
    reason: str
    template: str
    expected_token_cost: int
    evidence_count: int = 0


class RejectionMemory:
    def __init__(self, config: LearningConfig | None = None):
        self.config = config or LearningConfig()
        self.path = resolve_memory_path(self.config.memory_path, self.config.tenant_id)
        self._load_warnings: list[str] = []

    def append(self, record: RejectionRecord) -> None:
        if not self.config.enabled:
            return
        # Stamp the active tenant onto every record so a later cross-tenant
        # read (e.g. when an operator points at a shared memory file) can
        # still segregate suggestions.
        if record.tenant_id is None:
            record.tenant_id = self.config.tenant_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def load(self) -> list[RejectionRecord]:
        if not self.path.exists():
            return []
        records: list[RejectionRecord] = []
        self._load_warnings = []
        with self.path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    # Drop fields the dataclass doesn't know about so old/new
                    # schemas remain forward/backward compatible without
                    # silently swallowing genuinely malformed lines.
                    valid_fields = {f.name for f in fields(RejectionRecord)}
                    filtered = {k: v for k, v in raw.items() if k in valid_fields}
                    records.append(RejectionRecord(**filtered))
                except Exception as exc:
                    self._load_warnings.append(f"line {lineno}: {exc}")
                    continue
        # Per-tenant view: if a tenant_id is configured, return only records
        # whose tenant_id matches (records lacking the field are treated as
        # belonging to the default tenant for backward compatibility).
        if self.config.tenant_id is not None:
            records = [r for r in records
                       if r.tenant_id in {None, "", self.config.tenant_id}]
        return records[-self.config.max_records_to_scan:]

    def stats(self) -> dict[str, Any]:
        records = self.load()
        by_family = Counter(r.theorem_family for r in records)
        by_outcome = Counter(r.outcome for r in records)
        by_kind = Counter(k for r in records for k in r.diagnostic_kinds)
        strategies = Counter(r.repair_strategy for r in records if r.repair_strategy)
        return {
            "memory_path": str(self.path),
            "record_count": len(records),
            "by_theorem_family": dict(by_family),
            "by_outcome": dict(by_outcome),
            "by_diagnostic_kind": dict(by_kind),
            "successful_strategies": dict(strategies),
        }

    def suggest(self, theorem_family: str, diagnostic_kinds: list[str], limit: int = 5) -> list[RepairSuggestion]:
        baseline = template_suggestions(theorem_family, diagnostic_kinds)
        records = self.load()

        family_matches = [
            r for r in records
            if r.theorem_family == theorem_family
            and r.outcome in {"accepted", "improved"}
            and r.repair_strategy
        ]
        kind_set = set(diagnostic_kinds)

        score: dict[str, int] = defaultdict(int)
        evidence: dict[str, int] = defaultdict(int)

        for r in family_matches:
            overlap = len(kind_set.intersection(set(r.diagnostic_kinds)))
            if overlap:
                score[r.repair_strategy or ""] += 2 * overlap + (3 if r.outcome == "accepted" else 1)
                evidence[r.repair_strategy or ""] += 1

        # boost baseline templates with learned evidence
        out = []
        seen = set()
        for s in baseline:
            learned = score.get(s.strategy, 0)
            ev = evidence.get(s.strategy, 0)
            out.append(RepairSuggestion(
                rank=0,
                strategy=s.strategy,
                reason=s.reason + (f" Learned evidence: {ev} matching prior successes." if ev else ""),
                template=s.template,
                expected_token_cost=s.expected_token_cost,
                evidence_count=ev,
            ))
            seen.add(s.strategy)

        # add strategies seen in memory but not in baseline
        for strat, sc in sorted(score.items(), key=lambda x: -x[1]):
            if strat and strat not in seen:
                out.append(RepairSuggestion(
                    rank=0,
                    strategy=strat,
                    reason=f"Prior successful repair strategy for {theorem_family} with overlapping diagnostics.",
                    template=f"Apply learned repair strategy: {strat}. Preserve theorem fingerprint exactly.",
                    expected_token_cost=80,
                    evidence_count=evidence[strat],
                ))

        out.sort(key=lambda s: (-(s.evidence_count), s.expected_token_cost, s.strategy))
        for i, s in enumerate(out[:limit], 1):
            s.rank = i
        return out[:limit]


def resolve_memory_path(memory_path: str | None, tenant_id: str | None = None) -> Path:
    """Resolve the memory file path, segregating by tenant where possible.

    Precedence:
      1. explicit ``memory_path`` argument
      2. ``SHADOWPROOF_MEMORY_PATH`` environment variable
      3. tenant-segregated default: ``.shadowproof_memory/<tenant>/rejections.jsonl``
      4. global default: ``.shadowproof_memory/rejections.jsonl``

    The tenant fallback exists so that operators who use the default path
    don't accidentally co-mingle rejection records across tenants.  Callers
    that intentionally want a shared memory across tenants can pass a
    ``memory_path`` explicitly.
    """
    if memory_path:
        return resolve_under_allowed_root(memory_path, kind="memory_path")
    env = os.environ.get("SHADOWPROOF_MEMORY_PATH")
    if env:
        return resolve_under_allowed_root(env, kind="SHADOWPROOF_MEMORY_PATH")
    if tenant_id:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tenant_id).strip(".") or "default"
        return resolve_under_allowed_root(Path(DEFAULT_MEMORY_DIR) / safe / DEFAULT_MEMORY_FILE, kind="tenant memory_path")
    return resolve_under_allowed_root(Path(DEFAULT_MEMORY_DIR) / DEFAULT_MEMORY_FILE, kind="memory_path")


def make_rejection_record(payload: dict[str, Any], config: LearningConfig | None = None) -> RejectionRecord:
    config = config or LearningConfig()
    request_id = str(payload.get("request_id", "unknown"))
    theorem_family = extract_theorem_family(payload)
    diagnostics = payload.get("diagnostics") or payload.get("lean_diagnostics") or []
    diagnostic_kinds = normalize_diagnostic_kinds(diagnostics)
    severity_counts = count_severities(diagnostics)
    messages = [str(d.get("message", "")) for d in diagnostics if isinstance(d, dict)]
    error_fps = [fingerprint_error(m) for m in messages[:10] if m]

    lean_code = str(payload.get("lean_code") or payload.get("final_lean_code") or "")
    theorem_text = str(payload.get("natural_language_theorem") or payload.get("theorem") or "")

    excerpt = None
    if config.privacy_mode == "raw_local":
        excerpt = "\n\n".join(messages)[:config.max_message_chars]
    elif config.privacy_mode == "redacted":
        excerpt = redact_text("\n\n".join(messages))[:config.max_message_chars]

    return RejectionRecord(
        timestamp=time.time(),
        request_id=request_id,
        theorem_family=theorem_family,
        diagnostic_kinds=diagnostic_kinds,
        severity_counts=severity_counts,
        error_fingerprints=error_fps,
        lean_code_hash=sha256_text(lean_code) if lean_code else None,
        theorem_text_hash=sha256_text(theorem_text) if theorem_text else None,
        patch_kind=payload.get("patch_kind"),
        repair_strategy=payload.get("repair_strategy"),
        outcome=str(payload.get("outcome", payload.get("status", "rejected"))),
        token_estimate_in=estimate_tokens(lean_code + theorem_text + "\n".join(messages)),
        token_estimate_out=payload.get("token_estimate_out"),
        stored_excerpt=excerpt,
        metadata=safe_metadata(payload.get("metadata", {})),
        tenant_id=config.tenant_id or (str(payload.get("tenant_id")) if payload.get("tenant_id") else None),
    )


def normalize_diagnostic_kinds(diagnostics: list[Any]) -> list[str]:
    kinds = []
    for d in diagnostics:
        if isinstance(d, dict):
            k = d.get("kind") or d.get("code") or "unknown"
            kinds.append(str(k))
        else:
            kinds.append("unknown")
    return sorted(set(kinds))


def count_severities(diagnostics: list[Any]) -> dict[str, int]:
    c = Counter()
    for d in diagnostics:
        if isinstance(d, dict):
            c[str(d.get("severity", "unknown"))] += 1
        else:
            c["unknown"] += 1
    return dict(c)


def extract_theorem_family(payload: dict[str, Any]) -> str:
    fp = payload.get("theorem_fingerprint") or {}
    if isinstance(fp, dict) and fp.get("theorem_family"):
        return str(fp["theorem_family"])
    draft = payload.get("draft") or {}
    if isinstance(draft, dict):
        fp2 = draft.get("theorem_fingerprint") or {}
        if isinstance(fp2, dict) and fp2.get("theorem_family"):
            return str(fp2["theorem_family"])
    return str(payload.get("theorem_family", "unknown"))


def fingerprint_error(message: str) -> str:
    norm = normalize_error_message(message)
    return sha256_text(norm)[:16]


def normalize_error_message(message: str) -> str:
    s = message.lower()
    s = re.sub(r"/tmp/[^:\s]+", "/tmp/FILE", s)
    s = re.sub(r":\d+:\d+:", ":LINE:COL:", s)
    s = re.sub(r"\b[a-f0-9]{8,}\b", "HASH", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:1000]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    # Rough, deterministic estimate. Good enough for prompt budgeting.
    if not text:
        return 0
    chunks = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return max(1, int(len(chunks) * 0.75))


def redact_text(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL]", text)
    text = re.sub(r"/(?:[\w.-]+/)+[\w.-]+", "[PATH]", text)
    text = re.sub(r"\b[A-Fa-f0-9]{16,}\b", "[HASH]", text)
    return text


def safe_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    safe = {}
    for k, v in raw.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe[str(k)[:80]] = v if not isinstance(v, str) else v[:240]
    return safe


def template_suggestions(theorem_family: str, diagnostic_kinds: list[str]) -> list[RepairSuggestion]:
    kinds = set(diagnostic_kinds)
    suggestions: list[RepairSuggestion] = []

    if "unknown_identifier" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="resolve_unknown_identifier",
            reason="Lean could not resolve a constant/tactic/theorem name.",
            template=(
                "Do not change the theorem statement. Repair only identifiers/imports/proof terms. "
                "Replace unknown theorem names with Mathlib names likely to match the goal, or expand into a local proof. "
                "Return a new DraftProposal JSON only."
            ),
            expected_token_cost=95,
        ))

    if "unsolved_goal" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="solve_current_goal_minimally",
            reason="Lean elaborated the theorem but left proof goals unsolved.",
            template=(
                "Inspect the stated Lean goal and available hypotheses. Add the minimal tactic sequence or calc proof. "
                "Do not add assumptions, change types, weaken the conclusion, or use sorry."
            ),
            expected_token_cost=90,
        ))

    if "type_mismatch" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="repair_type_shape",
            reason="A proof term has the wrong type for the current goal.",
            template=(
                "Repair the proof term shape. Check argument order, implicit arguments, coercions, and rewrite orientation. "
                "Prefer explicit `have` steps or `calc` if direct exact fails."
            ),
            expected_token_cost=110,
        ))

    if "missing_typeclass_instance" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="repair_typeclass_context",
            reason="Lean cannot synthesize a needed structure instance.",
            template=(
                "Do not upgrade the theorem's structure unless theorem mutation is explicitly allowed. "
                "Use only the existing typeclass context from the fingerprint. If the theorem truly needs stronger structure, report theorem_drift."
            ),
            expected_token_cost=105,
        ))

    if "missing_import" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="repair_imports",
            reason="Required declarations are not in scope.",
            template=(
                "Add the smallest allowed import from the target import allowlist. "
                "If in doubt use `import Mathlib`; do not add non-allowlisted imports."
            ),
            expected_token_cost=70,
        ))

    if "theorem_drift" in kinds:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="preserve_theorem_fingerprint",
            reason="The proposed fix appears to mutate the theorem.",
            template=(
                "Reject theorem mutation. Restore the exact objects, assumptions, and conclusion from the theorem_fingerprint. "
                "Repair only the proof body unless the user explicitly authorizes theorem revision."
            ),
            expected_token_cost=75,
        ))

    if theorem_family == "group_assoc":
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="group_assoc_known_paths",
            reason="Known compact repairs exist for group associativity.",
            template="Try `simpa using mul_assoc a b c`, `exact mul_assoc a b c`, or `rw [mul_assoc]`.",
            expected_token_cost=35,
        ))

    if theorem_family == "group_left_cancel":
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="group_left_cancel_known_paths",
            reason="Known compact repairs exist for group left cancellation.",
            template="Try `exact mul_left_cancel h`; if unavailable, expand with a calc proof using `a⁻¹ *` and `mul_assoc`.",
            expected_token_cost=45,
        ))

    if not suggestions:
        suggestions.append(RepairSuggestion(
            rank=0,
            strategy="llm_minimal_rewrite",
            reason="No specialized template matched.",
            template=(
                "Produce a minimal revised DraftProposal. Preserve theorem_fingerprint exactly. "
                "Only change imports/proof body/local lemmas. Summarize the obstruction in proof_graph.boundary."
            ),
            expected_token_cost=80,
        ))

    # Deduplicate while preserving order.
    seen = set()
    out = []
    for s in suggestions:
        if s.strategy not in seen:
            out.append(s)
            seen.add(s.strategy)
    for i, s in enumerate(out, 1):
        s.rank = i
    return out

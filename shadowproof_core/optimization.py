from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .path_guard import resolve_under_allowed_root


DEFAULT_OPT_DIR = ".shadowproof_opt"
DEFAULT_EVENTS_FILE = "optimization_events.jsonl"
DEFAULT_POLICY_FILE = "policies.json"


@dataclass
class OptimizationConfig:
    events_path: str | None = None
    policy_path: str | None = None
    privacy_mode: str = "hash_only"  # hash_only | redacted | raw_local
    learning_enabled: bool = True
    exploration_rate: float = 0.0
    min_evidence: int = 3
    max_records_to_scan: int = 20000


@dataclass
class OptimizationContext:
    company_id: str = "default_company"
    frontier_model_id: str = "unknown_model"
    domain: str = "unknown_domain"
    subfield: str = "general"
    task_type: str = "draft_repair"
    theorem_family: str = "unknown"
    diagnostic_kinds: list[str] = field(default_factory=list)
    user_segment: str = "default"
    deployment_stage: str = "offline"  # offline | shadow | canary | production
    policy_version: str | None = None


@dataclass
class OptimizationAction:
    repair_strategy: str = "llm_minimal_rewrite"
    prompt_template: str = "compact_repair"
    retrieval_profile: str = "default"
    token_budget: int = 900
    deterministic_repair_first: bool = True
    require_draft_schema_reminder: bool = True
    proof_graph_detail: str = "medium"  # low | medium | high
    escalation_model: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class OptimizationOutcome:
    status: str = "unknown"  # accepted | improved | rejected | unchanged | theorem_drift_blocked
    accepted: bool = False
    repair_turns: int = 0
    estimated_tokens: int = 0
    elapsed_ms: int = 0
    theorem_drift_escape: bool = False
    user_accepted: bool | None = None


@dataclass
class OptimizationEvent:
    timestamp: float
    event_id: str
    context: OptimizationContext
    action: OptimizationAction
    outcome: OptimizationOutcome
    feature_key: str
    action_key: str
    reward: float
    stored_excerpt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyArmStats:
    action: OptimizationAction
    count: int = 0
    reward_sum: float = 0.0
    accepted_count: int = 0
    token_sum: int = 0
    turn_sum: int = 0
    drift_escape_count: int = 0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.count if self.count else 0.0


@dataclass
class PolicySuggestion:
    feature_key: str
    action_key: str
    action: OptimizationAction
    confidence: str
    reason: str
    expected_reward: float
    evidence_count: int
    alternatives: list[dict[str, Any]] = field(default_factory=list)


class OptimizationStore:
    def __init__(self, config: OptimizationConfig | None = None):
        self.config = config or OptimizationConfig()
        self.events_path = resolve_events_path(self.config.events_path)
        self.policy_path = resolve_policy_path(self.config.policy_path)

    def append_event(self, event: OptimizationEvent) -> None:
        if not self.config.learning_enabled:
            return
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dataclass_to_jsonable(event), ensure_ascii=False) + "\n")

    def load_events(self) -> list[OptimizationEvent]:
        if not self.events_path.exists():
            return []
        raw_events = []
        with self.events_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    raw_events.append(json.loads(line))
                except Exception:
                    continue
        raw_events = raw_events[-self.config.max_records_to_scan:]
        return [event_from_raw(r) for r in raw_events]

    def train_policy(self) -> dict[str, Any]:
        events = self.load_events()
        table: dict[str, dict[str, PolicyArmStats]] = {}

        for ev in events:
            table.setdefault(ev.feature_key, {})
            if ev.action_key not in table[ev.feature_key]:
                table[ev.feature_key][ev.action_key] = PolicyArmStats(action=ev.action)
            stats = table[ev.feature_key][ev.action_key]
            stats.count += 1
            stats.reward_sum += ev.reward
            stats.accepted_count += 1 if ev.outcome.accepted else 0
            stats.token_sum += ev.outcome.estimated_tokens
            stats.turn_sum += ev.outcome.repair_turns
            stats.drift_escape_count += 1 if ev.outcome.theorem_drift_escape else 0

        policy = {
            "policy_version": policy_version_hash(events),
            "created_at": time.time(),
            "event_count": len(events),
            "features": {},
        }

        for feature_key, arms in table.items():
            ranked = sorted(arms.items(), key=lambda kv: ucb_score(kv[1], total_count=sum(a.count for a in arms.values())), reverse=True)
            policy["features"][feature_key] = [
                {
                    "action_key": action_key,
                    "action": dataclass_to_jsonable(stats.action),
                    "count": stats.count,
                    "mean_reward": stats.mean_reward,
                    "accepted_count": stats.accepted_count,
                    "avg_tokens": stats.token_sum / stats.count if stats.count else None,
                    "avg_repair_turns": stats.turn_sum / stats.count if stats.count else None,
                    "drift_escape_count": stats.drift_escape_count,
                }
                for action_key, stats in ranked
            ]

        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
        return policy

    def load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            return {"policy_version": "empty", "features": {}, "event_count": 0}
        try:
            return json.loads(self.policy_path.read_text(encoding="utf-8"))
        except Exception:
            return {"policy_version": "corrupt", "features": {}, "event_count": 0}

    def stats(self) -> dict[str, Any]:
        events = self.load_events()
        by_model = Counter(ev.context.frontier_model_id for ev in events)
        by_domain = Counter(ev.context.domain for ev in events)
        by_subfield = Counter(ev.context.subfield for ev in events)
        by_status = Counter(ev.outcome.status for ev in events)
        by_strategy = Counter(ev.action.repair_strategy for ev in events)
        accepted = [ev for ev in events if ev.outcome.accepted]
        return {
            "events_path": str(self.events_path),
            "policy_path": str(self.policy_path),
            "event_count": len(events),
            "accepted_count": len(accepted),
            "by_frontier_model": dict(by_model),
            "by_domain": dict(by_domain),
            "by_subfield": dict(by_subfield),
            "by_status": dict(by_status),
            "by_repair_strategy": dict(by_strategy),
            "avg_tokens_accepted": statistics.mean([ev.outcome.estimated_tokens for ev in accepted]) if accepted else None,
            "avg_turns_accepted": statistics.mean([ev.outcome.repair_turns for ev in accepted]) if accepted else None,
            "theorem_drift_escape_count": sum(1 for ev in events if ev.outcome.theorem_drift_escape),
        }


class OptimizationPolicyEngine:
    def __init__(self, config: OptimizationConfig | None = None):
        self.config = config or OptimizationConfig()
        self.store = OptimizationStore(self.config)

    def suggest(self, context: OptimizationContext) -> PolicySuggestion:
        feature_key = context_feature_key(context)
        policy = self.store.load_policy()
        arms = policy.get("features", {}).get(feature_key, [])

        # Backoff sequence lets the policy generalize when a subfield/model has little data.
        backoff_keys = feature_backoff_keys(context)
        for key in backoff_keys:
            arms = policy.get("features", {}).get(key, [])
            if arms:
                feature_key = key
                break

        if arms and random.random() >= self.config.exploration_rate:
            best = arms[0]
            action = action_from_raw(best["action"])
            confidence = confidence_from_count(best.get("count", 0), self.config.min_evidence)
            alternatives = arms[1:4]
            return PolicySuggestion(
                feature_key=feature_key,
                action_key=best["action_key"],
                action=action,
                confidence=confidence,
                reason=f"Selected learned policy arm with mean_reward={best.get('mean_reward'):.3f}, count={best.get('count')}.",
                expected_reward=float(best.get("mean_reward", 0.0)),
                evidence_count=int(best.get("count", 0)),
                alternatives=alternatives,
            )

        # Exploration or cold start.
        action = default_action_for_context(context)
        return PolicySuggestion(
            feature_key=feature_key,
            action_key=action_key(action),
            action=action,
            confidence="cold_start",
            reason="No sufficient learned policy for this context; using domain/default heuristic.",
            expected_reward=0.0,
            evidence_count=0,
            alternatives=[],
        )


def context_from_payload(payload: dict[str, Any]) -> OptimizationContext:
    ctx = payload.get("optimization_context") or payload.get("context") or {}
    fp = payload.get("theorem_fingerprint") or {}
    if not fp and isinstance(payload.get("draft"), dict):
        fp = payload["draft"].get("theorem_fingerprint", {})
    diagnostics = payload.get("diagnostics", [])
    diag_kinds = sorted(set(str(d.get("kind", "unknown")) for d in diagnostics if isinstance(d, dict)))

    return OptimizationContext(
        company_id=str(ctx.get("company_id", payload.get("company_id", "default_company"))),
        frontier_model_id=str(ctx.get("frontier_model_id", payload.get("frontier_model_id", "unknown_model"))),
        domain=str(ctx.get("domain", payload.get("domain", "unknown_domain"))),
        subfield=str(ctx.get("subfield", payload.get("subfield", "general"))),
        task_type=str(ctx.get("task_type", payload.get("task_type", "draft_repair"))),
        theorem_family=str(ctx.get("theorem_family", fp.get("theorem_family", payload.get("theorem_family", "unknown")))),
        diagnostic_kinds=list(ctx.get("diagnostic_kinds", diag_kinds)),
        user_segment=str(ctx.get("user_segment", payload.get("user_segment", "default"))),
        deployment_stage=str(ctx.get("deployment_stage", payload.get("deployment_stage", "offline"))),
        policy_version=ctx.get("policy_version", payload.get("policy_version")),
    )


def action_from_payload(payload: dict[str, Any]) -> OptimizationAction:
    raw = payload.get("optimization_action") or payload.get("action") or {}
    return OptimizationAction(
        repair_strategy=str(raw.get("repair_strategy", payload.get("repair_strategy", "llm_minimal_rewrite"))),
        prompt_template=str(raw.get("prompt_template", payload.get("prompt_template", "compact_repair"))),
        retrieval_profile=str(raw.get("retrieval_profile", payload.get("retrieval_profile", "default"))),
        token_budget=int(raw.get("token_budget", payload.get("token_budget", 900))),
        deterministic_repair_first=bool(raw.get("deterministic_repair_first", payload.get("deterministic_repair_first", True))),
        require_draft_schema_reminder=bool(raw.get("require_draft_schema_reminder", payload.get("require_draft_schema_reminder", True))),
        proof_graph_detail=str(raw.get("proof_graph_detail", payload.get("proof_graph_detail", "medium"))),
        escalation_model=raw.get("escalation_model", payload.get("escalation_model")),
        notes=list(raw.get("notes", [])),
    )


def outcome_from_payload(payload: dict[str, Any]) -> OptimizationOutcome:
    raw = payload.get("optimization_outcome") or payload.get("outcome_details") or {}
    status = str(raw.get("status", payload.get("outcome", payload.get("status", "unknown"))))
    accepted = bool(raw.get("accepted", status == "accepted" or (payload.get("status") == "ok" and payload.get("lean_status") == "accepted")))
    return OptimizationOutcome(
        status=status,
        accepted=accepted,
        repair_turns=int(raw.get("repair_turns", payload.get("repair_turns", len(payload.get("patches", []) or [])))),
        estimated_tokens=int(raw.get("estimated_tokens", payload.get("estimated_tokens", 0))),
        elapsed_ms=int(raw.get("elapsed_ms", payload.get("elapsed_ms", 0))),
        theorem_drift_escape=bool(raw.get("theorem_drift_escape", payload.get("theorem_drift_escape", False))),
        user_accepted=raw.get("user_accepted", payload.get("user_accepted")),
    )


def event_from_payload(payload: dict[str, Any], config: OptimizationConfig | None = None) -> OptimizationEvent:
    config = config or OptimizationConfig()
    context = context_from_payload(payload)
    action = action_from_payload(payload)
    outcome = outcome_from_payload(payload)
    feature_key = context_feature_key(context)
    akey = action_key(action)
    reward = compute_reward(outcome)
    excerpt = None
    if config.privacy_mode == "raw_local":
        excerpt = str(payload.get("excerpt") or payload.get("final_lean_code") or "")[:1000]
    elif config.privacy_mode == "redacted":
        excerpt = redact(str(payload.get("excerpt") or ""))[:1000]

    event_id = payload.get("event_id") or stable_hash({
        "t": time.time(),
        "context": context.__dict__,
        "action": action.__dict__,
        "outcome": outcome.__dict__,
    })[:16]

    return OptimizationEvent(
        timestamp=time.time(),
        event_id=str(event_id),
        context=context,
        action=action,
        outcome=outcome,
        feature_key=feature_key,
        action_key=akey,
        reward=reward,
        stored_excerpt=excerpt,
        metadata=safe_metadata(payload.get("metadata", {})),
    )


def default_action_for_context(ctx: OptimizationContext) -> OptimizationAction:
    kinds = set(ctx.diagnostic_kinds)
    domain = ctx.domain.lower()
    subfield = ctx.subfield.lower()

    action = OptimizationAction()

    if "unknown_identifier" in kinds:
        action.repair_strategy = "resolve_unknown_identifier"
        action.retrieval_profile = "mathlib_name_search"
        action.token_budget = 800
    elif "type_mismatch" in kinds:
        action.repair_strategy = "repair_type_shape"
        action.prompt_template = "type_shape_repair"
        action.token_budget = 1100
        action.proof_graph_detail = "high"
    elif "unsolved_goal" in kinds:
        action.repair_strategy = "solve_current_goal_minimally"
        action.prompt_template = "goal_state_repair"
        action.token_budget = 1000
    elif "theorem_drift" in kinds:
        action.repair_strategy = "preserve_theorem_fingerprint"
        action.prompt_template = "drift_rejection"
        action.token_budget = 700
        action.deterministic_repair_first = False

    if domain in {"category_theory", "topology", "analysis"} or subfield in {"algebraic_geometry", "homotopy_type_theory"}:
        action.proof_graph_detail = "high"
        action.token_budget = max(action.token_budget, 1400)
        action.retrieval_profile = f"{domain}_deep" if domain != "unknown_domain" else "deep_mathlib"
    elif domain in {"logic", "sets", "order"}:
        action.token_budget = min(action.token_budget, 900)

    action.notes.append("cold-start heuristic selected by OptimizationPolicyEngine")
    return action


def compute_reward(outcome: OptimizationOutcome) -> float:
    reward = 0.0
    if outcome.accepted:
        reward += 10.0
    elif outcome.status == "improved":
        reward += 3.0
    elif outcome.status == "theorem_drift_blocked":
        reward += 2.0
    elif outcome.status == "rejected":
        reward -= 1.0
    elif outcome.status == "unchanged":
        reward -= 2.0

    reward -= min(outcome.repair_turns, 10) * 0.35
    reward -= min(outcome.estimated_tokens, 10000) / 2500.0
    reward -= min(outcome.elapsed_ms, 120000) / 60000.0

    if outcome.theorem_drift_escape:
        reward -= 50.0
    if outcome.user_accepted is True:
        reward += 1.0
    elif outcome.user_accepted is False:
        reward -= 1.0

    return round(reward, 6)


def context_feature_key(ctx: OptimizationContext) -> str:
    parts = [
        ctx.company_id,
        ctx.frontier_model_id,
        ctx.domain,
        ctx.subfield,
        ctx.task_type,
        ctx.theorem_family,
        ",".join(sorted(ctx.diagnostic_kinds)),
        ctx.user_segment,
    ]
    return "|".join(parts)


def feature_backoff_keys(ctx: OptimizationContext) -> list[str]:
    diag = ",".join(sorted(ctx.diagnostic_kinds))
    return [
        context_feature_key(ctx),
        "|".join([ctx.company_id, ctx.frontier_model_id, ctx.domain, "general", ctx.task_type, ctx.theorem_family, diag, ctx.user_segment]),
        "|".join([ctx.company_id, ctx.frontier_model_id, ctx.domain, "general", ctx.task_type, "unknown", diag, "default"]),
        "|".join([ctx.company_id, "any_model", ctx.domain, "general", ctx.task_type, "unknown", diag, "default"]),
        "|".join(["global", "any_model", ctx.domain, "general", ctx.task_type, "unknown", diag, "default"]),
    ]


def action_key(action: OptimizationAction) -> str:
    return stable_hash({
        "repair_strategy": action.repair_strategy,
        "prompt_template": action.prompt_template,
        "retrieval_profile": action.retrieval_profile,
        "token_budget": bucket_token_budget(action.token_budget),
        "deterministic_repair_first": action.deterministic_repair_first,
        "require_draft_schema_reminder": action.require_draft_schema_reminder,
        "proof_graph_detail": action.proof_graph_detail,
        "escalation_model": action.escalation_model,
    })[:16]


def bucket_token_budget(n: int) -> int:
    if n <= 500: return 500
    if n <= 800: return 800
    if n <= 1200: return 1200
    if n <= 1600: return 1600
    if n <= 2400: return 2400
    return 4000


def ucb_score(stats: PolicyArmStats, total_count: int, c: float = 1.25) -> float:
    if stats.count == 0:
        return float("inf")
    return stats.mean_reward + c * math.sqrt(math.log(max(total_count, 2)) / stats.count)


def confidence_from_count(count: int, min_evidence: int) -> str:
    if count == 0:
        return "cold_start"
    if count < min_evidence:
        return "low"
    if count < min_evidence * 5:
        return "medium"
    return "high"


def resolve_events_path(path: str | None) -> Path:
    if path:
        return resolve_under_allowed_root(path, kind="optimization events_path")
    env = os.environ.get("SHADOWPROOF_OPT_EVENTS_PATH")
    if env:
        return resolve_under_allowed_root(env, kind="SHADOWPROOF_OPT_EVENTS_PATH")
    return resolve_under_allowed_root(Path(DEFAULT_OPT_DIR) / DEFAULT_EVENTS_FILE, kind="optimization events_path")


def resolve_policy_path(path: str | None) -> Path:
    if path:
        return resolve_under_allowed_root(path, kind="optimization policy_path")
    env = os.environ.get("SHADOWPROOF_OPT_POLICY_PATH")
    if env:
        return resolve_under_allowed_root(env, kind="SHADOWPROOF_OPT_POLICY_PATH")
    return resolve_under_allowed_root(Path(DEFAULT_OPT_DIR) / DEFAULT_POLICY_FILE, kind="optimization policy_path")


def policy_version_hash(events: list[OptimizationEvent]) -> str:
    basis = [(ev.feature_key, ev.action_key, ev.reward) for ev in events[-5000:]]
    return stable_hash(basis)[:16]


def stable_hash(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dataclass_to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: dataclass_to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [dataclass_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: dataclass_to_jsonable(v) for k, v in obj.items()}
    return obj


def event_from_raw(raw: dict[str, Any]) -> OptimizationEvent:
    ctx = OptimizationContext(**raw.get("context", {}))
    action = OptimizationAction(**raw.get("action", {}))
    outcome = OptimizationOutcome(**raw.get("outcome", {}))
    return OptimizationEvent(
        timestamp=float(raw.get("timestamp", 0.0)),
        event_id=str(raw.get("event_id", "")),
        context=ctx,
        action=action,
        outcome=outcome,
        feature_key=str(raw.get("feature_key", context_feature_key(ctx))),
        action_key=str(raw.get("action_key", action_key(action))),
        reward=float(raw.get("reward", compute_reward(outcome))),
        stored_excerpt=raw.get("stored_excerpt"),
        metadata=dict(raw.get("metadata", {})),
    )


def action_from_raw(raw: dict[str, Any]) -> OptimizationAction:
    return OptimizationAction(
        repair_strategy=str(raw.get("repair_strategy", "llm_minimal_rewrite")),
        prompt_template=str(raw.get("prompt_template", "compact_repair")),
        retrieval_profile=str(raw.get("retrieval_profile", "default")),
        token_budget=int(raw.get("token_budget", 900)),
        deterministic_repair_first=bool(raw.get("deterministic_repair_first", True)),
        require_draft_schema_reminder=bool(raw.get("require_draft_schema_reminder", True)),
        proof_graph_detail=str(raw.get("proof_graph_detail", "medium")),
        escalation_model=raw.get("escalation_model"),
        notes=list(raw.get("notes", [])),
    )


def redact(text: str) -> str:
    import re
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL]", text)
    text = re.sub(r"/(?:[\w.-]+/)+[\w.-]+", "[PATH]", text)
    text = re.sub(r"\b[A-Fa-f0-9]{16,}\b", "[HASH]", text)
    return text


def safe_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)[:80]] = v if not isinstance(v, str) else v[:240]
    return out

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any


BYTES_PER_PARAM = {
    "fp32": 4.0,
    "tf32": 4.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "int8": 1.0,
    "int4": 0.5,
}

OPTIMIZER_MULTIPLIER = {
    # Approximate trainable-parameter memory multipliers, excluding activations.
    # These are deliberately conservative planning constants, not vendor claims.
    "none": 1.0,
    "sgd": 3.0,
    "adamw": 8.0,
    "adamw_8bit": 4.0,
    "adafactor": 3.5,
}


@dataclass(frozen=True)
class AdapterGeometry:
    """Model-agnostic adapter geometry for offline capacity planning.

    This does not call or depend on any LLM.  It estimates trainable LoRA-style
    adapter parameters from a target hidden size, layer count, rank, and number
    of adapted matrices per layer.
    """

    hidden_size: int = 4096
    num_layers: int = 32
    target_matrices_per_layer: int = 4
    rank: int = 16
    include_bias_params: bool = False

    @property
    def trainable_params(self) -> int:
        # For one dense H×H matrix, LoRA adds A:H×r and B:r×H = 2Hr.
        base = 2 * self.hidden_size * self.rank * self.target_matrices_per_layer * self.num_layers
        if self.include_bias_params:
            base += self.hidden_size * self.target_matrices_per_layer * self.num_layers
        return int(base)


@dataclass(frozen=True)
class TrainingCapacityConfig:
    """Offline, non-integrated training-capacity planner.

    The planner is meant for buyer-side integration.  It sizes param budgets,
    storage, and minimal event targets for future bespoke optimization without
    embedding a Lean runtime, LLM client, trainer, or customer data.
    """

    base_model_params_b: float = 7.0
    quantization_bits: int = 4
    precision: str = "bf16"
    optimizer: str = "adamw_8bit"
    gpu_vram_gb: float | None = None
    activation_overhead_gb: float = 2.0
    safety_margin: float = 0.88
    domains: list[str] = field(default_factory=lambda: ["algebra", "analysis", "logic", "topology"])
    subfields_per_domain: int = 6
    arms_per_subfield: int = 12
    min_events_per_arm: int = 30
    target_policy_versions: int = 3
    adapter_geometry: AdapterGeometry = field(default_factory=AdapterGeometry)


@dataclass(frozen=True)
class CapacityPlan:
    mode: str
    base_model_storage_gb: float
    adapter_trainable_params: int
    adapter_trainable_params_m: float
    estimated_trainable_memory_gb: float
    estimated_total_training_footprint_gb: float
    fits_requested_vram: bool | None
    recommended_rank: int
    rank_schedule: list[dict[str, Any]]
    policy_event_capacity: dict[str, Any]
    recommendations: list[str]
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_capacity_plan(payload: dict[str, Any] | None = None) -> CapacityPlan:
    payload = payload or {}
    geometry_payload = dict(payload.get("adapter_geometry") or {})
    geometry = AdapterGeometry(
        hidden_size=int(geometry_payload.get("hidden_size", payload.get("hidden_size", 4096))),
        num_layers=int(geometry_payload.get("num_layers", payload.get("num_layers", 32))),
        target_matrices_per_layer=int(geometry_payload.get("target_matrices_per_layer", payload.get("target_matrices_per_layer", 4))),
        rank=int(geometry_payload.get("rank", payload.get("rank", 16))),
        include_bias_params=bool(geometry_payload.get("include_bias_params", payload.get("include_bias_params", False))),
    )
    cfg = TrainingCapacityConfig(
        base_model_params_b=float(payload.get("base_model_params_b", 7.0)),
        quantization_bits=int(payload.get("quantization_bits", 4)),
        precision=str(payload.get("precision", "bf16")),
        optimizer=str(payload.get("optimizer", "adamw_8bit")),
        gpu_vram_gb=float(payload["gpu_vram_gb"]) if payload.get("gpu_vram_gb") is not None else None,
        activation_overhead_gb=float(payload.get("activation_overhead_gb", 2.0)),
        safety_margin=float(payload.get("safety_margin", 0.88)),
        domains=list(payload.get("domains", ["algebra", "analysis", "logic", "topology"])),
        subfields_per_domain=int(payload.get("subfields_per_domain", 6)),
        arms_per_subfield=int(payload.get("arms_per_subfield", 12)),
        min_events_per_arm=int(payload.get("min_events_per_arm", 30)),
        target_policy_versions=int(payload.get("target_policy_versions", 3)),
        adapter_geometry=geometry,
    )
    return capacity_plan_from_config(cfg)


def capacity_plan_from_config(cfg: TrainingCapacityConfig) -> CapacityPlan:
    base_gb = estimate_base_model_storage_gb(cfg.base_model_params_b, cfg.quantization_bits)
    trainable_params = cfg.adapter_geometry.trainable_params
    trainable_gb = estimate_trainable_memory_gb(trainable_params, cfg.precision, cfg.optimizer)
    total_gb = round(base_gb + trainable_gb + cfg.activation_overhead_gb, 3)
    fits = None if cfg.gpu_vram_gb is None else total_gb <= cfg.gpu_vram_gb * cfg.safety_margin
    rank_schedule = make_rank_schedule(cfg)
    recommended_rank = recommend_rank(cfg, rank_schedule)
    domain_count = max(len(cfg.domains), 1)
    subfield_count = domain_count * max(cfg.subfields_per_domain, 1)
    arm_count = subfield_count * max(cfg.arms_per_subfield, 1)
    events_per_policy = arm_count * max(cfg.min_events_per_arm, 1)
    policy_event_capacity = {
        "domain_count": domain_count,
        "estimated_subfield_count": subfield_count,
        "arms_per_subfield": cfg.arms_per_subfield,
        "policy_arms": arm_count,
        "min_events_per_arm": cfg.min_events_per_arm,
        "min_events_for_one_stable_policy": events_per_policy,
        "target_policy_versions": cfg.target_policy_versions,
        "target_total_events": events_per_policy * max(cfg.target_policy_versions, 1),
    }
    recommendations = [
        "Keep this as an offline planner until a buyer provides trainer, model, data, and infra.",
        f"Use rank {recommended_rank} as the first adapter sweep point for this hardware/model profile.",
        "Record outcomes with company_id/model/domain/subfield so policy learning can specialize without storing raw proofs.",
        "Promote policy arms only after drift_escape_count is zero for the candidate arm.",
    ]
    if fits is False:
        recommendations.append("Requested VRAM is tight: lower rank, use 8-bit optimizer, reduce target matrices, or add gradient checkpointing before integration.")
    assumptions = [
        "LoRA-style adapter estimate uses 2 * hidden_size * rank trainable parameters per adapted dense matrix.",
        "Base-model storage estimate is quantized-weight storage only; serving/training frameworks may add allocator and KV/cache overhead.",
        "Trainable-memory estimate excludes activation tensors except for the configurable activation_overhead_gb reserve.",
        "No Lean runtime, LLM provider, dataset, or trainer is integrated by this planner.",
    ]
    return CapacityPlan(
        mode="offline_capacity_plan_only",
        base_model_storage_gb=base_gb,
        adapter_trainable_params=trainable_params,
        adapter_trainable_params_m=round(trainable_params / 1_000_000, 3),
        estimated_trainable_memory_gb=trainable_gb,
        estimated_total_training_footprint_gb=total_gb,
        fits_requested_vram=fits,
        recommended_rank=recommended_rank,
        rank_schedule=rank_schedule,
        policy_event_capacity=policy_event_capacity,
        recommendations=recommendations,
        assumptions=assumptions,
    )


def make_rank_schedule(cfg: TrainingCapacityConfig, ranks: list[int] | None = None) -> list[dict[str, Any]]:
    ranks = ranks or [4, 8, 16, 32, 64, 96, 128, 192]
    out = []
    for rank in ranks:
        geom = AdapterGeometry(
            hidden_size=cfg.adapter_geometry.hidden_size,
            num_layers=cfg.adapter_geometry.num_layers,
            target_matrices_per_layer=cfg.adapter_geometry.target_matrices_per_layer,
            rank=rank,
            include_bias_params=cfg.adapter_geometry.include_bias_params,
        )
        trainable = geom.trainable_params
        trainable_gb = estimate_trainable_memory_gb(trainable, cfg.precision, cfg.optimizer)
        total = round(estimate_base_model_storage_gb(cfg.base_model_params_b, cfg.quantization_bits) + trainable_gb + cfg.activation_overhead_gb, 3)
        out.append({
            "rank": rank,
            "trainable_params": trainable,
            "trainable_params_m": round(trainable / 1_000_000, 3),
            "estimated_trainable_memory_gb": trainable_gb,
            "estimated_total_training_footprint_gb": total,
            "fits_requested_vram": None if cfg.gpu_vram_gb is None else total <= cfg.gpu_vram_gb * cfg.safety_margin,
        })
    return out


def recommend_rank(cfg: TrainingCapacityConfig, rank_schedule: list[dict[str, Any]]) -> int:
    if cfg.gpu_vram_gb is None:
        return cfg.adapter_geometry.rank
    fitting = [r for r in rank_schedule if r.get("fits_requested_vram")]
    if not fitting:
        return min(r["rank"] for r in rank_schedule)
    # Choose the largest rank that fits while preserving the requested safety margin.
    return int(max(fitting, key=lambda r: r["rank"])["rank"])


def estimate_base_model_storage_gb(base_model_params_b: float, quantization_bits: int) -> float:
    bytes_total = base_model_params_b * 1_000_000_000 * (quantization_bits / 8.0)
    return round(bytes_total / (1024 ** 3), 3)


def estimate_trainable_memory_gb(trainable_params: int, precision: str, optimizer: str) -> float:
    bytes_per = BYTES_PER_PARAM.get(precision.lower(), 2.0)
    mult = OPTIMIZER_MULTIPLIER.get(optimizer.lower(), OPTIMIZER_MULTIPLIER["adamw_8bit"])
    return round(trainable_params * bytes_per * mult / (1024 ** 3), 3)

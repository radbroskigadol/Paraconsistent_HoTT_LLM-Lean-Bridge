from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class CostEstimate:
    model_id: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    worker_cost_usd: float
    total_cost_usd: float
    notes: list[str]


DEFAULT_PRICE_TABLE = {
    # Placeholder values. Companies should replace with contracted pricing.
    "frontier-model-x": {"input_per_million": 5.0, "output_per_million": 15.0},
    "cheap-repair-model": {"input_per_million": 0.5, "output_per_million": 1.5},
    "unknown_model": {"input_per_million": 0.0, "output_per_million": 0.0},
}


def estimate_cost(payload: dict[str, Any]) -> dict[str, Any]:
    model_id = str(payload.get("model_id", "unknown_model"))
    price_table = payload.get("price_table") or DEFAULT_PRICE_TABLE
    pricing = price_table.get(model_id, price_table.get("unknown_model", {"input_per_million": 0.0, "output_per_million": 0.0}))

    input_tokens = int(payload.get("input_tokens", payload.get("estimated_input_tokens", 0)))
    output_tokens = int(payload.get("output_tokens", payload.get("estimated_output_tokens", 0)))
    worker_ms = int(payload.get("worker_ms", 0))
    worker_hour_cost = float(payload.get("worker_hour_cost_usd", 0.0))

    input_cost = input_tokens / 1_000_000 * float(pricing.get("input_per_million", 0.0))
    output_cost = output_tokens / 1_000_000 * float(pricing.get("output_per_million", 0.0))
    worker_cost = (worker_ms / 1000.0 / 3600.0) * worker_hour_cost
    total = input_cost + output_cost + worker_cost

    return asdict(CostEstimate(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=round(input_cost, 8),
        output_cost_usd=round(output_cost, 8),
        worker_cost_usd=round(worker_cost, 8),
        total_cost_usd=round(total, 8),
        notes=["Pricing table is a deployment-owned configuration. Defaults are placeholders."],
    ))

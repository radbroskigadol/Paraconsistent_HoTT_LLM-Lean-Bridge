from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from collections import defaultdict

from .config import ShadowProofConfig

_REQUEST_COUNTERS: dict[tuple[str, str], int] = defaultdict(int)
_REQUEST_LATENCY_BUCKETS = [50, 100, 250, 500, 1000, 2500, 5000, 10000]
_REQUEST_LATENCY: dict[tuple[str, str, int | str], int] = defaultdict(int)


def record_request_metric(tool: str, status: str, duration_ms: int) -> None:
    tool = str(tool or "unknown")
    status = str(status or "unknown")
    _REQUEST_COUNTERS[(tool, status)] += 1
    placed = False
    for bucket in _REQUEST_LATENCY_BUCKETS:
        if duration_ms <= bucket:
            _REQUEST_LATENCY[(tool, status, bucket)] += 1
            placed = True
    _REQUEST_LATENCY[(tool, status, "+Inf")] += 1
    _REQUEST_LATENCY[(tool, status, "sum")] += int(duration_ms)


def structured_log(**fields: Any) -> None:
    print(json.dumps({"ts": time.time(), **fields}, ensure_ascii=False, default=str), flush=True)


def begin_span(name: str, attributes: dict[str, Any] | None = None):
    """Optional OpenTelemetry hook. Returns a context manager.

    If OpenTelemetry is absent or disabled by deployment, this returns a no-op
    context manager so the core remains dependency-light.
    """
    class _Noop:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
    try:
        from opentelemetry import trace  # type: ignore
        tracer = trace.get_tracer("shadowproof")
        return tracer.start_as_current_span(name, attributes=attributes or {})
    except Exception:
        return _Noop()


@dataclass
class MetricEvent:
    timestamp: float
    tenant_id: str
    event_type: str
    tool: str
    status: str
    elapsed_ms: int | None = None
    model_id: str | None = None
    domain: str | None = None
    estimated_tokens: int | None = None
    repair_turns: int | None = None
    lean_status: str | None = None
    theorem_family: str | None = None
    theorem_drift_blocked: bool | None = None
    false_theorem_drift_escape: bool | None = None
    metadata: dict[str, Any] | None = None


def record_metric(cfg: ShadowProofConfig, event: MetricEvent) -> None:
    if not cfg.metrics_enabled:
        return
    path = Path(cfg.metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")


def record_audit(cfg: ShadowProofConfig, tenant_id: str, action: str, payload: dict[str, Any]) -> None:
    path = Path(cfg.audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "tenant_id": tenant_id,
        "action": action,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def load_metric_events(cfg: ShadowProofConfig, limit: int = 10000) -> list[dict[str, Any]]:
    path = Path(cfg.metrics_path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:]


def metrics_report(cfg: ShadowProofConfig, limit: int = 10000) -> dict[str, Any]:
    rows = load_metric_events(cfg, limit=limit)
    by_tool: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    tokens = []
    turns = []
    drift_escapes = 0
    drift_blocks = 0

    for r in rows:
        by_tool[r.get("tool", "unknown")] = by_tool.get(r.get("tool", "unknown"), 0) + 1
        by_status[r.get("status", "unknown")] = by_status.get(r.get("status", "unknown"), 0) + 1
        if r.get("domain"):
            by_domain[r["domain"]] = by_domain.get(r["domain"], 0) + 1
        if isinstance(r.get("estimated_tokens"), int):
            tokens.append(r["estimated_tokens"])
        if isinstance(r.get("repair_turns"), int):
            turns.append(r["repair_turns"])
        if r.get("false_theorem_drift_escape"):
            drift_escapes += 1
        if r.get("theorem_drift_blocked"):
            drift_blocks += 1

    return {
        "event_count": len(rows),
        "by_tool": by_tool,
        "by_status": by_status,
        "by_domain": by_domain,
        "avg_estimated_tokens": sum(tokens) / len(tokens) if tokens else None,
        "avg_repair_turns": sum(turns) / len(turns) if turns else None,
        "theorem_drift_block_count": drift_blocks,
        "false_theorem_drift_escape_count": drift_escapes,
    }


def prometheus_text(cfg: ShadowProofConfig) -> str:
    report = metrics_report(cfg)
    lines = []
    lines.append("# HELP shadowproof_events_total Total recorded ShadowProof events")
    lines.append("# TYPE shadowproof_events_total counter")
    lines.append(f"shadowproof_events_total {report['event_count']}")
    for tool, count in report["by_tool"].items():
        lines.append(f'shadowproof_tool_events_total{{tool="{escape_label(tool)}"}} {count}')
    for status, count in report["by_status"].items():
        lines.append(f'shadowproof_status_events_total{{status="{escape_label(status)}"}} {count}')
    lines.append(f"shadowproof_theorem_drift_blocks_total {report['theorem_drift_block_count']}")
    lines.append(f"shadowproof_false_theorem_drift_escapes_total {report['false_theorem_drift_escape_count']}")
    if report["avg_estimated_tokens"] is not None:
        lines.append(f"shadowproof_avg_estimated_tokens {report['avg_estimated_tokens']}")
    if report["avg_repair_turns"] is not None:
        lines.append(f"shadowproof_avg_repair_turns {report['avg_repair_turns']}")
    lines.append("# HELP shadowproof_http_requests_total Total HTTP tool requests observed in-process")
    lines.append("# TYPE shadowproof_http_requests_total counter")
    for (tool, status), count in sorted(_REQUEST_COUNTERS.items()):
        lines.append(f'shadowproof_http_requests_total{{tool="{escape_label(tool)}",status="{escape_label(status)}"}} {count}')
    lines.append("# HELP shadowproof_http_request_duration_ms HTTP tool request latency histogram in milliseconds")
    lines.append("# TYPE shadowproof_http_request_duration_ms histogram")
    for (tool, status, bucket), count in sorted(_REQUEST_LATENCY.items(), key=lambda x: (str(x[0][0]), str(x[0][1]), str(x[0][2]))):
        if bucket == "sum":
            lines.append(f'shadowproof_http_request_duration_ms_sum{{tool="{escape_label(tool)}",status="{escape_label(status)}"}} {count}')
        else:
            lines.append(f'shadowproof_http_request_duration_ms_bucket{{tool="{escape_label(tool)}",status="{escape_label(status)}",le="{bucket}"}} {count}')
    return "\n".join(lines) + "\n"


def escape_label(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AdapterCapability:
    name: str
    status: str  # available | scaffolded | external_required
    description: str
    config_keys: list[str]


class ModelProviderAdapter(Protocol):
    name: str
    def complete(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class StorageBackend(Protocol):
    name: str
    def put_json(self, tenant_id: str, key: str, value: dict[str, Any]) -> dict[str, Any]: ...
    def get_json(self, tenant_id: str, key: str) -> dict[str, Any] | None: ...
    def delete_prefix(self, tenant_id: str, prefix: str) -> dict[str, Any]: ...


class RetrievalBackend(Protocol):
    name: str
    def search(self, query: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class LocalJSONLStorageBackend:
    name = "local_jsonl"

    def __init__(self, base_dir: str = ".shadowproof_data/adapters"):
        self.base_dir = Path(base_dir)

    def put_json(self, tenant_id: str, key: str, value: dict[str, Any]) -> dict[str, Any]:
        path = self.base_dir / safe(tenant_id) / f"{safe(key)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return {"status": "ok", "backend": self.name, "path": str(path)}

    def get_json(self, tenant_id: str, key: str) -> dict[str, Any] | None:
        path = self.base_dir / safe(tenant_id) / f"{safe(key)}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_prefix(self, tenant_id: str, prefix: str) -> dict[str, Any]:
        base = self.base_dir / safe(tenant_id)
        removed = 0
        if base.exists():
            for p in base.glob(f"{safe(prefix)}*"):
                if p.is_file():
                    p.unlink()
                    removed += 1
        return {"status": "ok", "backend": self.name, "removed": removed}


class ExternalBackendPlaceholder:
    """
    Placeholder for Redis/Postgres/S3/vector DB/model provider adapters.

    It intentionally returns `external_required` rather than pretending to connect.
    Companies can implement the Protocols above and register their adapters.
    """
    def __init__(self, name: str, required_config: list[str]):
        self.name = name
        self.required_config = required_config

    def status(self) -> dict[str, Any]:
        return {
            "status": "external_required",
            "backend": self.name,
            "required_config": self.required_config,
            "message": f"{self.name} adapter is a scaffold; provide company implementation.",
        }


def adapter_catalog() -> dict[str, Any]:
    return {
        "model_providers": [
            asdict(AdapterCapability("frontier_http", "scaffolded", "Generic HTTP model-provider adapter surface.", ["SHADOWPROOF_MODEL_PROVIDER_URL", "SHADOWPROOF_MODEL_PROVIDER_API_KEY"])),
            asdict(AdapterCapability("openai_responses", "external_required", "OpenAI Responses/Tools adapter should be implemented by deployment owner.", ["OPENAI_API_KEY"])),
            asdict(AdapterCapability("anthropic_messages", "external_required", "Anthropic-compatible adapter surface.", ["ANTHROPIC_API_KEY"])),
            asdict(AdapterCapability("local_mock", "available", "Local mock adapter for tests.", [])),
        ],
        "storage_backends": [
            asdict(AdapterCapability("local_jsonl", "available", "Local file-backed JSON storage for dev/test.", ["SHADOWPROOF_DATA_DIR"])),
            asdict(AdapterCapability("postgres", "external_required", "Production relational storage adapter.", ["DATABASE_URL"])),
            asdict(AdapterCapability("s3", "external_required", "Object storage adapter for packets/certificates/artifacts.", ["S3_BUCKET", "AWS_REGION"])),
        ],
        "quota_backends": [
            asdict(AdapterCapability("memory", "available", "In-process rate limiter for development.", [])),
            asdict(AdapterCapability("redis", "external_required", "Distributed quota/rate-limit backend.", ["REDIS_URL"])),
        ],
        "retrieval_backends": [
            asdict(AdapterCapability("lexical", "available", "Built-in domain-pack/JSONL lexical retrieval.", ["SHADOWPROOF_DOMAIN_DIRS"])),
            asdict(AdapterCapability("vector_http", "scaffolded", "HTTP vector retrieval adapter surface.", ["SHADOWPROOF_VECTOR_RETRIEVAL_URL"])),
            asdict(AdapterCapability("company_custom", "external_required", "Company-specific Mathlib/private-library retrieval.", ["CUSTOM_RETRIEVAL_CONFIG"])),
        ],
    }


def safe(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:180]

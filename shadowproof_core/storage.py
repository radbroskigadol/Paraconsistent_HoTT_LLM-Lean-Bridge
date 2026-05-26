from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import ShadowProofConfig


class StorageBackend(Protocol):
    name: str

    def store_event(self, tenant_id: str, category: str, payload: dict[str, Any]) -> Any: ...
    def retention_sweep(self) -> dict[str, Any]: ...
    def health_check(self) -> dict[str, Any]: ...


_TENANT_DIR_ILLEGAL = frozenset({"", ".", "..", "/"})


def _safe_tenant_segment(tenant_id: str) -> str:
    """Map a tenant id to a single safe path segment.

    The legacy implementation used ``re.sub(r"[^A-Za-z0-9_.-]+", "_", ...)``
    which let dots through, so ``tenant_id=".."`` produced the literal ``..``
    segment and the resulting path escaped the tenants/ directory.  We strip
    leading/trailing dots and refuse any value that is structurally a
    parent-directory reference.
    """
    if not isinstance(tenant_id, str):
        raise ValueError("tenant_id must be a string")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", tenant_id).strip(".")
    if not cleaned or cleaned in _TENANT_DIR_ILLEGAL or set(cleaned) <= {".", "_", "-"}:
        raise ValueError(f"refusing path-unsafe tenant_id: {tenant_id!r}")
    return cleaned


def tenant_dir(cfg: ShadowProofConfig, tenant_id: str) -> Path:
    safe = _safe_tenant_segment(tenant_id)
    base = Path(cfg.data_dir).resolve() / "tenants"
    base.mkdir(parents=True, exist_ok=True)
    target = (base / safe).resolve()
    # Defence in depth: even after _safe_tenant_segment, double-check that the
    # resolved path is strictly inside the tenants/ directory.
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"tenant directory {target} escapes tenants root {base}") from exc
    target.mkdir(parents=True, exist_ok=True)
    return target


@dataclass
class JsonlStorageBackend:
    cfg: ShadowProofConfig
    name: str = "jsonl"

    def store_event(self, tenant_id: str, category: str, payload: dict[str, Any]) -> Path:
        path = tenant_dir(self.cfg, tenant_id) / f"{category}.jsonl"
        record = privacy_filter(payload, self.cfg.privacy_mode)
        record["_stored_at"] = time.time()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    def retention_sweep(self) -> dict[str, Any]:
        cutoff = time.time() - self.cfg.retention_days * 86400
        base = Path(self.cfg.data_dir)
        removed = 0
        scanned = 0
        if not base.exists():
            return {"status": "ok", "backend": self.name, "scanned": 0, "removed": 0, "cutoff": cutoff}
        for p in base.rglob("*.jsonl"):
            scanned += 1
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except Exception:
                continue
        return {"status": "ok", "backend": self.name, "scanned": scanned, "removed": removed, "cutoff": cutoff, "retention_days": self.cfg.retention_days}

    def health_check(self) -> dict[str, Any]:
        try:
            base = Path(self.cfg.data_dir)
            base.mkdir(parents=True, exist_ok=True)
            p = base / ".storage_health"
            p.write_text("ok", encoding="utf-8")
            p.unlink(missing_ok=True)
            return {"name": "storage", "backend": self.name, "status": "ok", "detail": str(base)}
        except Exception as e:
            return {"name": "storage", "backend": self.name, "status": "fail", "detail": str(e)}


@dataclass
class PostgresStorageBackend:
    """Production storage adapter scaffold.

    This backend intentionally imports psycopg lazily so the demo package keeps
    zero required third-party dependencies.  In production install
    shadowproof-bridge[prod] and set SHADOWPROOF_STORAGE_BACKEND=postgres plus
    SHADOWPROOF_POSTGRES_DSN.
    """

    cfg: ShadowProofConfig
    name: str = "postgres"

    def _connect(self):
        if not self.cfg.postgres_dsn:
            raise RuntimeError("SHADOWPROOF_POSTGRES_DSN is required for postgres storage")
        try:
            import psycopg  # type: ignore
        except Exception as e:  # pragma: no cover - depends on optional prod extra
            raise RuntimeError("psycopg is not installed; install shadowproof-bridge[prod]") from e
        return psycopg.connect(self.cfg.postgres_dsn)

    def migrate(self) -> None:
        ddl = """
        create table if not exists shadowproof_events (
          id bigserial primary key,
          tenant_id text not null,
          category text not null,
          payload jsonb not null,
          stored_at timestamptz not null default now()
        );
        create index if not exists shadowproof_events_tenant_stored_idx
          on shadowproof_events (tenant_id, stored_at desc);
        create table if not exists shadowproof_audit_events (
          id bigserial primary key,
          tenant_id text not null,
          action text not null,
          payload jsonb not null,
          prev_hash text,
          event_hash text not null,
          stored_at timestamptz not null default now()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)

    def store_event(self, tenant_id: str, category: str, payload: dict[str, Any]) -> str:
        record = privacy_filter(payload, self.cfg.privacy_mode)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into shadowproof_events (tenant_id, category, payload) values (%s, %s, %s::jsonb) returning id",
                    (tenant_id, category, json.dumps(record, ensure_ascii=False, default=str)),
                )
                row = cur.fetchone()
        return f"postgres://shadowproof_events/{row[0] if row else 'unknown'}"

    def retention_sweep(self) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from shadowproof_events where stored_at < now() - (%s || ' days')::interval", (self.cfg.retention_days,))
                removed = cur.rowcount
        return {"status": "ok", "backend": self.name, "removed": removed, "retention_days": self.cfg.retention_days}

    def health_check(self) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("select 1")
                    cur.fetchone()
            return {"name": "storage", "backend": self.name, "status": "ok", "detail": "postgres select 1 ok"}
        except Exception as e:
            return {"name": "storage", "backend": self.name, "status": "fail", "detail": str(e)}


def get_storage_backend(cfg: ShadowProofConfig) -> StorageBackend:
    if str(cfg.storage_backend).lower() == "postgres":
        return PostgresStorageBackend(cfg)
    return JsonlStorageBackend(cfg)


def store_event(cfg: ShadowProofConfig, tenant_id: str, category: str, payload: dict[str, Any]) -> Any:
    return get_storage_backend(cfg).store_event(tenant_id, category, payload)


def retention_sweep(cfg: ShadowProofConfig) -> dict[str, Any]:
    return get_storage_backend(cfg).retention_sweep()


def storage_health_check(cfg: ShadowProofConfig) -> dict[str, Any]:
    return get_storage_backend(cfg).health_check()


def privacy_filter(payload: Any, mode: str) -> Any:
    if mode == "raw_local":
        return payload
    if mode == "redacted":
        return redact(payload)
    return hash_only(payload)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL]", value)
        s = re.sub(r"/(?:[\w.-]+/)+[\w.-]+", "[PATH]", s)
        s = re.sub(r"\b[A-Fa-f0-9]{16,}\b", "[HASH]", s)
        return s[:5000]
    return value


def hash_only(value: Any) -> dict[str, Any]:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "privacy_mode": "hash_only",
        "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "approx_bytes": len(blob.encode("utf-8")),
        "top_level_keys": sorted(list(value.keys())) if isinstance(value, dict) else [],
    }

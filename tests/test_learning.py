"""Learning-layer tests, including the LEARN-1 fix that tenant-scopes
rejection memory by default and stamps every record with a tenant_id.
"""
import json

from shadowproof_core.learning import (
    LearningConfig,
    RejectionMemory,
    make_rejection_record,
    resolve_memory_path,
)


def test_rejection_record_stores_tenant_id(tmp_path):
    cfg = LearningConfig(memory_path=str(tmp_path / "mem.jsonl"),
                         tenant_id="acme")
    record = make_rejection_record({
        "request_id": "r1",
        "theorem_fingerprint": {"theorem_family": "group_assoc"},
        "diagnostics": [{"kind": "unsolved_goal", "severity": "error",
                          "message": "..."}],
        "outcome": "rejected",
        "tenant_id": "acme",
    }, cfg)
    assert record.tenant_id == "acme"


def test_memory_load_filters_by_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    path = tmp_path / "mem.jsonl"
    # Manually write records belonging to two tenants.
    with path.open("w") as f:
        f.write(json.dumps({"timestamp": 1.0, "request_id": "r1",
                            "theorem_family": "fam", "diagnostic_kinds": [],
                            "severity_counts": {}, "error_fingerprints": [],
                            "tenant_id": "acme"}) + "\n")
        f.write(json.dumps({"timestamp": 2.0, "request_id": "r2",
                            "theorem_family": "fam", "diagnostic_kinds": [],
                            "severity_counts": {}, "error_fingerprints": [],
                            "tenant_id": "globex"}) + "\n")
    acme = RejectionMemory(LearningConfig(memory_path=str(path), tenant_id="acme")).load()
    globex = RejectionMemory(LearningConfig(memory_path=str(path), tenant_id="globex")).load()
    assert [r.request_id for r in acme] == ["r1"]
    assert [r.request_id for r in globex] == ["r2"]


def test_memory_load_backwards_compatible_with_records_lacking_tenant_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    path = tmp_path / "mem.jsonl"
    # Old-shape record with no tenant_id field.
    with path.open("w") as f:
        f.write(json.dumps({"timestamp": 1.0, "request_id": "legacy",
                            "theorem_family": "fam", "diagnostic_kinds": [],
                            "severity_counts": {}, "error_fingerprints": []}) + "\n")
    out = RejectionMemory(LearningConfig(memory_path=str(path), tenant_id="acme")).load()
    # Legacy records without tenant_id are treated as belonging to the
    # caller's tenant view for backward compatibility.
    assert len(out) == 1
    assert out[0].request_id == "legacy"


def test_memory_load_tolerates_unknown_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    # If a future writer adds new fields to a record, the older reader
    # should not crash on the unknown keys.
    path = tmp_path / "mem.jsonl"
    with path.open("w") as f:
        f.write(json.dumps({"timestamp": 1.0, "request_id": "r1",
                            "theorem_family": "f", "diagnostic_kinds": [],
                            "severity_counts": {}, "error_fingerprints": [],
                            "future_field_42": "ignored"}) + "\n")
    out = RejectionMemory(LearningConfig(memory_path=str(path))).load()
    assert len(out) == 1


def test_resolve_memory_path_segregates_by_tenant_when_no_override(monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_MEMORY_PATH", raising=False)
    p_acme = resolve_memory_path(None, "acme")
    p_globex = resolve_memory_path(None, "globex")
    p_default = resolve_memory_path(None, None)
    assert "acme" in str(p_acme)
    assert "globex" in str(p_globex)
    # Default (no tenant) remains at the legacy location.
    assert str(p_default).endswith("rejections.jsonl")
    assert "acme" not in str(p_default)


def test_resolve_memory_path_explicit_override_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_MEMORY_PATH", raising=False)
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    explicit = tmp_path / "explicit.jsonl"
    p = resolve_memory_path(str(explicit), "acme")
    assert p == explicit.resolve()


def test_suggest_uses_only_caller_tenant_records(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    path = tmp_path / "mem.jsonl"
    with path.open("w") as f:
        for tenant, family, strategy in [
            ("acme",   "group_assoc", "group_assoc_known_paths"),
            ("acme",   "group_assoc", "group_assoc_known_paths"),
            ("globex", "group_assoc", "secret_globex_strategy"),
        ]:
            f.write(json.dumps({
                "timestamp": 1.0, "request_id": "r",
                "theorem_family": family,
                "diagnostic_kinds": ["unsolved_goal"],
                "severity_counts": {"error": 1},
                "error_fingerprints": [],
                "repair_strategy": strategy,
                "outcome": "accepted",
                "tenant_id": tenant,
            }) + "\n")
    sug_acme = RejectionMemory(
        LearningConfig(memory_path=str(path), tenant_id="acme")
    ).suggest("group_assoc", ["unsolved_goal"])
    strategies = [s.strategy for s in sug_acme]
    # acme must not see globex's private strategy
    assert "secret_globex_strategy" not in strategies

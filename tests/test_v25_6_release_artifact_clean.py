from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from shadowproof_core.bilattice import BilatticeValue, BOTH_L, BOTTOM_L, L_VALUES, NEITHER_L, TOP_L
from shadowproof_core.lean_runner import LeanRunner
from shadowproof_core.model_providers import _validate_provider_url
from shadowproof_core.schema_validation import schema_for_tool, validate_tool_payload


def test_bilattice_rejects_string_truthiness_coordinates():
    with pytest.raises(ValueError, match="JSON boolean"):
        BilatticeValue.from_label({"truth_coordinate": "false", "refutation_coordinate": False})
    with pytest.raises(ValueError, match="JSON boolean"):
        BilatticeValue.from_label({"truth": True, "refutation": "0"})


def test_bilattice_join_absorption_and_demorgan_duality():
    for a in L_VALUES:
        assert a.join(a) == a
        for b in L_VALUES:
            assert a.join(b) == b.join(a)
            assert a.meet(a.join(b)) == a
            assert a.join(a.meet(b)) == a
            assert a.meet(b).involution() == a.involution().join(b.involution())
            assert a.join(b).involution() == a.involution().meet(b.involution())
            for c in L_VALUES:
                assert a.join(b).join(c) == a.join(b.join(c))


def test_join_truth_order_tables_are_expected():
    assert TOP_L.join(BOTTOM_L) == TOP_L
    assert BOTTOM_L.join(NEITHER_L) == NEITHER_L
    assert BOTTOM_L.join(BOTH_L) == BOTH_L
    assert NEITHER_L.join(BOTH_L) == TOP_L


def test_schema_loader_makes_family_schemas_top_level_strict():
    schema = schema_for_tool("shadowproof_optimize_record")
    assert schema is not None
    assert schema.get("additionalProperties") is False
    errors = validate_tool_payload("shadowproof_optimize_record", {"request_id": "x", "unexpected": True})
    assert errors
    assert any("unexpected" in e or "Additional properties" in e for e in errors)


def test_cli_rejects_schema_invalid_payload_before_dispatch(tmp_path):
    req = tmp_path / "bad.json"
    req.write_text(json.dumps({"request_id": "x", "roots": ["."], "unexpected": True}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "shadowproof_core.cli", "list-domains", str(req)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert "schema_validation_failed" in proc.stdout


def test_model_provider_rechecks_dns_resolution_after_host_validation(monkeypatch):
    def fake_getaddrinfo(host, port, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    err = _validate_provider_url("https://model.example/v1")
    assert err is not None
    assert "forbidden IP" in err


def test_model_provider_dns_resolution_failure_is_fail_closed(monkeypatch):
    def fake_getaddrinfo(host, port, type=0):
        raise socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    err = _validate_provider_url("https://missing.example/v1")
    assert err is not None
    assert "DNS resolution failed closed" in err


def test_lean_runner_bounds_stdout_without_memory_capture(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_LEAN_OUTPUT_MAX_BYTES", "512")
    runner = LeanRunner(command=f'{sys.executable} -c "import sys; sys.stdout.write(\'x\'*4096)"', timeout_seconds=5)
    result = runner.check_code("theorem t : True := trivial")
    assert len(result.stdout.encode("utf-8")) <= 1024
    assert "output truncated" in result.stdout

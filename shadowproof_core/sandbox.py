from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from .config import ShadowProofConfig
from .io_limits import capped_read_bytes, read_text_file_capped


@dataclass
class LeanWorkerResult:
    status: str
    lean_status: str
    stdout: str
    stderr: str
    elapsed_ms: int
    exit_code: int | None
    worker_mode: str
    diagnostics: list[dict[str, Any]]


def run_lean_worker(code: str, cfg: ShadowProofConfig, request_id: str = "lean-worker") -> LeanWorkerResult:
    if cfg.lean_worker_mode == "disabled":
        return LeanWorkerResult("unchecked", "not_available", "", "Lean worker disabled", 0, None, "disabled", [])

    if cfg.lean_worker_mode == "http":
        return run_lean_worker_http(code, cfg, request_id)

    return run_lean_worker_local(code, cfg, request_id)


def run_lean_worker_local(code: str, cfg: ShadowProofConfig, request_id: str) -> LeanWorkerResult:
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="shadowproof_lean_") as td:
        path = Path(td) / "Main.lean"
        path.write_text(code, encoding="utf-8")
        cmd = shlex.split(cfg.lean_command) + [str(path)]
        try:
            out_path = Path(td) / "stdout.txt"
            err_path = Path(td) / "stderr.txt"
            with out_path.open("wb") as out_f, err_path.open("wb") as err_f:
                proc = subprocess.run(
                    cmd,
                    cwd=td,
                    stdout=out_f,
                    stderr=err_f,
                    timeout=cfg.lean_timeout_seconds,
                )
            elapsed = int((time.monotonic() - start) * 1000)
            stdout = read_text_file_capped(out_path, cfg.lean_output_max_bytes)
            stderr = read_text_file_capped(err_path, cfg.lean_output_max_bytes)
            lean_status = "accepted" if proc.returncode == 0 else "rejected"
            return LeanWorkerResult(
                status="ok" if proc.returncode == 0 else "needs_repair",
                lean_status=lean_status,
                stdout=stdout,
                stderr=stderr,
                elapsed_ms=elapsed,
                exit_code=proc.returncode,
                worker_mode="local",
                diagnostics=parse_basic_lean_diagnostics(stderr),
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - start) * 1000)
            stdout = read_text_file_capped(Path(td) / "stdout.txt", cfg.lean_output_max_bytes) if (Path(td) / "stdout.txt").exists() else ""
            stderr = read_text_file_capped(Path(td) / "stderr.txt", cfg.lean_output_max_bytes) if (Path(td) / "stderr.txt").exists() else ""
            return LeanWorkerResult("timeout", "timeout", stdout, stderr, elapsed, None, "local", [
                {"severity": "error", "kind": "timeout", "message": f"Lean timed out after {cfg.lean_timeout_seconds}s"}
            ])
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return LeanWorkerResult("unchecked", "not_available", "", str(e), elapsed, None, "local", [
                {"severity": "error", "kind": "lean_not_available", "message": str(e)}
            ])


def run_lean_worker_http(code: str, cfg: ShadowProofConfig, request_id: str) -> LeanWorkerResult:
    if not cfg.lean_worker_url:
        return LeanWorkerResult("unchecked", "not_available", "", "missing lean_worker_url", 0, None, "http", [])
    start = time.monotonic()
    payload = json.dumps({"request_id": request_id, "code": code, "timeout_seconds": cfg.lean_timeout_seconds}).encode("utf-8")
    req = urlrequest.Request(cfg.lean_worker_url.rstrip("/") + "/check", data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=cfg.lean_timeout_seconds + 5) as resp:
            raw = json.loads(capped_read_bytes(resp, cfg.lean_worker_response_max_bytes).decode("utf-8"))
        elapsed = int((time.monotonic() - start) * 1000)
        return LeanWorkerResult(
            status=raw.get("status", "unknown"),
            lean_status=raw.get("lean_status", "unknown"),
            stdout=raw.get("stdout", ""),
            stderr=raw.get("stderr", ""),
            elapsed_ms=raw.get("elapsed_ms", elapsed),
            exit_code=raw.get("exit_code"),
            worker_mode="http",
            diagnostics=raw.get("diagnostics", []),
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return LeanWorkerResult("unchecked", "not_available", "", str(e), elapsed, None, "http", [
            {"severity": "error", "kind": "lean_worker_http_error", "message": str(e)}
        ])


def parse_basic_lean_diagnostics(stderr: str) -> list[dict[str, Any]]:
    out = []
    for line in stderr.splitlines():
        kind = "unknown_lean_failure"
        low = line.lower()
        if "unknown identifier" in low:
            kind = "unknown_identifier"
        elif "type mismatch" in low:
            kind = "type_mismatch"
        elif "unsolved goals" in low:
            # We deliberately do NOT trigger on the substring "goals" alone:
            # benign Lean output ("no goals", "1 goals accomplished",
            # "subgoals") would otherwise be misclassified as unsolved.
            kind = "unsolved_goal"
        elif "failed to synthesize" in low:
            kind = "missing_typeclass_instance"
        elif "no goals" in low or "goals accomplished" in low:
            # Lean often emits these for *successful* goal completion at a
            # stage where stderr still includes the line; surface as info
            # rather than an error so callers don't misroute on them.
            continue
        out.append({"severity": "error", "kind": kind, "message": line, "source": "lean"})
    return out


def sandbox_check(cfg: ShadowProofConfig) -> dict[str, Any]:
    return {
        "lean_worker_mode": cfg.lean_worker_mode,
        "lean_worker_url": cfg.lean_worker_url,
        "lean_timeout_seconds": cfg.lean_timeout_seconds,
        "lean_memory_mb": cfg.lean_memory_mb,
        "sandbox_network_disabled": cfg.sandbox_network_disabled,
        "notes": [
            "Python cannot enforce cgroups/firecracker isolation by itself.",
            "Production deployments should run workers through Docker/gVisor/Firecracker/Kubernetes with CPU, memory, network, and filesystem controls.",
        ],
    }

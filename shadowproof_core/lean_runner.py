from __future__ import annotations

import os
import signal
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from .diagnostics import parse_lean_output
from .io_limits import read_text_file_capped
from .models import Diagnostic, DiagnosticSeverity, LeanRunResult, LeanStatus, ObstructionKind
from .security import SecurityPolicy


def _env_int(name: str, default: int, *, minimum: int = 1024, maximum: int = 10_000_000) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


class LeanRunner:
    def __init__(
        self,
        command: str | None = None,
        timeout_seconds: int = 30,
        workdir: str | Path | None = None,
        security_policy: SecurityPolicy | None = None,
        output_limit_bytes: int | None = None,
    ):
        self.command = command or os.environ.get("SHADOWPROOF_LEAN_CMD", "lake env lean")
        self.timeout_seconds = timeout_seconds
        self.workdir = Path(workdir).resolve() if workdir else None
        self.security_policy = security_policy or SecurityPolicy()
        self.output_limit_bytes = output_limit_bytes or _env_int("SHADOWPROOF_LEAN_OUTPUT_MAX_BYTES", 200_000)

    def check_code(self, code: str) -> LeanRunResult:
        preflight = self.security_policy.preflight(code)
        if any(d.severity == DiagnosticSeverity.ERROR for d in preflight):
            return LeanRunResult(
                lean_status=LeanStatus.NOT_RUN,
                ok=False,
                diagnostics=preflight,
                stdout="",
                stderr="",
                command=shlex.split(self.command),
            )

        with tempfile.TemporaryDirectory(prefix="shadowproof_bridge_") as d:
            path = Path(d) / "ShadowProofBridge.lean"
            path.write_text(code, encoding="utf-8")
            return self.check_file(path)

    def check_file(self, path: Path) -> LeanRunResult:
        cmd = shlex.split(self.command) + [str(path)]
        start = time.monotonic()
        proc = None
        with tempfile.TemporaryDirectory(prefix="shadowproof_lean_output_") as outdir:
            out_path = Path(outdir) / "stdout.txt"
            err_path = Path(outdir) / "stderr.txt"
            try:
                with out_path.open("wb") as out_f, err_path.open("wb") as err_f:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(self.workdir) if self.workdir else None,
                        stdout=out_f,
                        stderr=err_f,
                        start_new_session=True,
                    )
                    proc.wait(timeout=self.timeout_seconds)
            except FileNotFoundError as e:
                return LeanRunResult(
                    lean_status=LeanStatus.NOT_AVAILABLE,
                    ok=False,
                    stderr=str(e),
                    diagnostics=[Diagnostic(
                        DiagnosticSeverity.ERROR,
                        ObstructionKind.LEAN_NOT_AVAILABLE,
                        str(e),
                        source="lean_runner",
                    )],
                    command=cmd,
                )
            except subprocess.TimeoutExpired:
                if proc is not None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)
                stdout = read_text_file_capped(out_path, self.output_limit_bytes) if out_path.exists() else ""
                stderr = read_text_file_capped(err_path, self.output_limit_bytes) if err_path.exists() else ""
                return LeanRunResult(
                    lean_status=LeanStatus.TIMEOUT,
                    ok=False,
                    stdout=stdout,
                    stderr=stderr,
                    diagnostics=[Diagnostic(
                        DiagnosticSeverity.ERROR,
                        ObstructionKind.TIMEOUT,
                        f"Lean timed out after {self.timeout_seconds} seconds.",
                        source="lean_runner",
                    )],
                    command=cmd,
                )

            stdout = read_text_file_capped(out_path, self.output_limit_bytes)
            stderr = read_text_file_capped(err_path, self.output_limit_bytes)

        elapsed = int((time.monotonic() - start) * 1000)
        result = parse_lean_output(stdout, stderr, proc.returncode if proc is not None else 1, cmd)
        result.elapsed_ms = elapsed
        return result

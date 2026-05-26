from __future__ import annotations

import os
import signal
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from .diagnostics import parse_lean_output
from .models import Diagnostic, DiagnosticSeverity, LeanRunResult, LeanStatus, ObstructionKind
from .security import SecurityPolicy


class LeanRunner:
    def __init__(
        self,
        command: str | None = None,
        timeout_seconds: int = 30,
        workdir: str | Path | None = None,
        security_policy: SecurityPolicy | None = None,
        max_output_bytes: int | None = None,
    ):
        self.command = command or os.environ.get("SHADOWPROOF_LEAN_CMD", "lake env lean")
        self.timeout_seconds = timeout_seconds
        self.workdir = Path(workdir).resolve() if workdir else None
        self.security_policy = security_policy or SecurityPolicy()
        self.max_output_bytes = _bounded_int(
            max_output_bytes if max_output_bytes is not None else os.environ.get("SHADOWPROOF_LEAN_MAX_OUTPUT_BYTES", 1_000_000),
            default=1_000_000,
            minimum=8_192,
            maximum=10_000_000,
        )

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
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.workdir) if self.workdir else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                start_new_session=True,
            )
            stdout, stderr, timed_out, truncated = _communicate_bounded(
                proc,
                timeout_seconds=self.timeout_seconds,
                max_bytes_per_stream=self.max_output_bytes,
            )
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

        if timed_out:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
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

        elapsed = int((time.monotonic() - start) * 1000)
        result = parse_lean_output(stdout, stderr, proc.returncode if proc is not None else 1, cmd)
        result.elapsed_ms = elapsed
        if truncated:
            result.diagnostics.append(Diagnostic(
                DiagnosticSeverity.WARNING,
                ObstructionKind.UNKNOWN_LEAN_FAILURE,
                f"Lean stdout/stderr was truncated to {self.max_output_bytes} bytes per stream.",
                source="lean_runner",
            ))
        return result


def _communicate_bounded(proc: subprocess.Popen[bytes], *, timeout_seconds: int, max_bytes_per_stream: int) -> tuple[str, str, bool, bool]:
    """Communicate with child and retain only capped stdout/stderr.

    This local developer runner truncates retained output so diagnostics and
    API responses cannot grow without bound.  Production deployments should
    still use the isolated Lean worker for OS-level memory/process limits.
    """
    timed_out = False
    try:
        stdout_b, stderr_b = proc.communicate(timeout=max(1, int(timeout_seconds)))
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            stdout_b, stderr_b = proc.communicate(timeout=1)
        except Exception:
            stdout_b, stderr_b = exc.stdout or b"", exc.stderr or b""

    stdout, stdout_truncated = _decode_and_cap(stdout_b or b"", max_output_bytes=max_bytes_per_stream)
    stderr, stderr_truncated = _decode_and_cap(stderr_b or b"", max_output_bytes=max_bytes_per_stream)
    return stdout, stderr, timed_out, stdout_truncated or stderr_truncated


def _decode_and_cap(data: bytes, *, max_output_bytes: int) -> tuple[str, bool]:
    truncated = len(data) > max_output_bytes
    if truncated:
        data = data[:max_output_bytes]
    text = data.decode("utf-8", errors="replace")
    if truncated:
        text += "\n[shadowproof: output truncated]\n"
    return text, truncated


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        out = int(value)  # type: ignore[arg-type]
    except Exception:
        out = default
    return max(minimum, min(maximum, out))

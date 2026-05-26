from __future__ import annotations

import re

from .models import Diagnostic, DiagnosticSeverity, LeanRunResult, LeanStatus, ObstructionKind


def parse_lean_output(stdout: str, stderr: str, return_code: int, command: list[str]) -> LeanRunResult:
    text = "\n".join(x for x in [stdout, stderr] if x)
    diagnostics = parse_diagnostics(text)
    ok = return_code == 0 and not any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics)

    return LeanRunResult(
        lean_status=LeanStatus.ACCEPTED if ok else LeanStatus.REJECTED,
        ok=ok,
        stdout=stdout,
        stderr=stderr,
        diagnostics=diagnostics,
        command=command,
        axiom_report=extract_axiom_report(text),
    )


def parse_diagnostics(text: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    loc_re = re.compile(
        r":(?P<line>\d+):(?P<col>\d+):\s+(?P<sev>error|warning|information):\s+(?P<msg>.*?)(?=\n\S.*?:\d+:\d+:\s+(?:error|warning|information):|\Z)",
        re.S,
    )

    for m in loc_re.finditer(text):
        sev_text = m.group("sev")
        msg = m.group("msg").strip()
        severity = DiagnosticSeverity.ERROR if sev_text == "error" else (
            DiagnosticSeverity.WARNING if sev_text == "warning" else DiagnosticSeverity.INFO
        )
        diagnostics.append(Diagnostic(
            severity=severity,
            kind=classify_lean_message(msg),
            message=msg,
            line=int(m.group("line")),
            column=int(m.group("col")),
            source="lean",
        ))

    if diagnostics:
        return diagnostics

    lower = text.lower()
    if "unknown package" in lower or "unknown module prefix" in lower or "object file" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.MISSING_IMPORT, text.strip(), source="lean"))
    elif "executable file not found" in lower or "no such file or directory" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.LEAN_NOT_AVAILABLE, text.strip(), source="lean"))
    elif "unsolved goals" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.UNSOLVED_GOAL, text.strip(), source="lean"))
    elif "unknown identifier" in lower or "unknown constant" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.UNKNOWN_IDENTIFIER, text.strip(), source="lean"))
    elif "type mismatch" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.TYPE_MISMATCH, text.strip(), source="lean"))
    elif "failed to synthesize" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.MISSING_TYPECLASS_INSTANCE, text.strip(), source="lean"))
    elif "error:" in lower:
        diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.UNKNOWN_LEAN_FAILURE, text.strip(), source="lean"))

    return diagnostics


def classify_lean_message(msg: str) -> ObstructionKind:
    lower = msg.lower()
    if "unsolved goals" in lower:
        return ObstructionKind.UNSOLVED_GOAL
    if "unknown identifier" in lower or "unknown constant" in lower:
        return ObstructionKind.UNKNOWN_IDENTIFIER
    if "type mismatch" in lower:
        return ObstructionKind.TYPE_MISMATCH
    if "failed to synthesize" in lower:
        return ObstructionKind.MISSING_TYPECLASS_INSTANCE
    if "unknown module prefix" in lower or "object file" in lower:
        return ObstructionKind.MISSING_IMPORT
    if "sorryax" in lower:
        return ObstructionKind.SORRY_LEAK
    return ObstructionKind.UNKNOWN_LEAN_FAILURE


def extract_axiom_report(text: str) -> str | None:
    lines = []
    for line in text.splitlines():
        if "depends on axioms" in line or "does not depend on any axioms" in line:
            lines.append(line.strip())
        elif lines and line.strip() and not re.search(r":\d+:\d+:", line):
            lines.append(line.strip())
    return "\n".join(lines) if lines else None

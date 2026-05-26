from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Diagnostic, DiagnosticSeverity, ObstructionKind, SecurityLevel
from .lean_text import strip_lean_comments


@dataclass
class SecurityPolicy:
    level: SecurityLevel = SecurityLevel.CONSERVATIVE
    allow_sorry: bool = False
    allow_unsafe: bool = False
    allow_eval: bool = False
    allowed_import_prefixes: tuple[str, ...] = ("Mathlib", "Init", "Std", "Batteries")

    def preflight(self, code: str) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        stripped = strip_comments(code)

        forbidden_patterns: list[tuple[str, str]] = []

        if not self.allow_sorry:
            forbidden_patterns.append((r"\bsorry\b", "`sorry` is not allowed."))
            forbidden_patterns.append((r"\badmit\b", "`admit` is not allowed."))

        forbidden_patterns.extend([
            (r"^\s*axiom\s+", "Axiom declarations are not allowed."),
            (r"^\s*constant\s+", "Uninterpreted constant declarations are not allowed in conservative mode."),
            (r"^\s*opaque\s+", "Opaque declarations are not allowed in conservative mode."),
        ])

        if not self.allow_unsafe:
            forbidden_patterns.append((r"\bunsafe\b", "`unsafe` is not allowed."))

        if not self.allow_eval:
            forbidden_patterns.extend([
                (r"^\s*#eval\b", "`#eval` is not allowed."),
                (r"\bIO\.", "IO use is not allowed in conservative mode."),
                (r"\bIO\b", "IO use is not allowed in conservative mode."),
                (r"\brun_cmd\b", "`run_cmd` is not allowed."),
                (r"\binitialize\b", "`initialize` is not allowed."),
            ])

        for pattern, msg in forbidden_patterns:
            if re.search(pattern, stripped, flags=re.M):
                diagnostics.append(Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.SECURITY_REJECTION,
                    message=msg,
                    source="security",
                ))

        if self.level == SecurityLevel.CONSERVATIVE:
            for imp in re.finditer(r"^\s*import\s+([A-Za-z0-9_./]+)", stripped, flags=re.M):
                mod = imp.group(1)
                if not mod.startswith(self.allowed_import_prefixes):
                    diagnostics.append(Diagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        kind=ObstructionKind.SECURITY_REJECTION,
                        message=f"Import `{mod}` is outside the conservative allowlist.",
                        source="security",
                    ))

        return diagnostics


def strip_comments(code: str) -> str:
    """Strip Lean comments for policy preflight without regex parsing.

    Delegates to the delimiter-aware scanner in ``lean_text`` so comment
    delimiters inside strings cannot hide live code, and nested Lean block
    comments are handled correctly.
    """
    return strip_lean_comments(code, preserve_layout=True)

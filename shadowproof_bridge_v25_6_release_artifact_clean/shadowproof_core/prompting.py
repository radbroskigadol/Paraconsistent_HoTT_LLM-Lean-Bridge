from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .learning import LearningConfig, RejectionMemory, estimate_tokens, normalize_diagnostic_kinds
from .models import Diagnostic, DiagnosticSeverity, ObstructionKind
from .repair_retrieval import compile_retrieval_augmented_repair_context


def compile_repair_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Produce a compact model-facing repair prompt from a failed validation response.

    This is intentionally not a hidden chain of thought. It is an external repair
    instruction object that can be shown to / consumed by an LLM.
    """
    theorem_fingerprint = payload.get("theorem_fingerprint") or {}
    theorem_family = theorem_fingerprint.get("theorem_family", payload.get("theorem_family", "unknown"))
    diagnostics = payload.get("diagnostics", [])
    kinds = normalize_diagnostic_kinds(diagnostics)
    max_tokens = int(payload.get("max_prompt_tokens", 900))

    config = LearningConfig(
        memory_path=payload.get("memory_path"),
        privacy_mode=payload.get("privacy_mode", "hash_only"),
        enabled=bool(payload.get("learning_enabled", True)),
    )
    suggestions = RejectionMemory(config).suggest(theorem_family, kinds, limit=5)

    compact_diags = compress_diagnostics(diagnostics, max_items=5, max_chars_each=360)

    retrieval_context = None
    if bool(payload.get("auto_retrieve", False)):
        try:
            retrieval_context = compile_retrieval_augmented_repair_context(payload)
        except Exception as e:
            retrieval_context = {
                "prompt_context": f"[retrieval failed: {e}]",
                "retrieval": {"candidates": [], "imports": [], "drift_traps": []},
            }

    required_invariants = [
        "Return only schema-valid DraftProposal JSON.",
        "Preserve theorem_fingerprint exactly unless theorem mutation is explicitly allowed.",
        "Do not use sorry, admit, axiom, unsafe, #eval, or run_cmd.",
        "Prefer changing the proof body before changing imports.",
        "Do not add assumptions or strengthen typeclasses unless the prior response explicitly allowed theorem mutation.",
    ]

    prompt_sections = [
        "You are repairing a Lean 4 DraftProposal rejected by ShadowProof/Lean.",
        "Use the ShadowHoTT state as the control object: preserve truth-lane obligations, eliminate falsity-lane blockers, and resolve boundary-lane obstructions.",
        "",
        "THEOREM FINGERPRINT:",
        json.dumps(theorem_fingerprint, ensure_ascii=False, indent=2),
        "",
        "DIAGNOSTIC SUMMARY:",
        json.dumps(compact_diags, ensure_ascii=False, indent=2),
        "",
        "REPAIR STRATEGIES, RANKED:",
    ]

    for s in suggestions:
        prompt_sections.append(f"{s.rank}. {s.strategy}: {s.template}")

    if retrieval_context:
        prompt_sections.extend([
            "",
            "RETRIEVAL-AUGMENTED CONTEXT:",
            retrieval_context.get("prompt_context", ""),
        ])

    prompt_sections.extend([
        "",
        "INVARIANTS:",
        *[f"- {x}" for x in required_invariants],
        "",
        "OUTPUT:",
        "Return a complete revised DraftProposal JSON object. No prose outside JSON.",
    ])

    prompt = "\n".join(prompt_sections)
    prompt = trim_to_token_budget(prompt, max_tokens)

    out = {
        "status": "ok",
        "theorem_family": theorem_family,
        "diagnostic_kinds": kinds,
        "estimated_prompt_tokens": estimate_tokens(prompt),
        "max_prompt_tokens": max_tokens,
        "suggestions": [asdict(s) for s in suggestions],
        "prompt": prompt,
    }
    if retrieval_context:
        out["retrieval_augmented"] = True
        out["retrieval"] = retrieval_context.get("retrieval")
        out["retrieval_query"] = retrieval_context.get("retrieval_query")
    else:
        out["retrieval_augmented"] = False
    return out


def compress_diagnostics(diagnostics: list[Any], max_items: int = 5, max_chars_each: int = 360) -> list[dict[str, Any]]:
    out = []
    for d in diagnostics[:max_items]:
        if not isinstance(d, dict):
            out.append({"severity": "unknown", "kind": "unknown", "message": str(d)[:max_chars_each]})
            continue
        out.append({
            "severity": d.get("severity", "unknown"),
            "kind": d.get("kind", "unknown"),
            "line": d.get("line"),
            "column": d.get("column"),
            "message": str(d.get("message", ""))[:max_chars_each],
            "source": d.get("source", "unknown"),
        })
    if len(diagnostics) > max_items:
        out.append({
            "severity": "info",
            "kind": "truncated",
            "message": f"{len(diagnostics) - max_items} additional diagnostics omitted for token efficiency.",
        })
    return out


def trim_to_token_budget(prompt: str, max_tokens: int) -> str:
    # Estimate and trim by characters. Conservative enough for compact tool prompts.
    if estimate_tokens(prompt) <= max_tokens:
        return prompt
    approx_chars = max(200, int(max_tokens * 4.0))
    trimmed = prompt[:approx_chars]
    return trimmed + "\n\n[TRIMMED_TO_TOKEN_BUDGET]"

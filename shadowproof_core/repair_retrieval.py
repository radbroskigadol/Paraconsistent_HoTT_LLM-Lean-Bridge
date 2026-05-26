from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from .learning import normalize_diagnostic_kinds
from .retrieval import retrieve_mathlib_context, dataclass_to_jsonable
from .shadowhott import build_shadowhott_state


def extract_repair_query(payload: dict[str, Any]) -> str:
    """
    Build a compact retrieval query from theorem fingerprint, diagnostics, and code.
    """
    fp = payload.get("theorem_fingerprint") or {}
    if not fp and isinstance(payload.get("draft"), dict):
        fp = payload["draft"].get("theorem_fingerprint", {})

    diagnostics = payload.get("diagnostics", []) or []
    final_code = str(payload.get("final_lean_code") or payload.get("lean_code") or "")
    source_theorem = str(fp.get("source_theorem", ""))
    conclusion = str(fp.get("conclusion", ""))
    family = str(fp.get("theorem_family", ""))

    diag_bits = []
    unknowns = []
    goals = []
    for d in diagnostics:
        if not isinstance(d, dict):
            continue
        msg = str(d.get("message", ""))
        kind = str(d.get("kind", ""))
        diag_bits.append(f"{kind}: {msg[:240]}")
        unknowns.extend(extract_unknown_identifiers(msg))
        goals.extend(extract_goal_like_fragments(msg))

    code_symbols = extract_code_symbols(final_code)

    parts = [
        source_theorem,
        conclusion,
        family.replace("_", " "),
        " ".join(unknowns),
        " ".join(goals[:5]),
        " ".join(code_symbols[:20]),
        " ".join(diag_bits[:5]),
    ]
    query = " ".join(p for p in parts if p).strip()
    return re.sub(r"\s+", " ", query)[:2000]


def retrieve_for_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload.get("retrieval_query") or extract_repair_query(payload)
    fp = payload.get("theorem_fingerprint") or {}
    requested_domains = payload.get("domains")
    if not requested_domains and fp.get("theorem_family"):
        requested_domains = infer_domains_from_family(str(fp.get("theorem_family")))

    retrieval_payload = {
        "query": query,
        "domains": requested_domains or [],
        "domain_dirs": payload.get("domain_dirs", ["domains"]),
        "index_paths": payload.get("index_paths", []),
        "limit": int(payload.get("retrieval_limit", payload.get("limit", 8))),
        "include_prompt_context": True,
        "max_prompt_chars": int(payload.get("max_retrieval_prompt_chars", 4500)),
    }
    result = retrieve_mathlib_context(retrieval_payload)
    return {
        "query": query,
        "retrieval_payload": retrieval_payload,
        "retrieval": dataclass_to_jsonable(result),
    }


def compile_retrieval_augmented_repair_context(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = payload.get("diagnostics", []) or []
    fp = payload.get("theorem_fingerprint") or {}
    kinds = normalize_diagnostic_kinds(diagnostics)

    retrieval_result = retrieve_for_diagnostics(payload)

    shadow_state_payload = dict(payload)
    shadow_state_payload["retrieval"] = retrieval_result["retrieval"]
    shadowhott_state = build_shadowhott_state(shadow_state_payload).to_dict()

    compact = {
        "theorem_fingerprint": fp,
        "diagnostic_kinds": kinds,
        "diagnostic_summary": compact_diagnostics(diagnostics),
        "retrieval_query": retrieval_result["query"],
        "retrieval": retrieval_result["retrieval"],
        "shadowhott_state": shadowhott_state,
        "repair_constraints": [
            "Preserve theorem_fingerprint exactly unless theorem mutation is explicitly allowed.",
            "Do not use sorry, admit, axiom, unsafe, #eval, or run_cmd.",
            "Prefer proof-body repair before changing imports.",
            "Use retrieved candidates as suggestions, not as authority.",
            "Return complete DraftProposal JSON only.",
        ],
    }
    compact["prompt_context"] = render_repair_context(compact, max_chars=int(payload.get("max_prompt_chars", 7000)))
    return compact


def render_repair_context(context: dict[str, Any], max_chars: int = 7000) -> str:
    fp = context.get("theorem_fingerprint", {})
    retrieval = context.get("retrieval", {})
    candidates = retrieval.get("candidates", [])
    prompt_parts = []

    prompt_parts.append("RETRIEVAL-AUGMENTED LEAN REPAIR CONTEXT")
    prompt_parts.append("")
    prompt_parts.append("THEOREM FINGERPRINT:")
    prompt_parts.append(json.dumps(fp, indent=2, ensure_ascii=False))
    prompt_parts.append("")
    prompt_parts.append("DIAGNOSTIC SUMMARY:")
    prompt_parts.append(json.dumps(context.get("diagnostic_summary", []), indent=2, ensure_ascii=False))
    prompt_parts.append("")
    if context.get("shadowhott_state"):
        sh = context["shadowhott_state"]
        prompt_parts.append("SHADOWHOTT STATE SUMMARY:")
        prompt_parts.append(json.dumps({
            "state_id": sh.get("state_id"),
            "valuation": sh.get("global_valuation"),
            "verdict": sh.get("verdict"),
            "obstructions": [
                {
                    "id": o.get("id"),
                    "kind": o.get("kind"),
                    "lane": o.get("lane"),
                    "repairability": o.get("repairability"),
                    "blocks_validation": o.get("blocks_validation"),
                    "suggested_patch_kind": o.get("suggested_patch_kind"),
                }
                for o in sh.get("obstructions", [])[:8]
            ],
            "patch_morphisms": sh.get("patch_morphisms", [])[:4],
        }, indent=2, ensure_ascii=False))
        prompt_parts.append("")
    prompt_parts.append(f"RETRIEVAL QUERY: {context.get('retrieval_query', '')}")
    prompt_parts.append("")
    prompt_parts.append("RECOMMENDED IMPORTS:")
    for imp in retrieval.get("imports", [])[:8]:
        prompt_parts.append(f"- {imp}")
    prompt_parts.append("")
    prompt_parts.append("USEFUL TACTICS:")
    for tac in retrieval.get("tactics", [])[:16]:
        prompt_parts.append(f"- {tac}")
    prompt_parts.append("")
    if retrieval.get("drift_traps"):
        prompt_parts.append("THEOREM-DRIFT TRAPS:")
        for trap in retrieval.get("drift_traps", [])[:12]:
            prompt_parts.append(f"- {trap}")
        prompt_parts.append("")
    if retrieval.get("notation_notes"):
        prompt_parts.append("NOTATION NOTES:")
        for note in retrieval.get("notation_notes", [])[:8]:
            prompt_parts.append(f"- {note}")
        prompt_parts.append("")
    if retrieval.get("definition_hints"):
        prompt_parts.append("DEFINITION HINTS:")
        for hint in retrieval.get("definition_hints", [])[:8]:
            prompt_parts.append(f"- {hint}")
        prompt_parts.append("")
    prompt_parts.append("RETRIEVED CANDIDATES:")
    for i, c in enumerate(candidates[:10], 1):
        prompt_parts.append(f"{i}. {c.get('name')} [{c.get('domain')}; {c.get('source')}; score={c.get('score')}]")
        if c.get("statement"):
            prompt_parts.append(f"   pattern: {c.get('statement')}")
        if c.get("use_when"):
            prompt_parts.append(f"   use when: {c.get('use_when')}")
        if c.get("example"):
            ex = str(c.get("example")).replace("\n", "\n   ")
            prompt_parts.append(f"   example: {ex}")
    prompt_parts.append("")
    prompt_parts.append("REPAIR CONSTRAINTS:")
    for c in context.get("repair_constraints", []):
        prompt_parts.append(f"- {c}")
    prompt_parts.append("")
    prompt_parts.append("OUTPUT:")
    prompt_parts.append("Return a complete revised DraftProposal JSON object. No prose outside JSON.")

    text = "\n".join(prompt_parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[TRIMMED_REPAIR_CONTEXT]"
    return text


def compact_diagnostics(diagnostics: list[Any], max_items: int = 6, max_chars_each: int = 420) -> list[dict[str, Any]]:
    out = []
    for d in diagnostics[:max_items]:
        if isinstance(d, dict):
            out.append({
                "severity": d.get("severity", "unknown"),
                "kind": d.get("kind", "unknown"),
                "line": d.get("line"),
                "column": d.get("column"),
                "source": d.get("source", "unknown"),
                "message": str(d.get("message", ""))[:max_chars_each],
            })
        else:
            out.append({"severity": "unknown", "kind": "unknown", "message": str(d)[:max_chars_each]})
    if len(diagnostics) > max_items:
        out.append({"severity": "info", "kind": "truncated", "message": f"{len(diagnostics) - max_items} diagnostics omitted."})
    return out


def extract_unknown_identifiers(message: str) -> list[str]:
    out = []
    patterns = [
        r"Unknown identifier [`']([^`']+)[`']",
        r"unknown identifier [`']([^`']+)[`']",
        r"Unknown constant [`']([^`']+)[`']",
        r"unknown constant [`']([^`']+)[`']",
    ]
    for pat in patterns:
        out.extend(re.findall(pat, message))
    return out


def extract_goal_like_fragments(message: str) -> list[str]:
    # Extract small lines around common Lean goal markers.
    lines = message.splitlines()
    out = []
    for line in lines:
        if "⊢" in line or "⊨" in line or "goal" in line.lower():
            cleaned = re.sub(r"\s+", " ", line).strip()
            if cleaned:
                out.append(cleaned[:240])
    return out


def extract_code_symbols(code: str) -> list[str]:
    names = re.findall(r"\b[A-Za-z_][A-Za-z0-9_'.]*\b", code)
    stop = {
        "import", "theorem", "lemma", "example", "by", "exact", "using", "set_option",
        "Type", "Prop", "where", "class", "structure", "def", "if", "then", "else",
    }
    out = []
    seen = set()
    for n in names:
        if n in stop or len(n) <= 1:
            continue
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def infer_domains_from_family(family: str) -> list[str]:
    f = family.lower()
    if any(x in f for x in ["group", "ring", "monoid", "field", "algebra"]):
        return ["algebra"]
    if any(x in f for x in ["topology", "open", "closed", "compact"]):
        return ["topology"]
    if any(x in f for x in ["continuous", "limit", "deriv", "analysis"]):
        return ["analysis"]
    if any(x in f for x in ["order", "le", "lt", "lattice"]):
        return ["order"]
    if any(x in f for x in ["nat", "int", "prime", "dvd", "number"]):
        return ["number_theory"]
    if any(x in f for x in ["set", "function", "image", "preimage"]):
        return ["sets_functions"]
    if any(x in f for x in ["linear", "module", "matrix"]):
        return ["linear_algebra"]
    if any(x in f for x in ["category", "functor", "nattrans"]):
        return ["category_theory"]
    if any(x in f for x in ["finset", "combinatorics", "graph"]):
        return ["combinatorics"]
    if any(x in f for x in ["logic", "iff", "implies", "not"]):
        return ["logic"]
    return []

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .path_guard import resolve_under_allowed_root


REQUIRED_PACK_FIELDS = [
    "domain",
    "display_name",
    "imports",
    "common_tactics",
    "theorems",
    "drift_traps",
]


DOMAIN_PACK_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ShadowProofDomainPack",
    "type": "object",
    "required": REQUIRED_PACK_FIELDS,
    "properties": {
        "domain": {"type": "string"},
        "display_name": {"type": "string"},
        "description": {"type": "string"},
        "owner": {"type": "string"},
        "version": {"type": "string"},
        "imports": {"type": "array", "items": {"type": "string"}},
        "common_tactics": {"type": "array", "items": {"type": "string"}},
        "notation_notes": {"type": "array", "items": {"type": "string"}},
        "definition_hints": {"type": "array", "items": {"type": "string"}},
        "retrieval_keywords": {"type": "array", "items": {"type": "string"}},
        "drift_traps": {"type": "array", "items": {"type": "string"}},
        "theorems": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "statement"],
                "properties": {
                    "name": {"type": "string"},
                    "statement": {"type": "string"},
                    "use_when": {"type": "string"},
                    "example": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "import_hint": {"type": "string"},
                    "avoid_when": {"type": "string"},
                    "source": {"type": "string"}
                },
                "additionalProperties": True
            }
        },
        "eval_cases": {"type": "array", "items": {"type": "object"}},
        "metadata": {"type": "object"}
    },
    "additionalProperties": True,
}


@dataclass
class LintFinding:
    severity: str  # error | warning | info
    code: str
    message: str
    path: str


def domain_pack_schema(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "schema": DOMAIN_PACK_SCHEMA}


def create_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    domain = slug(str(payload.get("domain", "company_domain")))
    display_name = str(payload.get("display_name", domain.replace("_", " ").title()))
    owner = str(payload.get("owner", "company"))
    imports = list(payload.get("imports", ["Mathlib"]))
    common_tactics = list(payload.get("common_tactics", ["simp", "simpa", "exact", "rw"]))
    out_path = resolve_under_allowed_root(payload.get("output_path"), default=f"domains/company/{domain}.json", kind="domain pack output_path")

    pack = {
        "domain": domain,
        "display_name": display_name,
        "description": str(payload.get("description", f"Company domain pack for {display_name}.")),
        "owner": owner,
        "version": str(payload.get("version", "0.1.0")),
        "imports": imports,
        "common_tactics": common_tactics,
        "notation_notes": list(payload.get("notation_notes", [])),
        "definition_hints": list(payload.get("definition_hints", [])),
        "retrieval_keywords": list(payload.get("retrieval_keywords", [domain, display_name])),
        "drift_traps": list(payload.get("drift_traps", [
            "Do not strengthen hypotheses without theorem-lock approval.",
            "Do not weaken the conclusion to make the proof easier.",
            "Do not use sorry, admit, axiom, unsafe, #eval, or run_cmd."
        ])),
        "theorems": list(payload.get("theorems", [
            {
                "name": "example_theorem_name",
                "statement": "Replace with Lean theorem statement/pattern.",
                "use_when": "Replace with retrieval cue.",
                "example": "Replace with minimal Lean usage example.",
                "tags": [domain, "example"],
                "import_hint": imports[0] if imports else "Mathlib",
                "source": "company_authored"
            }
        ])),
        "eval_cases": list(payload.get("eval_cases", [])),
        "metadata": {
            "created_at": time.time(),
            "created_by": "shadowproof_domain_authoring",
            "notes": "Edit this pack, then run validate-domain-pack and domain-pack-eval-stub."
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "output_path": str(out_path), "pack": pack}


def load_pack_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if "pack" in payload and isinstance(payload["pack"], dict):
        return payload["pack"], "<inline>"
    raw_path = payload.get("path", payload.get("pack_path"))
    if not raw_path:
        raise ValueError("Provide `pack` or `path`.")
    path = resolve_under_allowed_root(raw_path, must_exist=True, kind="domain pack path")
    return json.loads(path.read_text(encoding="utf-8")), str(path)


def validate_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    pack, source = load_pack_from_payload(payload)
    findings = lint_domain_pack_object(pack)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    return {
        "status": "ok" if not errors else "rejected",
        "source": source,
        "domain": pack.get("domain"),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "findings": [asdict(f) for f in findings],
    }


def lint_domain_pack_object(pack: dict[str, Any]) -> list[LintFinding]:
    findings: list[LintFinding] = []

    for field in REQUIRED_PACK_FIELDS:
        if field not in pack:
            findings.append(LintFinding("error", "missing_required_field", f"Missing required field `{field}`.", f"/{field}"))

    domain = str(pack.get("domain", ""))
    if domain and slug(domain) != domain:
        findings.append(LintFinding("warning", "domain_not_slug", f"Domain should be slug-like: `{slug(domain)}`.", "/domain"))

    imports = pack.get("imports", [])
    if not isinstance(imports, list) or not imports:
        findings.append(LintFinding("error", "imports_empty", "`imports` must be a non-empty list.", "/imports"))
    elif not any(str(x).startswith(("Mathlib", "Init", "Std", "Batteries")) for x in imports):
        findings.append(LintFinding("warning", "no_standard_import", "No standard Lean/Mathlib import hint found.", "/imports"))

    tactics = pack.get("common_tactics", [])
    if not isinstance(tactics, list) or not tactics:
        findings.append(LintFinding("warning", "common_tactics_empty", "`common_tactics` should list common tactics.", "/common_tactics"))

    traps = pack.get("drift_traps", [])
    if not isinstance(traps, list) or len(traps) < 2:
        findings.append(LintFinding("warning", "few_drift_traps", "Add at least two theorem-drift traps.", "/drift_traps"))
    else:
        trap_text = " ".join(str(x).lower() for x in traps)
        for word in ["strengthen", "weaken", "sorry", "axiom"]:
            if word not in trap_text:
                findings.append(LintFinding("info", "drift_trap_coverage", f"Consider a drift trap mentioning `{word}`.", "/drift_traps"))

    theorems = pack.get("theorems", [])
    if not isinstance(theorems, list) or not theorems:
        findings.append(LintFinding("error", "theorems_empty", "`theorems` must be a non-empty list.", "/theorems"))
    else:
        seen = set()
        for i, thm in enumerate(theorems):
            path = f"/theorems/{i}"
            if not isinstance(thm, dict):
                findings.append(LintFinding("error", "theorem_not_object", "Each theorem entry must be an object.", path))
                continue
            name = str(thm.get("name", ""))
            if not name:
                findings.append(LintFinding("error", "theorem_missing_name", "Theorem entry missing `name`.", path + "/name"))
            elif name in seen:
                findings.append(LintFinding("warning", "duplicate_theorem_name", f"Duplicate theorem name `{name}`.", path + "/name"))
            seen.add(name)
            if not thm.get("statement"):
                findings.append(LintFinding("error", "theorem_missing_statement", f"Theorem `{name}` missing `statement`.", path + "/statement"))
            if not thm.get("example"):
                findings.append(LintFinding("warning", "theorem_missing_example", f"Theorem `{name}` should include a minimal usage example.", path + "/example"))
            if not thm.get("use_when"):
                findings.append(LintFinding("warning", "theorem_missing_use_when", f"Theorem `{name}` should include `use_when` retrieval cue.", path + "/use_when"))
            if not thm.get("tags"):
                findings.append(LintFinding("warning", "theorem_missing_tags", f"Theorem `{name}` should include tags.", path + "/tags"))

    eval_cases = pack.get("eval_cases", [])
    if not eval_cases:
        findings.append(LintFinding("warning", "eval_cases_empty", "Add eval cases or generate stubs with domain-pack-eval-stub.", "/eval_cases"))

    return findings


def domain_pack_eval_stub(payload: dict[str, Any]) -> dict[str, Any]:
    pack, source = load_pack_from_payload(payload)
    output_path = resolve_under_allowed_root(payload.get("output_path"), default=f"examples/evals/{pack.get('domain', 'domain')}_domain_pack_eval.json", kind="domain pack eval output_path")
    limit = int(payload.get("limit", 25))

    cases = []
    for thm in pack.get("theorems", [])[:limit]:
        if not isinstance(thm, dict):
            continue
        name = thm.get("name", "unknown")
        query = " ".join([
            str(thm.get("use_when", "")),
            str(thm.get("statement", "")),
            " ".join(str(x) for x in thm.get("tags", [])),
        ]).strip()
        cases.append({
            "case_id": f"{pack.get('domain', 'domain')}_{slug(name)}_retrieval",
            "tool": "shadowproof_retrieve_mathlib",
            "input": {
                "query": query or str(name),
                "domains": [pack.get("domain")],
                "domain_dirs": ["domains", "domains/company"],
                "limit": 8,
            },
            "expect_domains": [pack.get("domain")],
            "expect_candidates": [name],
            "expect_drift_traps": [],
        })

    suite = {
        "suite_id": f"{pack.get('domain', 'domain')}_domain_pack_retrieval_eval",
        "source_pack": source,
        "cases": cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "output_path": str(output_path), "case_count": len(cases), "suite": suite}


def domain_pack_authoring_guide(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "guide": {
            "steps": [
                "Create a pack from template or `create-domain-pack`.",
                "Add imports and common tactics.",
                "Add theorem entries with name, statement, use_when, example, tags, and import_hint.",
                "Add theorem-drift traps that forbid common false repairs.",
                "Run `validate-domain-pack`.",
                "Generate retrieval evals with `domain-pack-eval-stub`.",
                "Run regression including the generated eval suite.",
                "Submit pack for domain expert review.",
            ],
            "minimum_quality_bar": [
                "Every theorem has statement/use_when/example/tags.",
                "Pack has at least two drift traps.",
                "Pack has retrieval keywords.",
                "Retrieval eval stubs generated.",
                "Domain expert reviewed false-positive risk.",
            ],
            "anti_patterns": [
                "Adding a theorem name without a usage example.",
                "Using vague tags only.",
                "Omitting theorem-drift traps.",
                "Encoding stronger assumptions than the natural-language theorem permits.",
                "Using pack entries to bypass theorem-lock."
            ],
        },
    }


def slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_") or "domain"

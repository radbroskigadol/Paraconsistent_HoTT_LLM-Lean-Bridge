from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .path_guard import resolve_under_allowed_root
from .schema_validation import strict_bool


DEFAULT_DOMAIN_DIRS = ["domains"]
DEFAULT_INDEX_DIR = "retrieval_index"
DEFAULT_INDEX_FILE = "mathlib_index.jsonl"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_domain_dirs(domain_dirs: list[str] | None = None) -> list[Path]:
    """Resolve caller-supplied domain directories under safe roots.

    All public domain-pack operations share this guard so listing, direct
    retrieval, and Mathlib-context retrieval cannot be pointed at arbitrary
    filesystem locations. Relative paths are resolved against the current
    process root by ``resolve_under_allowed_root``; a package-root fallback is
    allowed only for non-absolute paths and is still root-guarded.
    """
    resolved: list[Path] = []
    for raw in domain_dirs or DEFAULT_DOMAIN_DIRS:
        path = resolve_under_allowed_root(raw, kind="domain_dir")
        if not path.exists():
            raw_path = Path(str(raw))
            if not raw_path.is_absolute():
                package_relative = PROJECT_ROOT / raw_path
                try:
                    path = resolve_under_allowed_root(package_relative, kind="domain_dir")
                except Exception:
                    # Keep the original root-guarded non-existing path so the
                    # caller gets an empty result instead of an escape hatch.
                    path = resolve_under_allowed_root(raw, kind="domain_dir")
        resolved.append(path)
    return resolved


@dataclass
class DomainTheorem:
    name: str
    statement_pattern: str = ""
    use_when: str = ""
    example: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class DomainPack:
    domain: str
    aliases: list[str] = field(default_factory=list)
    subfields: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=lambda: ["Mathlib"])
    common_tactics: list[str] = field(default_factory=list)
    common_theorems: list[DomainTheorem] = field(default_factory=list)
    notation_notes: list[str] = field(default_factory=list)
    definition_hints: list[str] = field(default_factory=list)
    drift_traps: list[str] = field(default_factory=list)
    example_skeletons: list[str] = field(default_factory=list)
    retrieval_keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalCandidate:
    source: str
    domain: str
    name: str
    kind: str
    score: float
    statement: str = ""
    use_when: str = ""
    example: str = ""
    import_hint: str | None = None
    file: str | None = None
    line: int | None = None
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    lsh_bucket: str | None = None
    structure_hash: str | None = None


@dataclass
class RetrievalResult:
    query: str
    detected_domains: list[str]
    candidates: list[RetrievalCandidate]
    imports: list[str]
    tactics: list[str]
    drift_traps: list[str]
    notation_notes: list[str]
    definition_hints: list[str]
    prompt_context: str
    elapsed_ms: int
    retrieval_mode: str = "lexical"
    dependency_graph_summary: dict[str, Any] = field(default_factory=dict)


def list_domain_packs(domain_dirs: list[str] | None = None) -> list[DomainPack]:
    packs = []
    for path in _resolve_domain_dirs(domain_dirs):
        if not path.exists():
            continue
        for file in sorted(path.rglob("*.json")):
            try:
                packs.append(load_domain_pack(file))
            except Exception:
                continue
    return packs


def _domain_theorem_entries(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Return theorem entries in the canonical authoring format.

    v25.4 authoring produced ``theorems[*].statement`` while older retrieval
    packs used ``common_theorems[*].statement_pattern``.  Retrieval now accepts
    both so a pack created by ``shadowproof_create_domain_pack`` is immediately
    usable by ``shadowproof_retrieve_mathlib``.
    """
    out: list[dict[str, Any]] = []
    for key in ("theorems", "common_theorems"):
        value = raw.get(key, [])
        if isinstance(value, list):
            out.extend(t for t in value if isinstance(t, dict))
    return out


def load_domain_pack(path: str | Path) -> DomainPack:
    safe_path = resolve_under_allowed_root(path, must_exist=True, kind="domain pack path")
    raw = json.loads(safe_path.read_text(encoding="utf-8"))
    theorems = [
        DomainTheorem(
            name=str(t.get("name", "")),
            statement_pattern=str(t.get("statement_pattern", t.get("statement", ""))),
            use_when=str(t.get("use_when", "")),
            example=str(t.get("example", "")),
            tags=list(t.get("tags", [])),
        )
        for t in _domain_theorem_entries(raw)
    ]
    return DomainPack(
        domain=str(raw.get("domain", Path(path).stem)),
        aliases=list(raw.get("aliases", [])),
        subfields=list(raw.get("subfields", [])),
        imports=list(raw.get("imports", ["Mathlib"])),
        common_tactics=list(raw.get("common_tactics", [])),
        common_theorems=theorems,
        notation_notes=list(raw.get("notation_notes", [])),
        definition_hints=list(raw.get("definition_hints", [])),
        drift_traps=list(raw.get("drift_traps", [])),
        example_skeletons=list(raw.get("example_skeletons", [])),
        retrieval_keywords=list(raw.get("retrieval_keywords", [])),
        metadata=dict(raw.get("metadata", {})),
    )


def get_domain_pack(domain: str, domain_dirs: list[str] | None = None) -> DomainPack | None:
    norm = normalize(domain)
    for pack in list_domain_packs(domain_dirs):
        keys = [pack.domain] + pack.aliases + pack.subfields
        if norm in {normalize(k) for k in keys}:
            return pack
    return None


def detect_domains(query: str, domain_dirs: list[str] | None = None, limit: int = 3) -> list[str]:
    q_terms = set(tokenize(query))
    scored = []
    for pack in list_domain_packs(domain_dirs):
        terms = set()
        for x in [pack.domain] + pack.aliases + pack.subfields + pack.retrieval_keywords:
            terms.update(tokenize(x))
        for th in pack.common_theorems:
            terms.update(tokenize(th.name))
            terms.update(tokenize(th.statement_pattern))
            terms.update(tokenize(th.use_when))
            terms.update(tokenize(" ".join(th.tags)))
        score = len(q_terms & terms)
        # Mild direct alias boost.
        q_norm = normalize(query)
        if any(normalize(a) in q_norm for a in [pack.domain] + pack.aliases + pack.subfields):
            score += 5
        if score:
            scored.append((score, pack.domain))
    scored.sort(reverse=True)
    return [d for _, d in scored[:limit]]


def retrieve_mathlib_context(payload: dict[str, Any]) -> RetrievalResult:
    start = time.monotonic()
    query = str(payload.get("query", ""))
    requested_domains = list(payload.get("domains", []))
    domain_dirs = [str(p) for p in _resolve_domain_dirs(list(payload.get("domain_dirs", DEFAULT_DOMAIN_DIRS)))]
    index_paths = [str(resolve_under_allowed_root(p, kind="retrieval index_path")) for p in payload.get("index_paths", [])]
    limit = int(payload.get("limit", 12))
    include_prompt_context = bool(payload.get("include_prompt_context", True))

    domains = requested_domains or detect_domains(query, domain_dirs=domain_dirs, limit=3)
    packs = [get_domain_pack(d, domain_dirs=domain_dirs) for d in domains]
    packs = [p for p in packs if p is not None]

    candidates: list[RetrievalCandidate] = []
    for pack in packs:
        candidates.extend(candidates_from_pack(query, pack))

    for index_path in index_paths:
        candidates.extend(candidates_from_index(query, index_path, domains=domains))

    candidates.sort(key=lambda c: c.score, reverse=True)

    # Deduplicate by source/name/file/line
    seen = set()
    deduped = []
    for c in candidates:
        key = (c.source, c.name, c.file, c.line)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    candidates = deduped[:limit]

    imports = unique(x for p in packs for x in p.imports)
    tactics = unique(x for p in packs for x in p.common_tactics)
    drift_traps = unique(x for p in packs for x in p.drift_traps)
    notation_notes = unique(x for p in packs for x in p.notation_notes)
    definition_hints = unique(x for p in packs for x in p.definition_hints)

    result = RetrievalResult(
        query=query,
        detected_domains=[p.domain for p in packs],
        candidates=candidates,
        imports=imports,
        tactics=tactics,
        drift_traps=drift_traps,
        notation_notes=notation_notes,
        definition_hints=definition_hints,
        prompt_context="",
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )
    if include_prompt_context:
        result.prompt_context = compile_formalization_context_text(result, packs, max_chars=int(payload.get("max_prompt_chars", 6000)))
    return result


def candidates_from_pack(query: str, pack: DomainPack) -> list[RetrievalCandidate]:
    q_terms = set(tokenize(query))
    out = []
    for th in pack.common_theorems:
        text = " ".join([th.name, th.statement_pattern, th.use_when, th.example, " ".join(th.tags)])
        score = lexical_score(q_terms, text)
        if normalize(th.name) in normalize(query):
            score += 8
        if score <= 0:
            # include a few generic high-value candidates for detected domain
            score = 0.2
        out.append(RetrievalCandidate(
            source="domain_pack",
            domain=pack.domain,
            name=th.name,
            kind="theorem",
            score=score,
            statement=th.statement_pattern,
            use_when=th.use_when,
            example=th.example,
            import_hint=pack.imports[0] if pack.imports else "Mathlib",
            tags=th.tags,
        ))
    return out


def candidates_from_index(query: str, index_path: str | Path, domains: list[str] | None = None) -> list[RetrievalCandidate]:
    path = resolve_under_allowed_root(index_path, kind="retrieval index_path")
    if not path.exists():
        return []
    q_terms = set(tokenize(query))
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except Exception:
                continue
            text = " ".join(str(raw.get(k, "")) for k in ["name", "statement", "namespace", "file"])
            score = lexical_score(q_terms, text)
            if score <= 0:
                continue
            deps = [str(x) for x in raw.get("dependencies", []) if isinstance(x, str)]
            dep_overlap = q_terms & set(tokenize(" ".join(deps)))
            if dep_overlap:
                score += min(3.0, 0.5 * len(dep_overlap))
            out.append(RetrievalCandidate(
                source="mathlib_index",
                domain=str(raw.get("domain", "unknown")),
                name=str(raw.get("name", "")),
                kind=str(raw.get("kind", "decl")),
                score=score,
                statement=str(raw.get("statement", "")),
                import_hint=str(raw.get("import_hint", "Mathlib")),
                file=raw.get("file"),
                line=raw.get("line"),
                tags=list(raw.get("tags", [])),
                dependencies=deps,
                lsh_bucket=str(raw.get("lsh_bucket")) if raw.get("lsh_bucket") is not None else None,
                structure_hash=str(raw.get("structure_hash")) if raw.get("structure_hash") is not None else None,
            ))
    return out


def compile_formalization_context_text(result: RetrievalResult, packs: list[DomainPack], max_chars: int = 6000) -> str:
    parts = []
    parts.append("MATHLIB / DOMAIN FORMALIZATION CONTEXT")
    parts.append("")
    parts.append(f"Query: {result.query}")
    parts.append(f"Detected domains: {', '.join(result.detected_domains) or 'none'}")
    parts.append("")
    parts.append("Recommended imports:")
    for imp in result.imports[:10]:
        parts.append(f"- {imp}")
    parts.append("")
    parts.append("Useful tactics:")
    for tac in result.tactics[:20]:
        parts.append(f"- {tac}")
    parts.append("")
    if result.notation_notes:
        parts.append("Notation notes:")
        for note in result.notation_notes[:10]:
            parts.append(f"- {note}")
        parts.append("")
    if result.definition_hints:
        parts.append("Definition hints:")
        for hint in result.definition_hints[:10]:
            parts.append(f"- {hint}")
        parts.append("")
    if result.drift_traps:
        parts.append("Theorem-drift traps to avoid:")
        for trap in result.drift_traps[:12]:
            parts.append(f"- {trap}")
        parts.append("")
    parts.append("Retrieved theorem/lemma candidates:")
    for i, c in enumerate(result.candidates[:12], 1):
        parts.append(f"{i}. {c.name} [{c.source}; score={c.score:.2f}]")
        if c.statement:
            parts.append(f"   pattern: {c.statement}")
        if c.use_when:
            parts.append(f"   use when: {c.use_when}")
        if c.example:
            ex = c.example.replace("\n", "\n   ")
            parts.append(f"   example: {ex}")
        if c.import_hint:
            parts.append(f"   import: {c.import_hint}")
    parts.append("")
    parts.append("DraftProposal instruction:")
    parts.append("- Use this context to choose Lean imports, theorem names, tactics, and definitions.")
    parts.append("- Preserve theorem_fingerprint exactly.")
    parts.append("- Do not add assumptions, strengthen typeclasses, use sorry/axiom, or mutate the theorem.")
    parts.append("- Return DraftProposal JSON only.")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[TRIMMED_FORMALIZATION_CONTEXT]"
    return text


def index_mathlib_sources(payload: dict[str, Any]) -> dict[str, Any]:
    source_dirs = [resolve_under_allowed_root(p, must_exist=True, kind="source_dir") for p in payload.get("source_dirs", [])]
    output_path = resolve_under_allowed_root(payload.get("output_path"), default=Path(DEFAULT_INDEX_DIR) / DEFAULT_INDEX_FILE, kind="output_path")
    max_files = int(payload.get("max_files", 5000))
    include_private = strict_bool(payload.get("include_private"), False, field="include_private")
    default_import = str(payload.get("default_import", "Mathlib"))
    build_dependency_graph = strict_bool(payload.get("build_dependency_graph"), False, field="build_dependency_graph")
    lsh_bucket_bits = int(payload.get("lsh_bucket_bits", 16))
    if lsh_bucket_bits < 4 or lsh_bucket_bits > 64:
        raise ValueError("lsh_bucket_bits must be between 4 and 64")

    records = []
    files_scanned = 0
    file_imports: dict[str, list[str]] = {}
    for src in source_dirs:
        if not src.exists():
            continue
        for file in src.rglob("*.lean"):
            if files_scanned >= max_files:
                break
            files_scanned += 1
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            file_imports[str(file)] = extract_imports_from_lean(text)
            records.extend(extract_declarations_from_lean(text, file, default_import=default_import, include_private=include_private, lsh_bucket_bits=lsh_bucket_bits))
        if files_scanned >= max_files:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    result = {
        "status": "ok",
        "output_path": str(output_path),
        "files_scanned": files_scanned,
        "declaration_count": len(records),
        "index_hash": file_hash(output_path),
        "retrieval_features": {
            "lexical": True,
            "dependency_metadata": True,
            "lsh_buckets": True,
            "dense_embeddings": False,
            "tree_sitter_required": False,
        },
    }
    if build_dependency_graph:
        graph_path = output_path.with_suffix(".dependency_graph.json")
        graph = build_dependency_graph_payload(records, file_imports)
        graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
        result["dependency_graph_path"] = str(graph_path)
        result["dependency_node_count"] = len(graph["nodes"])
        result["dependency_edge_count"] = len(graph["edges"])
        result["dependency_graph_hash"] = file_hash(graph_path)
    return result


DECL_RE = re.compile(
    r"^\s*(?P<private>private\s+)?(?P<kind>theorem|lemma|def|abbrev|structure|class|inductive)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)"
    r"(?P<rest>.*?)(?=^\s*(?:private\s+)?(?:theorem|lemma|def|abbrev|structure|class|inductive)\s+|\Z)",
    re.S | re.M,
)


def extract_declarations_from_lean(text: str, file: Path, default_import: str, include_private: bool = False, lsh_bucket_bits: int = 16) -> list[dict[str, Any]]:
    records = []
    for m in DECL_RE.finditer(text):
        if m.group("private") and not include_private:
            continue
        kind = m.group("kind")
        name = m.group("name")
        rest = m.group("rest").strip()
        line = text[:m.start()].count("\n") + 1
        statement = rest.split(":=", 1)[0].strip()
        statement = re.sub(r"\s+", " ", statement)[:500]
        normalized_shape = normalize_declaration_shape(kind, name, statement)
        dependencies = extract_decl_dependencies(statement, name)
        records.append({
            "kind": kind,
            "name": name,
            "statement": statement,
            "file": str(file),
            "line": line,
            "import_hint": default_import,
            "domain": infer_domain_from_path(file),
            "tags": tokenize(name)[:8],
            "dependencies": dependencies,
            "lsh_bucket": lsh_bucket(normalized_shape, bits=lsh_bucket_bits),
            "structure_hash": hashlib.sha256(normalized_shape.encode("utf-8")).hexdigest(),
            "normalized_ast_hint": normalized_shape[:500],
        })
    return records


def extract_imports_from_lean(text: str) -> list[str]:
    imports: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s*import\s+(.+?)\s*$", line)
        if not m:
            continue
        for item in m.group(1).split():
            if re.match(r"^[A-Za-z_][A-Za-z0-9_.']*$", item):
                imports.append(item)
    return unique(imports)


def normalize_declaration_shape(kind: str, name: str, statement: str) -> str:
    """Return a stable, dependency-light structure hint for retrieval LSH.

    This is not a full Lean parser. It intentionally avoids claiming Tree-Sitter
    or elaborator semantics. The goal is a safe pilot hook for sub-quadratic
    candidate bucketing that can later be replaced by a real AST parser.
    """
    masked = re.sub(r"[A-Za-z_][A-Za-z0-9_'.]*", "ID", statement)
    masked = re.sub(r"\d+", "NUM", masked)
    masked = re.sub(r"\s+", " ", masked).strip()
    return f"{kind}:{masked}"


def lsh_bucket(normalized_shape: str, bits: int = 16) -> str:
    digest = hashlib.sha256(normalized_shape.encode("utf-8")).hexdigest()
    hex_chars = max(1, min(16, (bits + 3) // 4))
    return digest[:hex_chars]


def extract_decl_dependencies(statement: str, own_name: str) -> list[str]:
    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_'.]*\b", statement)
    stop = {"theorem", "lemma", "def", "by", "where", "Type", "Prop", "Sort", "fun", "forall", "let", "in"}
    deps: list[str] = []
    seen = set()
    for tok in tokens:
        if tok == own_name or tok in stop or tok[:1].islower():
            continue
        if tok not in seen:
            seen.add(tok)
            deps.append(tok)
    return deps[:64]


def build_dependency_graph_payload(records: list[dict[str, Any]], file_imports: dict[str, list[str]]) -> dict[str, Any]:
    names = {str(r.get("name")) for r in records}
    nodes = []
    edges = []
    for r in records:
        name = str(r.get("name", ""))
        nodes.append({
            "id": name,
            "kind": r.get("kind"),
            "domain": r.get("domain"),
            "file": r.get("file"),
            "line": r.get("line"),
            "lsh_bucket": r.get("lsh_bucket"),
        })
        for dep in r.get("dependencies", []):
            if dep in names:
                edges.append({"source": name, "target": dep, "kind": "declaration_reference"})
        for imp in file_imports.get(str(r.get("file")), []):
            edges.append({"source": name, "target": imp, "kind": "import"})
    return {
        "schema_version": "shadowproof.dependency_graph.v1",
        "nodes": nodes,
        "edges": edges,
        "note": "Lexical dependency graph hook; production GraphRAG may replace this with elaborator/Tree-Sitter-derived edges.",
    }


def infer_domain_from_path(file: Path) -> str:
    parts = [p.lower() for p in file.parts]
    for key in ["algebra", "analysis", "topology", "category", "numbertheory", "combinatorics", "logic", "order", "linearalgebra", "data", "settheory"]:
        if any(key in p for p in parts):
            return key
    return "unknown"


def lexical_score(query_terms: set[str], text: str) -> float:
    terms = tokenize(text)
    if not terms:
        return 0.0
    term_set = set(terms)
    overlap = query_terms & term_set
    score = float(len(overlap))
    # substring and name-ish boosts
    joined = normalize(text)
    for q in query_terms:
        if len(q) >= 4 and q in joined:
            score += 0.5
    return score


def tokenize(s: str) -> list[str]:
    s = s.replace("_", " ")
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9']+|\d+", s)]


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def unique(xs) -> list:
    out = []
    seen = set()
    for x in xs:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dataclass_to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: dataclass_to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [dataclass_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: dataclass_to_jsonable(v) for k, v in obj.items()}
    return obj

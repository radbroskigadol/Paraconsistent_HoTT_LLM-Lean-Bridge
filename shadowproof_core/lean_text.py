from __future__ import annotations

from dataclasses import dataclass


_IDENTIFIER_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_'")
_TOP_LEVEL_DECLARATIONS = (
    "theorem",
    "lemma",
    "def",
    "abbrev",
    "example",
    "instance",
    "structure",
    "class",
    "inductive",
    "namespace",
    "section",
    "end",
    "open",
    "variable",
    "variables",
    "axiom",
    "constant",
    "opaque",
)


@dataclass(frozen=True)
class ProofBodySpan:
    """A source span for a Lean ``:= by`` proof body.

    ``body_start`` points at the ``b`` in the proof-opening ``by`` token.
    ``body_end`` points at the first character after the proof body and before
    any trailer that must be preserved, such as ``#print axioms`` or the next
    top-level declaration.
    """

    assign_start: int
    body_start: int
    body_end: int
    trailer_start: int | None = None


def strip_lean_comments(code: str, *, preserve_layout: bool = True) -> str:
    """Strip Lean line and nested block comments without regex parsing.

    The previous implementation used broad regular expressions.  That is unsafe
    for policy preflight because comment delimiters inside strings can hide live
    code, and Lean block comments can be nested.  This scanner recognizes line
    comments, nested ``/- ... -/`` comments, and ordinary escaped string
    literals.  When ``preserve_layout`` is true, removed comment bytes are
    replaced with spaces while newlines are preserved, keeping source positions
    stable for downstream lightweight scanners.
    """

    out: list[str] = []
    i = 0
    n = len(code)
    state = "normal"
    block_depth = 0

    def blank(ch: str) -> str:
        if not preserve_layout:
            return "" if ch != "\n" else "\n"
        return "\n" if ch == "\n" else " "

    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""

        if state == "normal":
            if ch == '"':
                out.append(ch)
                state = "string"
                i += 1
                continue
            if ch == '-' and nxt == '-':
                out.append(blank(ch))
                out.append(blank(nxt))
                i += 2
                state = "line_comment"
                continue
            if ch == '/' and nxt == '-':
                out.append(blank(ch))
                out.append(blank(nxt))
                i += 2
                state = "block_comment"
                block_depth = 1
                continue
            out.append(ch)
            i += 1
            continue

        if state == "string":
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == '"':
                state = "normal"
            i += 1
            continue

        if state == "line_comment":
            out.append(blank(ch))
            i += 1
            if ch == "\n":
                state = "normal"
            continue

        # Nested block comment.
        if ch == '/' and nxt == '-':
            out.append(blank(ch))
            out.append(blank(nxt))
            i += 2
            block_depth += 1
            continue
        if ch == '-' and nxt == '/':
            out.append(blank(ch))
            out.append(blank(nxt))
            i += 2
            block_depth -= 1
            if block_depth <= 0:
                state = "normal"
            continue
        out.append(blank(ch))
        i += 1

    return "".join(out)


def find_first_by_proof_span(code: str) -> ProofBodySpan | None:
    """Find the first delimiter-aware ``:= by`` proof span in Lean source.

    This is intentionally a small source splitter rather than a Lean parser.  It
    uses a comment-stripped, layout-preserving mask to avoid anchors inside
    comments and strings, then preserves trailers and following declarations.
    """

    masked = _mask_comments_and_strings(code)
    n = len(masked)
    i = 0
    while i < n - 1:
        if masked[i] == ':' and masked[i + 1] == '=':
            j = i + 2
            while j < n and masked[j].isspace():
                j += 1
            if _has_token(masked, j, "by"):
                end, trailer = _proof_body_end(masked, code, j + 2)
                return ProofBodySpan(assign_start=i, body_start=j, body_end=end, trailer_start=trailer)
            i = j + 1
            continue
        i += 1
    return None


def replace_first_by_proof_body(code: str, body: str) -> str | None:
    """Replace the first ``:= by`` proof body while preserving surrounding code."""

    span = find_first_by_proof_span(code)
    if span is None:
        return None
    new_body = body.rstrip()
    suffix = code[span.body_end:]
    if suffix and not suffix.startswith(("\n", " ", "\t")):
        new_body += "\n"
    return code[:span.body_start] + new_body + suffix


def _mask_comments_and_strings(code: str) -> str:
    """Return a same-length search mask that hides comments and strings."""

    commentless = strip_lean_comments(code, preserve_layout=True)
    out: list[str] = []
    i = 0
    n = len(commentless)
    in_string = False
    while i < n:
        ch = commentless[i]
        if not in_string:
            if ch == '"':
                out.append(' ')
                in_string = True
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # Keep newlines visible but hide string contents so anchors inside string
        # literals cannot be treated as source syntax.
        out.append("\n" if ch == "\n" else " ")
        if ch == '\\' and i + 1 < n:
            out.append("\n" if commentless[i + 1] == "\n" else " ")
            i += 2
            continue
        if ch == '"':
            in_string = False
        i += 1
    return "".join(out)


def _has_token(masked: str, pos: int, token: str) -> bool:
    end = pos + len(token)
    if masked[pos:end] != token:
        return False
    before = masked[pos - 1] if pos > 0 else " "
    after = masked[end] if end < len(masked) else " "
    return before not in _IDENTIFIER_CHARS and after not in _IDENTIFIER_CHARS


def _proof_body_end(masked: str, code: str, search_start: int) -> tuple[int, int | None]:
    directive = _find_line_directive(masked, "#print axioms", search_start)
    if directive is not None:
        return _rewind_horizontal_blank_lines(code, directive), directive

    next_decl = _find_next_top_level_declaration(masked, search_start)
    if next_decl is not None:
        return _rewind_horizontal_blank_lines(code, next_decl), next_decl
    return len(code), None


def _find_line_directive(masked: str, directive: str, start: int) -> int | None:
    for line_start, line in _iter_lines_with_offsets(masked, start):
        stripped = line.lstrip()
        col = len(line) - len(stripped)
        if stripped.startswith(directive):
            return line_start + col
    return None


def _find_next_top_level_declaration(masked: str, start: int) -> int | None:
    first = True
    for line_start, line in _iter_lines_with_offsets(masked, start):
        if first:
            first = False
            continue
        if not line or line[0].isspace():
            continue
        stripped = line.rstrip("\n")
        if not stripped.strip():
            continue
        if stripped.startswith("#"):
            return line_start
        for word in _TOP_LEVEL_DECLARATIONS:
            if _has_token(stripped, 0, word):
                return line_start
    return None


def _iter_lines_with_offsets(s: str, start: int):
    line_start = s.rfind("\n", 0, start) + 1
    while line_start < len(s):
        line_end = s.find("\n", line_start)
        if line_end == -1:
            yield line_start, s[line_start:]
            return
        yield line_start, s[line_start:line_end + 1]
        line_start = line_end + 1


def _rewind_horizontal_blank_lines(code: str, idx: int) -> int:
    """Move a trailer boundary back over whitespace after the proof body.

    This preserves the trailer itself while allowing the replacement body to own
    its final line.  The original blank lines before ``#print axioms`` or the
    next declaration remain in the suffix.
    """

    j = idx
    while j > 0 and code[j - 1] in " \t\r\n":
        j -= 1
    return j

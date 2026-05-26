from __future__ import annotations

"""Small Lean lexical helpers used by security and repair code.

These helpers are deliberately not a full Lean parser.  They are a bounded,
delimiter-aware scanner for the pieces this bridge must classify safely before
calling Lean: comments, string/char literals, and proof-body anchors.  The
important property is that comment delimiters appearing inside Lean string or
character literals do not hide real declarations, and nested block comments are
handled the way Lean handles them.
"""


def mask_lean_comments_and_strings(code: str, *, mask_strings: bool = True) -> str:
    """Return ``code`` with comments and optionally literals replaced by spaces.

    Length and newline positions are preserved.  That lets callers run simple
    regular-expression checks on the masked text and then use match offsets
    against the original text without allowing a delimiter inside a string to
    create a fake comment or a fake proof-body anchor.

    Supported lexical forms:
    - line comments: ``-- ...``
    - nested block comments: ``/- ... -/``
    - double-quoted string literals with backslash escapes
    - single-quoted character literals with backslash escapes

    Unterminated block comments/literals are masked through EOF, which is the
    conservative behavior for pre-Lean security checks.
    """
    chars = list(code)
    n = len(chars)
    out = chars[:]
    i = 0
    while i < n:
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < n else ""

        # Lean line comment.  Preserve the newline; mask every other char.
        if ch == "-" and nxt == "-":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n and chars[i] != "\n":
                out[i] = " "
                i += 1
            continue

        # Lean nested block comment.
        if ch == "/" and nxt == "-":
            depth = 1
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n and depth > 0:
                a = chars[i]
                b = chars[i + 1] if i + 1 < n else ""
                if a == "/" and b == "-":
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    depth += 1
                    continue
                if a == "-" and b == "/":
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    depth -= 1
                    continue
                if chars[i] != "\n":
                    out[i] = " "
                i += 1
            continue

        # String literal.  Mask contents by default so security checks do not
        # reject harmless text and do not mistake delimiters inside strings for
        # syntax.  Newlines are preserved even in malformed strings.
        if mask_strings and ch == '"':
            out[i] = " "
            i += 1
            escaped = False
            while i < n:
                c = chars[i]
                if c != "\n":
                    out[i] = " "
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    i += 1
                    break
                i += 1
            continue

        # Character literal.  Lean character syntax is stricter than this, but
        # masking a single-quoted escaped span is enough to avoid false anchors.
        if mask_strings and ch == "'":
            out[i] = " "
            i += 1
            escaped = False
            while i < n:
                c = chars[i]
                if c != "\n":
                    out[i] = " "
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == "'":
                    i += 1
                    break
                i += 1
            continue

        i += 1
    return "".join(out)


def strip_lean_comments_for_policy(code: str) -> str:
    """Compatibility wrapper: remove comments/literal contents for policy scans."""
    return mask_lean_comments_and_strings(code, mask_strings=True)

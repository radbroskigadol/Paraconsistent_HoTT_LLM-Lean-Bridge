from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

TRUNCATION_SUFFIX = "\n[shadowproof: output truncated at {limit} bytes]"


def capped_read_bytes(stream: BinaryIO, limit: int) -> bytes:
    """Read at most ``limit`` bytes from a binary stream and fail if exceeded."""
    if limit <= 0:
        raise ValueError("byte limit must be positive")
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"response exceeded configured limit of {limit} bytes")
    return data


def truncate_text(value: str | bytes | None, limit: int, *, encoding: str = "utf-8") -> str:
    """Return text bounded to ``limit`` UTF-8 bytes with an explicit suffix."""
    if value is None:
        return ""
    raw = value.encode(encoding, errors="replace") if isinstance(value, str) else bytes(value)
    if len(raw) <= limit:
        return raw.decode(encoding, errors="replace")
    suffix = TRUNCATION_SUFFIX.format(limit=limit).encode(encoding)
    keep = max(0, limit - len(suffix))
    return raw[:keep].decode(encoding, errors="replace") + suffix.decode(encoding)


def read_text_file_capped(path: str | Path, limit: int, *, encoding: str = "utf-8") -> str:
    raw = Path(path).read_bytes()
    return truncate_text(raw, limit, encoding=encoding)

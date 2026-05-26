from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '.pytest_cache', '__pycache__', 'node_modules', 'dist', 'build', '.shadowproof_data'}
PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'ghp_[A-Za-z0-9]{20,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(r'(?i)(api[_-]?key|secret|token)\s*=\s*["\'][A-Za-z0-9_\-]{24,}["\']'),
]
ALLOW_SUBSTRINGS = [
    'SHADOWPROOF_MODEL_PROVIDER_BEARER_TOKEN',
    'SHADOWPROOF_BEARER_TOKENS',
    'placeholder',
    '<your-org>',
]

failures: list[str] = []
for path in ROOT.rglob('*'):
    if not path.is_file():
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for i, line in enumerate(text.splitlines(), 1):
        if any(s in line for s in ALLOW_SUBSTRINGS):
            continue
        if any(p.search(line) for p in PATTERNS):
            failures.append(f'{path.relative_to(ROOT)}:{i}: possible secret')
if failures:
    print('\n'.join(failures))
    raise SystemExit(1)
print('secret scan passed')

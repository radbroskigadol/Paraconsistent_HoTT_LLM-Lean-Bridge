# MCP server skeleton

This directory contains a TypeScript skeleton for exposing ShadowProof Bridge as MCP tools.

The Python bridge remains the source of truth. The MCP server shells out to:

```bash
python -m shadowproof_core.cli validate <request.json>
python -m shadowproof_core.cli check <request.json>
```

For production, replace the subprocess bridge with an HTTP call or direct Python service deployment.

OpenAI Apps SDK expects MCP tools with JSON Schema input/output contracts and structured tool results. The schemas are in `../schemas`.

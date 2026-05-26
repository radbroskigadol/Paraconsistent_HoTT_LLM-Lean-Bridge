import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const server = new McpServer({ name: "ShadowProof Lean Bridge", version: "0.25.6" }, { capabilities: { tools: {} } });
function runPythonTool(command, payload) {
    const dir = mkdtempSync(join(tmpdir(), "shadowproof-mcp-"));
    const inputPath = join(dir, "request.json");
    writeFileSync(inputPath, JSON.stringify(payload, null, 2), "utf8");
    const proc = spawnSync("python", ["-m", "shadowproof_core.cli", command, inputPath], {
        encoding: "utf8",
        timeout: Number(process.env.SHADOWPROOF_MCP_TIMEOUT_MS || "45000"),
        maxBuffer: Number(process.env.SHADOWPROOF_MCP_MAX_BUFFER || "1048576")
    });
    rmSync(dir, { recursive: true, force: true });
    if (proc.error) {
        return {
            request_id: "mcp-error",
            tool: command,
            status: "error",
            lean_status: "not_run",
            diagnostics: [{
                    severity: "error",
                    kind: "unknown_lean_failure",
                    message: String(proc.error),
                    source: "mcp"
                }]
        };
    }
    try {
        return JSON.parse(proc.stdout);
    }
    catch {
        return {
            request_id: "mcp-parse-error",
            tool: command,
            status: "error",
            lean_status: "not_run",
            diagnostics: [{
                    severity: "error",
                    kind: "unknown_lean_failure",
                    message: proc.stderr || proc.stdout || "No JSON returned by Python bridge.",
                    source: "mcp"
                }]
        };
    }
}
const AnyPayload = z.record(z.any()).refine((payload) => {
    const target = payload.target;
    return !(target && typeof target === "object" && "lean_command" in target);
}, { message: "target.lean_command is not accepted; configure SHADOWPROOF_LEAN_CMD on the server" });
function textResult(result) {
    return { structuredContent: result, content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
}
server.registerTool("lean_check", { description: "Check a Lean 4 proof attempt and return structured diagnostics.", inputSchema: AnyPayload }, async (args) => textResult(runPythonTool("check", args)));
server.registerTool("shadowproof_validate", { description: "Translate/check an NL or direct Lean proof attempt and return a certificate if Lean accepts.", inputSchema: AnyPayload }, async (args) => textResult(runPythonTool("validate", args)));
server.registerTool("shadowproof_check_draft", { description: "Statically check an LLM DraftProposal before running Lean.", inputSchema: AnyPayload }, async (args) => textResult(runPythonTool("check-draft", args)));
server.registerTool("shadowproof_validate_draft", { description: "Validate an LLM DraftProposal with theorem-lock, security preflight, Lean, and guarded repair.", inputSchema: AnyPayload }, async (args) => textResult(runPythonTool("validate-draft", args)));
const transport = new StdioServerTransport();
await server.connect(transport);

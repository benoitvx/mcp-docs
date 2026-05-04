# Node/TypeScript MCP Server Implementation Guide

## Overview

TypeScript-specific best practices for MCP servers using the MCP TypeScript SDK.

---

## Quick Reference

### Key Imports
```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
```

### Server Initialization
```typescript
const server = new McpServer({ name: "service-mcp-server", version: "1.0.0" });
```

### Tool Registration Pattern
```typescript
server.registerTool(
  "tool_name",
  {
    title: "Tool Display Name",
    description: "What the tool does",
    inputSchema: { param: z.string() },
    outputSchema: { result: z.string() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  async ({ param }) => ({
    content: [{ type: "text", text: JSON.stringify(output) }],
    structuredContent: output
  })
);
```

---

## Server Naming Convention

- **Format**: `{service}-mcp-server` (lowercase with hyphens)
- **Examples**: `github-mcp-server`, `jira-mcp-server`

## Project Structure

```
{service}-mcp-server/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── types.ts
│   ├── tools/
│   ├── services/
│   ├── schemas/
│   └── constants.ts
└── dist/
```

## Tool Implementation with Zod

```typescript
const UserSearchSchema = z.object({
  query: z.string().min(2).max(200).describe("Search string"),
  limit: z.number().int().min(1).max(100).default(20).describe("Max results"),
  offset: z.number().int().min(0).default(0).describe("Pagination offset")
}).strict();

type UserSearchInput = z.infer<typeof UserSearchSchema>;

server.registerTool(
  "example_search_users",
  {
    title: "Search Users",
    description: "Search for users by name or email...",
    inputSchema: UserSearchSchema,
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  async (params: UserSearchInput) => {
    try {
      const data = await makeApiRequest("users/search", "GET", undefined, { q: params.query, limit: params.limit });
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    } catch (error) {
      return { content: [{ type: "text", text: handleApiError(error) }] };
    }
  }
);
```

## Transport Options

```typescript
// stdio (local)
const transport = new StdioServerTransport();
await server.connect(transport);

// Streamable HTTP (remote)
const app = express();
app.post('/mcp', async (req, res) => {
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on('close', () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});
```

## Package Configuration

### package.json
```json
{
  "name": "{service}-mcp-server",
  "version": "1.0.0",
  "type": "module",
  "main": "dist/index.js",
  "scripts": { "start": "node dist/index.js", "build": "tsc", "dev": "tsx watch src/index.ts" },
  "dependencies": { "@modelcontextprotocol/sdk": "^1.6.1", "axios": "^1.7.9", "zod": "^3.23.8" },
  "devDependencies": { "@types/node": "^22.10.0", "tsx": "^4.19.2", "typescript": "^5.7.2" }
}
```

### tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2022", "module": "Node16", "moduleResolution": "Node16",
    "outDir": "./dist", "rootDir": "./src", "strict": true,
    "esModuleInterop": true, "declaration": true, "sourceMap": true
  },
  "include": ["src/**/*"], "exclude": ["node_modules", "dist"]
}
```

## Quality Checklist

- [ ] All tools registered using `registerTool` with title, description, inputSchema, annotations
- [ ] Zod schemas with `.strict()` enforcement
- [ ] No use of `any` type
- [ ] `npm run build` completes successfully
- [ ] Pagination properly implemented
- [ ] Error messages are clear and actionable
- [ ] Common functionality extracted into reusable functions

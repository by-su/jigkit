# MCP server definitions

One file per server: `<server-id>.json`, containing just the server object
(the value side of an `mcpServers` entry).

```json
{ "command": "npx", "args": ["-y", "@some/mcp-server"], "env": {} }
```

A profile opts in by id:

```yaml
mcp: [figma]
```

Profiles that declare nothing get `{"mcpServers":{}}` plus `--strict-mcp-config`,
which makes the session ignore every other MCP configuration.

`example.json` is a working instance of the format. It is also the golden fixture that
keeps this resolution path exercised — no real profile declares an MCP server yet, so
without it the branch would never run. See `profiles/_fixture/profile.yaml`.

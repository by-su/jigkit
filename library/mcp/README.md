# MCP server definitions

Profiles opt in by id:

```yaml
mcp: [playwright-mcp, shadcn]
```

The id comes from the **catalogue** in `library/stacks/` — every entry with
`surface: mcp` is directly enableable, no file needed here. `jig stack list` shows
what exists. A definition lives in one place: copying it here as well is how the two
drift apart.

Profiles that declare nothing get `{"mcpServers":{}}` plus `--strict-mcp-config`,
which makes the session ignore every other MCP configuration.

## This directory is the override

One file per server: `<server-id>.json`, containing just the server object
(the value side of an `mcpServers` entry).

```json
{ "command": "npx", "args": ["-y", "@some/mcp-server"], "env": {} }
```

A file here **wins over the catalogue** for that id. Two reasons to write one:

- a secret that cannot be committed — the catalogue only carries `${VAR}` references
- a server the catalogue does not know about, or one you want launched differently here

Nothing writes here automatically. `jig stack apply` used to scaffold one file per MCP
entry it placed; it no longer does, because a scaffold that wins over the catalogue turns
every later catalogue fix into a silent no-op. What it does instead is **tell you when a
file here diverges from the catalogue** — as does `jig stack check`. An override you meant
is fine; one you forgot is the failure this reports.

`example.json` is a working instance of the format. It is also the golden fixture that
keeps the file branch exercised, while `_fixture` also declares a catalogue-only id so
the fallback branch runs on every `jig golden` — see `profiles/_fixture/profile.yaml`.

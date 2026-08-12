# jigkit

> 한국어: [README.ko.md](README.ko.md)

**A profile harness for AI coding agents.** It swaps the skills, MCP servers,
tools and permissions loaded for each stage of work, so that a growing skill
library does not grow the session.

Named after the woodworking **jig** — the fixture that constrains a tool so it
can only cut where it is supposed to. A jig exists to make the result
repeatable regardless of who is operating. That is what this does to a coding
agent: the rules live in permissions, not in prompts.

Built for Claude Code. Profile content is tool-neutral, so adapters for other
CLIs can be added without rewriting profiles. MIT licensed.

## Why split profiles before the library is big

A skill's *description* is loaded at every session start, whether or not the
skill is used. Only the body is deferred. Measured on Claude Code 2.1.228
([`probe/results/growth.md`](probe/results/growth.md)):

| Skills loaded | Session start tokens | Per skill |
|---:|---:|---:|
| 0 | 12,069 | — |
| 10 | 12,815 | 75 |
| 25 | 13,820 | 70 |
| 50 | 15,495 | 69 |

Linear, at ~70 tokens for a short description and ~161 for a long one. A
profile itself costs 213 tokens. So splitting is roughly free, and not
splitting is linear:

| Library size | Everything loaded | Per-profile (8 skills each) |
|---:|---:|---:|
| 25 | +1.8k – 4.0k | +0.6k – 1.3k |
| 50 | +3.4k – 8.1k | +0.6k – 1.3k |
| 100 | +6.9k – 16.1k | +0.6k – 1.3k |

Below ~25 skills it barely matters. Past 50 it does. The cheap time to split is
before you get there.

**Keep skill descriptions short.** The body is loaded on invocation; the
description is paid by every session, every time.

## Install

```bash
git clone https://github.com/by-su/jigkit ~/jigkit
echo 'export PATH="$HOME/jigkit/bin:$PATH"' >> ~/.zshrc
```

Requires Claude Code, `python3`, and PyYAML.

## Use

```bash
jig list                    # profiles, with skill / agent / MCP counts
jig developer               # start a session in the current directory
jig developer ~/work/proj   # or in a given project
jig build [profile]         # compile profiles into build/claude/<name>/
jig doctor [profile]        # check rules and the handoff graph
jig budget [profile]        # measure session-start tokens against the cap
jig growth 0 10 25 50       # measure the cost curve for N skills
jig golden [--update]       # regression-test the compiler
jig argv developer          # print the launch argv without running it
jig new <name>              # scaffold a profile
```

## How a profile is defined

Two tool-neutral files. Nothing in them is Claude Code syntax.

```
profiles/developer/
├── profile.yaml    inputs, outputs, permissions, skills, MCP, budget, done_when
└── BRIEF.md        sequence, boundaries, latitude
```

Skills, subagents and MCP definitions live once in `library/` and are
referenced by id, so several profiles can share one without copies or symlinks.
`jig build` resolves all of it into `build/claude/<name>/` — a real Claude Code
plugin plus its settings, MCP config and system prompt.

A profile is defined by **what it reads, what it writes, and what it may not
touch** — not by a persona. See
[`PRINCIPLES.md`](PRINCIPLES.md#이-설계에-대한-반론--지우지-않고-남긴다), which
keeps the strongest published objection to this design rather than hiding it.

## Stages and handoff

Work moves between stages as **files**, not as conversation. A stage cannot edit
the previous stage's output, so when it disagrees it has to write the objection
down instead of quietly fixing it.

| Profile | Reads | Writes |
|---|---|---|
| `researcher` | — | `docs/research/{slug}.md` |
| `pm` | research | `docs/prd/{slug}.md` |
| `designer` | prd | `docs/design/{slug}.md` |
| `developer` | design, prd (+review) | `src/**`, `tests/**`, `docs/decisions/{slug}.md` |
| `reviewer` | prd, design (+decisions) | `docs/review/{slug}.md` |

`jig doctor` fails if this chain breaks — if a profile waits on a document
nobody produces, or produces one nobody reads.

### Write permissions are derived, not written by hand

```
deny_write = (every profile's outputs) − (this profile's outputs)
```

Add a sixth profile and the other five are denied its output without editing a
single one of their files. Maintaining that list by hand had already opened
three holes before this was automated.

`permissions.deny_write` in `profile.yaml` is then only for paths **no profile
owns** — for example `.github/**`.

This is a denylist. Files no profile owns (`README.md`, `package.json`) stay
writable by everyone. The goal is keeping stage boundaries, not sandboxing.

## Switching

**Switching happens at process boundaries.** Skills and permissions are bound
when the process starts, and Claude cannot restart itself, so `/profile` inside
a session does not pretend to switch. It checks the current profile's
done-conditions, records state in `.harness/state.json`, and prints the command
to run next.

```
> /profile designer
  ✓ developer done-conditions: 3/4
  ⚠ tests not run
  next: close this session and run  jig designer
```

## What isolation does and does not mean

**Does**, measured ([`probe/results/phase0.md`](probe/results/phase0.md)):

- The session process contains only `core` and the active profile. Other
  profiles' skills are never read, never tokenized, never invocable.
- Bundled skills are off by default (12 skills → 1, about 1,776 tokens).
- Only declared MCP servers load; `--strict-mcp-config` makes the session ignore
  every other MCP configuration.
- Previous stages' documents are denied at the permission layer, not requested
  in a prompt.
- Nothing is written to `~/.claude/settings.json`. Two profiles can run in two
  terminals without touching each other.

**Does not**:

- Filesystem isolation. Broad `Bash` access can route around a deny rule.
- Mid-session switching. Everything is decided at launch.
- Context continuity. A switch starts a fresh conversation — the documents are
  the handoff.

## Adding a profile

```bash
jig new qa
# 1) profiles/qa/profile.yaml  — inputs, outputs, done_when
# 2) profiles/qa/BRIEF.md      — sequence, boundaries, latitude
jig doctor qa
```

No code changes. Profiles are discovered by globbing `profiles/*/profile.yaml`;
there is no registry file to update.

Before adding one, ask whether what you are adding is a **stage** or a **job
title**. If it is a job title, don't.

## Layout

```
PRINCIPLES.md          principles, sources, and what enforces each one
core/                  always loaded: PREAMBLE.md and the /profile skill
library/               skills, agents and MCP definitions, one copy each
profiles/<name>/       profile.yaml + BRIEF.md — the tool-neutral source
adapters/claude/       the only place that knows Claude Code syntax
bin/jig                dispatch only
build/claude/<name>/   compiled output, what --plugin-dir points at (gitignored)
tests/golden/          expected compiler output
probe/results/         measurements, with the commands that produced them
```

## Status

Early. Five profiles work end to end; `library/` is deliberately empty until
repeated work shows what deserves to become a skill. Documentation is Korean
apart from this file, and evals are not written yet.

Claims marked `[M]` were measured on this machine against Claude Code 2.1.228
and record the command that produced them. Claims that could not be verified are
marked `[?]` along with how to settle them.

# Quick start

> 한국어: [ko/QUICK_START.md](ko/QUICK_START.md) · Why it works this way: [README.md](../README.md)

From an empty machine to a running profile session. Everything here is copy-pasteable.

## 1. Requirements

| | Check | If missing |
|---|---|---|
| Claude Code | `claude --version` | https://claude.com/claude-code |
| Python 3 | `python3 --version` | macOS: `brew install python3` |
| PyYAML | `python3 -c 'import yaml'` | `python3 -m pip install --user PyYAML` |
| git | `git --version` | needed to fetch skill sources |

`bootstrap.sh` checks all four and stops before doing anything if one is missing.

## 2. Install

```bash
git clone https://github.com/by-su/jigkit
cd jigkit
./bootstrap.sh --path     # preflight → fetch skills → verify → add PATH
exec "$SHELL" -l          # pick up the new PATH
```

- Clone it **anywhere** — `bootstrap.sh` derives its own location.
- Without `--path` it only *prints* the `export PATH=...` line for you to add yourself.
- `--no-sync` skips the network. **Do not use it on a fresh machine** — without the skill
  cache the verification step fails.
- It writes `~/.claude/CLAUDE.md` from `core/GLOBAL_CLAUDE.md` — the default global
  instructions every session loads. **Overwritten, not merged**: move hand-written
  global instructions out of the way first.
- `--lang English` sets the response language while it does that. Change it later with
  `jig lang English`; `jig lang` alone prints the current one.
- Running it again is safe and lands on the same state.

Confirm it worked:

```bash
jig list       # five profiles, with skill / agent / MCP counts
jig doctor     # rules and the handoff chain
```

### Starting from a machine that already has Claude Code

`reset-and-setup.sh` returns Claude Code to a just-installed state, then bootstraps.
Copy that single file to the machine — it clones jigkit itself if there is none beside it.

```bash
./reset-and-setup.sh --dry-run   # what would be deleted, and nothing else
./reset-and-setup.sh --path      # back up, reset, clone, bootstrap
```

- A `tar` backup lands in `~/.claude-reset-backups/` first; `--restore <file>` puts it back.
- `--keep-history` spares conversations and memory (`~/.claude/projects/`).
- **Close Claude first.** It refuses to run while Claude is open, because the desktop app
  and the CLI share `~/.claude` and rewrite it on exit — a reset under a live session is
  silently undone.

## 3. The idea, in four lines

- A **profile** is a stage of work, not a persona: `researcher → pm → designer → developer → reviewer`.
- Skills, MCP servers and permissions are decided **when the process starts**.
- Stages hand off through **files**, not conversation — a stage cannot edit the previous
  stage's output.
- So switching stages means starting a new session. There is no mid-session switch.

## 4. Run a session

```bash
jig list                   # what profiles exist
jig developer              # current directory as the project
jig developer ~/work/app   # or point at one
jig argv developer         # print the launch argv without running it
```

## 5. Add skills

Skills come from open-source repositories. Only the link and a pinned commit are committed.

```bash
jig source add https://github.com/anthropics/skills
jig sync                   # fetch to the pinned commit
jig skills                 # what is available, and what each costs at session start
```

Activate them in `profiles/<name>/profile.yaml`, by glob or by id:

```yaml
skills: ["anthropics/*"]                     # discovery — everything on
skills: [anthropics/pdf, anthropics/xlsx]    # after measuring
```

Then let usage decide what to keep:

```bash
jig usage                          # what actually got invoked, across all projects
jig usage --project ~/work/app     # narrowed to one project
```

Updating upstream is two steps on purpose — skills are instructions to an agent, so a
quiet upstream change is a quiet behaviour change:

```bash
jig sync --check                # is there an update? touches nothing
jig sync --update anthropics    # apply, showing what changed
```

## 6. Set a project up (stacks)

Stacks place what a *project* runs with — formatter hooks, gates, MCP definitions.

```bash
jig stack list                       # the catalogue, and which words map where
jig stack show web-app               # what that combination places
jig stack show web-app --plan ./app  # the commands to run, in order
jig stack apply web-app ./app        # dry-run
jig stack apply web-app ./app --apply
jig stack check web-app ./app        # declared against actual
```

- `apply` is a **dry-run without `--apply`**.
- `apply` **wires, it never installs.** Creating the project and installing tools is the
  `--plan` list's job; `apply` writes only what must not drift.
- Presets carry aliases, so `jig stack show fastapi` and `jig stack show api` are the same
  thing.

## 7. Move to the next stage

Inside the session:

```
> /profile designer
  ✓ developer done-conditions: 3/4
  ⚠ tests not run
  next: close this session and run  jig designer
```

It checks the done-conditions, records the verdict in `.harness/state.json`, and prints
the command. Then close the session and run it.

If the previous stage stopped short, launching **forward** is refused:

```bash
jig developer                        # relaunching the same profile is the recovery path
JIG_GATE_BYPASS=1 jig reviewer       # go anyway — an env var, so it leaves a trace
```

## 8. Things that will bite you

- **Isolation is not sandboxing.** Broad `Bash` access can route around a deny rule, and
  write permissions are a *denylist* — files no profile owns (`README.md`, `package.json`)
  stay writable by everyone.
- **A switch starts a fresh conversation.** The documents are the handoff; context does not
  carry over.
- **Keep skill descriptions short.** Every session pays for every description whether the
  skill is used or not (~70 tokens short, ~161 long). The body is free until invoked.
- **Nothing is pruned automatically.** `jig usage` reports; narrowing a profile is your
  one-line edit.
- **`--no-sync` on a fresh machine** leaves no skill cache, and `jig doctor` fails.

## 9. When something is wrong

| Symptom | Fix |
|---|---|
| `jig: command not found` | PATH line not added — `./bootstrap.sh --path`, or just use `./bin/jig` |
| bootstrap stops at `FAIL PyYAML` | `python3 -m pip install --user PyYAML` |
| `reset-and-setup.sh` refuses to run | Quit the Claude desktop app and all `claude` sessions |
| `jig doctor` fails after a profile edit | A profile waits on a document nobody produces, or produces one nobody reads |
| skills missing after a fresh clone | `jig sync` |

## Next

- [`README.md`](../README.md) — why profiles are split, what was measured, and what the
  isolation does and does not mean.
- [`PRINCIPLES.md`](PRINCIPLES.md) — the principles, their sources, and the strongest
  published objection to this design.

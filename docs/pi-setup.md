# Using co-scientist with the Pi coding agent

The harness runs on Pi as well as Claude Code. Almost nothing is ported: the
skills are already standard Agent Skills, and the MCP server is reached through
Pi's official MCP adapter reading the same `.mcp.json` Claude Code uses.

Clone it and point Pi at the clone. This package is deliberately **not** listed
in the Pi catalog:

```bash
git clone https://github.com/k821209/co-scientist-mcp-public ~/co-scientist-mcp-public
pi install ~/co-scientist-mcp-public
pip install -e ~/co-scientist-mcp-public/apps/local-mcp
```

That gives you the 25 skills, the provenance guard, and the MCP. Then wire the
tools.

## 0. Updating — and why the install is a path, not `git:`

```bash
cd ~/co-scientist-mcp-public && git pull
```

That is the whole update, for the skills, the guard and the MCP at once. A local
path is "added to settings without copying", so Pi reads the skills and the
extension out of your clone on every start, and `pip install -e` reads the MCP
out of the same tree. Nothing to re-install; restart the session.

`pi install git:…` also works and is what the Pi docs lead with, but do not use
it here:

- **Pi owns that clone and will overwrite it.** Reconciling a `git:` package runs
  `git reset --hard` followed by `git clean -fdx` in it
  (`package-manager.ts`). `-x` takes ignored files too — and that clone is
  exactly where this setup asks you to `pip install -e`, whose build artefacts
  are ignored files.
- **Two clones.** A machine that also runs Claude Code usually has its own
  checkout, so `pip install -e` points at one of them and Pi loads skills from
  the other — you end up running new skills against an old MCP, and `whoami`'s
  `update_available` cannot see it, because it checks the pip-installed side
  only.
- Updating it is `pi update --extensions`, not `git pull`: a manual pull inside
  Pi's clone is undone the next time Pi reconciles it.

One clone that you own avoids all three.

What does NOT collide either way: the skills. Pi reads `~/.pi/agent/skills` /
`.pi/skills`, the MCP links Claude Code's into `<project>/.claude/skills`, and the
MCP leaves `.claude/` alone entirely unless the project already has one (so a
Pi-only project stays clean).

## 1. What to install, and what each one buys you

One extension is required. The other two are per-skill: without them those
skills fail at the moment you run them, not at setup, so they are listed here
rather than left to be discovered.

```bash
pi install npm:pi-mcp-adapter   # required — every tool call goes through it
pi install npm:pi-subagents     # /reviewer-frame-check, and /paper-revision +
                                # /response-letter, which call it
pi install npm:pi-web-access    # /journal-requirements, /news-short,
                                # /science-short
```

3 of the 25 skills need each of the latter two; the remaining 19 need neither.

`pi-subagents` is the unscoped package. `@tintinweb/pi-subagents` is a
**different** extension that also exists on npm — the two are not
interchangeable, and the name in this file is the one the skills were written
against.

### What you do not need

- **`pi-memory`** — project memory is already server-side, in
  `get_project_memory` / `append_project_memory`, so it survives a machine
  change and a host change. Installing a second memory gives you two places
  where a decision might be recorded and one of them is invisible to the
  dashboard and to every other session.
- **`pi-lens`, `pi-sandbox`** and the rest of the catalog — general Pi
  extensions, unaffected by and unrelated to this package. Install them because
  you want them, not because co-scientist asks.

  One interaction worth knowing before you reach for `pi-sandbox`: this harness
  deliberately runs heavy compute on your own machine and ssh's to servers you
  registered. If you sandbox the Bash path, `launch_local_job` and
  `submit_remote_job` are exactly the things that will need permitting, and the
  `block-untracked-ssh` guard (§6) already covers the case sandboxing is usually
  reached for here.

## 2. The MCP server

The adapter (installed in §1) reads `mcpServers` from `.mcp.json` — the same file the co-scientist
setup script already writes for Claude Code, so if you have set this project up
once there is nothing to create:

```json
{
  "mcpServers": {
    "co_scientist": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "co_scientist_local"]
    }
  }
}
```

## 2b. One command instead of two files

The dashboard's Setup tab (Pi panel) hands out a setup script that writes both
`.mcp.json` and `CLAUDE.md` into the current directory and adds `.mcp.json` to
`.gitignore` — the same script the Claude Code path uses, with the two adapter
settings already in the config and no `.claude/` directory written (Pi reads
skills from the installed package, so one here would be a directory nothing
reads).

Every download there has a **Copy as command** beside it, which puts the file on
the machine your terminal is already on — over ssh a download lands on the
laptop and then has to be moved.

## 3. CLAUDE.md — the same file both hosts read

Pi loads `AGENTS.md` or `CLAUDE.md` from the project directory as a **context
file**, walking up from the cwd, plus `~/.pi/agent/AGENTS.md` globally. So the
`CLAUDE.md` the dashboard's Setup tab generates is read by Pi verbatim; there is
no Pi-specific version to write. Download it into the project folder alongside
`.mcp.json`.

Do NOT also add an `AGENTS.md` next to it. Pi takes the FIRST match in a
directory — `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`,
`CLAUDE.MD` — so an `AGENTS.md` shadows the `CLAUDE.md` rather than adding to it.

Why it matters on a fresh folder: the file carries the project id, and the
session-start sequence compares it against what `whoami()` returns. That check is
what catches a `.mcp.json` and a `CLAUDE.md` taken from two different dashboard
projects. Skip the file and there is nothing to compare — the mismatch surfaces
later, as edits landing in the wrong project.

### Personal rules are a different mechanism, and they do not merge

Pi has two other files, and they are not context files:

| | |
|---|---|
| `.pi/SYSTEM.md`, `~/.pi/agent/SYSTEM.md` | **replaces** the default system prompt |
| `.pi/APPEND_SYSTEM.md`, `~/.pi/agent/APPEND_SYSTEM.md` | **appends** to it |

For each pair Pi uses the project file **or** the global one, never both: a
`.pi/APPEND_SYSTEM.md` in a project silently disables your global working rules
for that project. Context files layer; these do not. This package ships neither,
and does not write to `~/.pi/agent/` — your rules there are yours.

The project-side ones also load only after the folder is trusted (`/trust`), so
on an untrusted folder they are skipped and the global one is used instead, which
reads as rules switching on and off between projects.

## 4. Two adapter settings that are NOT optional

```json
{
  "directTools": true,
  "toolPrefix": "mcp"
}
```

- **`directTools: true`** — by default the adapter exposes one `mcp` proxy tool
  rather than the individual tools. The skills call tools by name, so they need
  the direct form.
- **`toolPrefix: "mcp"`** — produces `mcp__co_scientist__<tool>`, which is
  exactly what every skill already writes. The adapter's DEFAULT prefix is
  `<server>_<tool>`, and under that default every tool reference in every skill
  is wrong. This is the single most likely thing to get wrong.

Verify before trusting it: run `/mcp` (or ask the agent to list its tools) and
confirm you see `mcp__co_scientist__whoami`. If you see `co_scientist_whoami`,
the prefix setting has not taken effect.

## 5. What differs from Claude Code

| | |
|---|---|
| 25 skills | identical — `SKILL.md` folders, discovered recursively |
| MCP tools | identical names, via the adapter settings above |
| The ssh/provenance guard | ported as a Pi extension (`block-untracked-ssh`), same aliases file, same `# setup` / `# allow-untracked` overrides |
| `session_start` hook | **not ported.** Claude Code ran the open-comment check itself. The same sequence is written into `CLAUDE.md` (§3), which Pi does read — so it runs because the agent is instructed to, not because a hook fires. Ask for it if a session starts without it |
| `/reviewer-frame-check` (and `/paper-revision`, `/response-letter`, which call it) | needs `pi-subagents` (§1) — or run the check in a separate Pi session with only the bundle files open. The isolation is the point, not the mechanism |
| Skills using `WebFetch` (`/news-short`, `/science-short`, `/journal-requirements`) | need `pi-web-access` (§1) |

## 6. What the guard does

`block-untracked-ssh` refuses a backgrounded `ssh` to a **registered** server
(`nohup`, `disown`, or a trailing `&`) and points you at
`submit_remote_job`, so the run lands in `analysis_runs` and shows up in the
dashboard's Running Jobs. It reads server aliases from
`~/.co-scientist/cache/servers.json`, which the MCP writes — no network call on
your Bash path — and **fails open** when that file is missing, so a fresh machine
is never blocked from working.

Legitimate non-job ssh (making a directory, creating an env) is allowed by
prefixing the command with `# setup` or including `# allow-untracked` anywhere in
it.

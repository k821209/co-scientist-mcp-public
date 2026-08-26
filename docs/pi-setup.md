# Using co-scientist with the Pi coding agent

The harness runs on Pi as well as Claude Code. Almost nothing is ported: the
skills are already standard Agent Skills, and the MCP server is reached through
Pi's official MCP adapter reading the same `.mcp.json` Claude Code uses.

Install by git, not npm — this package is deliberately **not** listed in the Pi
catalog:

```bash
pi install git:github.com/k821209/co-scientist-mcp-public
```

That gives you the 25 skills and the provenance guard. Then wire the tools.

## 0. One clone, not two — read this if you also use Claude Code

Both hosts install from the SAME git repo, and that is where a machine running
both can go wrong. `pi install git:…` clones into
`~/.pi/agent/git/github.com/k821209/co-scientist-mcp-public`, while a Claude Code
setup usually has its own clone elsewhere. Two copies, and only one of them is the
one `pip install -e` points at — so you can end up running **new skills against an
old MCP**, or the reverse, and `whoami`'s `update_available` cannot see it: it
checks the pip-installed side only.

So point pip at the clone Pi manages, and there is only ever one copy:

```bash
pi install git:github.com/k821209/co-scientist-mcp-public
pip install -e ~/.pi/agent/git/github.com/k821209/co-scientist-mcp-public/apps/local-mcp
```

Then a single `pi install …` refresh upgrades the skills, the extension AND the
MCP together. If you already have a Claude Code clone you would rather keep as the
canonical one, do the reverse — install the Pi package from that local path
(`pi install /path/to/co-scientist-mcp-public`) rather than from git.

What does NOT collide: the skills. Pi reads `~/.pi/agent/skills` / `.pi/skills`,
the MCP links Claude Code's into `<project>/.claude/skills`, and the MCP now
leaves `.claude/` alone entirely unless the project already has one (so a Pi-only
project stays clean).

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

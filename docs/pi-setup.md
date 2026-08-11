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

## 1. The MCP server

```bash
pi install npm:pi-mcp-adapter
```

The adapter reads `mcpServers` from `.mcp.json` — the same file the co-scientist
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

## 2. Two adapter settings that are NOT optional

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

## 3. What differs from Claude Code

| | |
|---|---|
| 25 skills | identical — `SKILL.md` folders, discovered recursively |
| MCP tools | identical names, via the adapter settings above |
| The ssh/provenance guard | ported as a Pi extension (`block-untracked-ssh`), same aliases file, same `# setup` / `# allow-untracked` overrides |
| `session_start` banner | **not ported.** Claude Code's SessionStart hook surfaced open comments at startup; on Pi, call `whoami` + `list_papers` + `count_open_user_comments` yourself, as `project_guide()` step 3 describes |
| `/reviewer-frame-check` | needs a subagent. Install `pi install npm:pi-subagents`, or run the check in a separate Pi session with only the bundle files open — the isolation is the point, not the mechanism |
| Skills using `WebFetch` (`/news-short`, `/science-short`, `/journal-requirements`) | need web access: `pi install npm:pi-web-access` |

## 4. What the guard does

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

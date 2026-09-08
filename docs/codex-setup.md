# Using co-scientist with OpenAI Codex

The harness runs on Codex (the `codex` CLI) as well as Claude Code and Pi, and
Codex is the easiest of the three to wire: it qualifies MCP tools as
`mcp__<server>__<tool>` on its own, it speaks Claude Code's hook protocol, and
it keeps MCP tools behind a tool search instead of listing them in every
prompt. So the skills, the hooks and every tool name cross over unchanged. What
differs is the file layout and two trust prompts on the first launch.

Everything below was read from the Codex source (`openai/codex`, v0.153.4) —
the paths in parentheses are where to look if a later Codex changes it.

## 1. Install

Codex itself (`npm i -g @openai/codex`, then `codex login`) is assumed. The MCP
is the same install as for Claude Code, and it carries the skills and the hooks.
It needs **Python 3.11 or newer**; a bare Ubuntu/WSL box usually has an older
one, so on such a machine start with the deadsnakes block in
[setup-user.md](setup-user.md). A venv is your choice — the setup script finds
the interpreter that has the package either way (PATH `python3`, then
`python3.11`–`3.13`, then `~/co-scientist-mcp-public/.venv`), and for a venv
anywhere else you set `CO_SCIENTIST_PYTHON` to its `python` before running it.

```bash
git clone https://github.com/k821209/co-scientist-mcp-public ~/co-scientist-mcp-public
pip install -e ~/co-scientist-mcp-public/apps/local-mcp      # or python3.11 -m pip, or a venv's pip
```

Verified on a bare Ubuntu machine (2026-09-08): deadsnakes python3.11, a venv
inside the clone, `pip install -e`, then the setup script.

Already installed for Claude Code or Pi on this machine? Nothing to do here.
Updating is `git pull` in that folder and a restart — MCP, skills and hooks at
once.

## 2. The project directory (one command)

The dashboard's Setup tab (Codex panel) hands out a setup script. Run it in the
project folder; it writes four things:

| | |
|---|---|
| `.codex/config.toml` | the MCP server, with the project's API key — **added to `.gitignore`** |
| `AGENTS.md` | the project context (project id + session-start sequence) |
| `.agents/skills/` | symlinks to the skills, one per skill |
| `.codex/hooks.json` | the session-start banner and the ssh provenance guard |

Every download there has a **Copy as command** beside it, which puts the file on
the machine your terminal is already on.

### Why these names, and not the Claude Code ones

- **`.codex/config.toml`, not `.mcp.json`.** Codex reads config layers: the user
  one at `~/.codex/config.toml`, and a project one found by walking up from
  the cwd looking for `.codex/config.toml` (`codex-rs/config/src/loader/mod.rs`).
  `codex mcp add` would write the *user* layer — one server for every project
  on the machine, and therefore one API key — which is the wrong scope for a
  per-project key. The project layer is loaded **but disabled until the
  directory is trusted** (§3).
- **`AGENTS.md`, not `CLAUDE.md`.** Codex looks for `AGENTS.override.md`, then
  `AGENTS.md`, then whatever `project_doc_fallback_filenames` names — and that
  list is **empty by default** (`codex-rs/core/src/agents_md.rs`,
  `config_toml.rs`). A `CLAUDE.md` is invisible to it. The content is the same
  file the other hosts get, so a folder used with both Codex and Claude Code
  simply has both names with identical text. (Pi takes the first match per
  directory and would read `AGENTS.md`; identical content makes that harmless.)
- **`.agents/skills/`.** One of Codex's repo-scope skill roots: it scans
  `<dir>/.agents/skills` for every directory from the project root down to the
  cwd (`codex-rs/ext/skills/src/host_roots.rs`). `~/.agents/skills` would be
  user-wide; the project one keeps the skill version tied to the checkout, as
  `.claude/skills` does for Claude Code. The MCP re-links it on every start.
- **`.codex/hooks.json`.** Project-layer hooks, in the shape Claude Code's
  `settings.json` uses (`PreToolUse` / `SessionStart` / `PostToolUse`, a
  `matcher`, `type: "command"` entries). Generated rather than copied, because
  `timeout` is **seconds** here and the commands carry the interpreter's
  absolute path — hooks run through `$SHELL -lc`, whose PATH need not be the
  one the MCP was installed from.

### Three lines in the config that are Codex-specific

```toml
startup_timeout_sec = 30
```

Codex gives an MCP server 10 seconds to start (`startup_timeout_sec`, default
`10`). This one exchanges the API key for a token and links the skills before
it answers, which on a slow network takes longer — and a server that misses the
deadline shows up as "no co-scientist tools", not as a timeout.

```toml
env_vars = ["CO_SCIENTIST_ENABLE_VIDEO", "CO_SCIENTIST_FIRESTORE_TIMEOUT", "…"]
```

Codex does **not** pass an MCP server the shell's environment. It builds one
from `HOME`, `PATH`, `LANG`, `TERM` and a handful more, plus the literal `env`
table, plus whatever `env_vars` names
(`codex-rs/rmcp-client/src/utils.rs`). Under Claude Code the server inherits
everything, so an `export CO_SCIENTIST_FIRESTORE_TIMEOUT=60` simply works;
under Codex it would silently not arrive. The generated list is every
environment variable the MCP reads, minus the API key the config sets — a test
in the repo keeps it that way. Names only; a name not set in your shell is
skipped.

```toml
[sandbox_workspace_write]
network_access = true
```

The skills run ssh, pip and curl through Codex's shell tool, and the default
`workspace-write` sandbox has **no network**
(`SandboxPolicy::new_workspace_write_policy`, `codex-rs/protocol/src/protocol.rs`).
Without this line every remote job and every install is a sandbox denial. The
MCP server process itself is launched by Codex outside that sandbox, so the
Firestore calls are unaffected either way. If you would rather approve network
use per command, delete the two lines and answer the prompts.

## 3. First launch — two trust prompts

1. **Trust the directory.** Codex asks on the first launch in a folder it has
   not seen (`should_show_trust_screen`, `codex-rs/tui/src/lib.rs`). Until you
   answer yes, the project `.codex/config.toml` is loaded but disabled and
   `AGENTS.md` is not read — so "no co-scientist tools" on a fresh folder means
   this, not a broken install.
2. **Review and trust the hooks.** Codex reports "N hooks are new or changed"
   and offers *Review hooks* / *Continue without trusting (hooks won't run)*.
   Trust is recorded per hook as a hash of its configuration (`[hooks.state]`
   in your user config), so a regenerated file with a changed command — a new
   interpreter path, say — asks again; an identical one does not. Untrusted
   hooks do not run — and that includes the ssh guard.

Then verify — do not assume:

- `/mcp` lists the tools. You should see `mcp__co_scientist__whoami` — the
  same name every skill writes. (A feature flag,
  `non_prefixed_mcp_tool_names`, would drop the `mcp__` prefix; it is off and
  marked "under development". If a future Codex turns it on, the skills'
  tool names would stop matching — that is the one thing to check after a
  Codex upgrade.)
- Ask it to call `whoami` and compare `project_id` with the one in `AGENTS.md`.
  A mismatch means `.codex/config.toml` and `AGENTS.md` came from two different
  dashboard projects; the MCP prints the same warning on its stderr.

## 4. What differs from Claude Code

| | |
|---|---|
| Skills | identical files. Invoked as **`$paper-review`** (a `$` mention), not `/paper-review`; where a skill's text says `/name` it means the same skill. Codex shows the catalog within a budget of about 2% of the context window, truncating long descriptions rather than dropping skills (`codex-rs/ext/skills/src/render.rs`) |
| MCP tools | identical names. Not listed in every prompt: with current OpenAI models they sit behind Codex's tool search and are loaded when looked up by name (`mcp_tool_exposure.rs`). So no direct-tool list is needed, unlike Pi. With `--oss` / a local provider the search is unavailable and all tools are direct; then `enabled_tools = [...]` under `[mcp_servers.co_scientist]` is the equivalent of Pi's list |
| `session_start` hook | **runs** (SessionStart, via `.codex/hooks.json`) — Claude Code parity, unlike Pi |
| The ssh provenance guard | the same Python file, via `PreToolUse` with matcher `Bash` — Codex reports its shell tool to hooks under that name (`codex-rs/core/src/tools/hook_names.rs`). Same `# setup` / `# allow-untracked` overrides, same fail-open when the aliases cache is missing |
| `/reviewer-frame-check` | needs a reader that holds only the bundle. Codex can spawn agents, but not one restricted to reading — run the check in a separate Codex session with only the bundle files open. The isolation is the point, not the mechanism |
| `/news-short`, `/science-short`, `/journal-requirements` | need the web: start Codex with `--search`, or set `web_search = "live"` in your user config |

## 5. Updating

`git pull` in the clone, restart Codex. The MCP re-links `.agents/skills` on
start; the hooks are read from the clone by path, so they update with it. If
the hook *files* change, Codex will ask you to re-trust them.

# Setup — user

For someone signing up at `https://co-scientist-5af1a.web.app` and writing
their first paper. Three commands on their machine, the rest in the browser.

## 1. Install the MCP (one-time, ~30s)

```bash
git clone https://github.com/k821209/co-scientist-mcp-public.git ~/co-scientist-mcp-public
pip install -e ~/co-scientist-mcp-public/apps/local-mcp
```

Pip-only alternative (no source on disk):

```bash
pip install "git+https://github.com/k821209/co-scientist-mcp-public.git#subdirectory=apps/local-mcp"
```

### Export dependencies (needed for `export_to_path`)

Manuscript export shells out to system binaries that pip can't install:

- **pandoc** — required. `brew install pandoc` (macOS) / `apt install pandoc` (Debian/Ubuntu). Pip-only fallback: `pip install pypandoc-binary`, then symlink its bundled pandoc onto your PATH.
- **LibreOffice** (`soffice`) — recommended. Used to normalize exported `.docx` so it opens cleanly in **Hancom Office (한컴오피스)**, which otherwise crashes on pandoc's output. Without it, export still works but falls back to a lighter zip-repair pass.

You only need these if you export. The MCP gives a clear "install pandoc" error if it's missing.

## 2. In the dashboard

1. Sign in (Google or email).
2. Create a project. Free tier = 3 projects.
3. Open the project → **Setup** tab.
4. Click **Download setup script** — gets `setup-<slug>.sh`.

The script bundles `.mcp.json` (with the project's API key) + `CLAUDE.md`
(slim, ~18 lines, refers to `project_guide()` MCP tool for the current
usage instructions). The key is project-scoped; every Firestore write
the MCP makes is constrained to that project by security rules.

## 3. In your project directory

```bash
cd /path/to/your/paper-project
bash ~/Downloads/setup-<slug>.sh
claude          # launch Claude Code
```

Claude Code auto-loads `CLAUDE.md` + spawns the MCP child process via
`.mcp.json`. The MCP exchanges your API key, signs in to Firebase as the
project owner, and is ready.

Try:

```
/paper-writing "Your paper title"
```

The dashboard's Papers tab updates live as the agent writes sections.

## Sanity checks

- `/mcp` in Claude Code → should show `co_scientist · ✔ connected`.
- Have the agent run `mcp__co_scientist__whoami()` — confirms the MCP
  is bound to the correct project_id (matches what your CLAUDE.md says).
- The MCP startup line on stderr looks like:
  `co-scientist-local: token-auth, project=<pid>, owner=<uid>`.

## Common gotchas

- **Mixing `.mcp.json` + `CLAUDE.md` from different projects** — the MCP
  authenticates to whichever project the API key belongs to, but the
  agent reads project identity from `CLAUDE.md`. They must match.
  `whoami()` catches this.
- **`pip install -e` ed — need to update?** — `git pull` (in
  `~/co-scientist-mcp-public`) updates the
  source files in-place because the install was editable. But the
  *running MCP child process* imported the code at startup, so you
  need to fully restart Claude Code (cmd-Q on macOS) to spawn a new
  child with the new code.
- **OPENAI_API_KEY in your shell** — only used if you also set
  `CO_SCIENTIST_USE_LOCAL_OPENAI=1`. Otherwise ignored.

## Image generation requires Pro

`generate_image` routes through a Firebase Cloud Function. Free plan = 403.
Upgrade in the dashboard (admin manually sets `plan_id=pro` until Stripe
webhook is wired). Free-tier alternative: set `GEMINI_API_KEY` in env +
configure `image_gen_mode=local` in `~/.co-scientist/projects/<pid>.toml`.

See the dashboard for current plan quotas.

# co-scientist MCP

Local [MCP](https://modelcontextprotocol.io) server for Claude Code that powers
the **co-scientist** scientific-writing assistant. It runs on your machine,
authenticates to the project you created in the dashboard, and gives the agent
tools to draft manuscripts, manage references, render figures/decks, and sync
review comments — all backed by your project's Firestore/Storage.

- **Dashboard / sign up**: https://co-scientist-5af1a.web.app
- **Heavy compute stays local**: no server-side LLM; the MCP runs as a Claude
  Code child process on your machine (or your registered HPC).

## Install

```bash
git clone https://github.com/k821209/co-scientist-mcp-public.git ~/co-scientist-mcp-public
pip install -e ~/co-scientist-mcp-public/apps/local-mcp
```

Then follow [`docs/setup-user.md`](docs/setup-user.md) to download your
project's setup script and launch Claude Code.

## What's here

```
apps/local-mcp/     # the MCP server (pip-installable)
packages/
├── cli/            # co_scientist_cli — Firebase auth / token helpers
├── hooks/          # Claude Code hooks (session start, pre-tool guards)
└── skills/         # SKILL decks: paper-writing, literature-review, decks, …
docs/               # setup + tool catalog + DOI verification
```

## Docs

- [setup-user.md](docs/setup-user.md) — sign up → first paper
- [mcp-tools.md](docs/mcp-tools.md) — full MCP tool catalog
- [doi-verification.md](docs/doi-verification.md) — CrossRef hallucination check

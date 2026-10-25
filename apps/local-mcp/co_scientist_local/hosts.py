"""The agent hosts Scivo can be wired into, as data.

Four hosts run the same MCP and the same skills; what differs between them is
small and entirely mechanical — where the server config goes, what the context
file is called, whether skills are read at all, how the user signs in. That
difference was written out by hand in three places: the dashboard's Setup tab
(a component per host), `docs/*-setup.md` (a page per host), and `scivo setup`
(which knew only Claude Code). Adding a host meant editing three copies, and
missing one leaves the documentation telling someone to configure something
the tool will refuse — which is exactly how `/paper-deck` came to document a
slide role `add_slide` rejected, and how seven files came to claim 30 skills.

So the facts live here, in the payload every host installs, and the three
surfaces read them:

  - Python, for the package's own installers;
  - `python -m co_scientist_local hosts --json`, for `scivo setup` and any
    script (the harness shells out to the interpreter rather than importing);
  - `apps/web/src/lib/hosts.generated.ts`, written by
    scripts/generate-host-catalog.py and checked by a test, for the dashboard.

Gemini CLI is deliberately absent: the 2026-07-22 POC passed the plumbing and
its answer quality was never evaluated, and the user's call on 2026-10-25 was
not yet. Adding it is a row here, which is the point.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Host:
    """One agent host, and everything that is different about wiring it."""

    id: str
    label: str
    # What the user runs to start a session in a wired directory.
    start: str
    # Where the MCP server registration is written, relative to the project
    # directory unless it starts with "~".
    config_path: str
    config_format: str                     # json | toml
    # The file the host reads as its project instructions, or None when the
    # host has no such convention.
    context_file: str | None
    # Whether the host loads SKILL.md directories. A host that does not still
    # gets every tool — `project_guide()` is a tool — but not the workflows.
    reads_skills: bool
    # How the user authenticates with the MODEL (not with Scivo).
    sign_in: str
    # Where this host looks for skills, when it reads them at all.
    skills_path: str | None = None
    # Things true of this host and no other, stated once.
    caveats: tuple[str, ...] = field(default_factory=tuple)


HOSTS: tuple[Host, ...] = (
    Host(
        id="claude",
        label="Claude Code",
        start="claude",
        config_path=".mcp.json",
        config_format="json",
        context_file="CLAUDE.md",
        reads_skills=True,
        sign_in="claude auth login",
        caveats=(
            "`command` must name the interpreter that HAS the package: a bare "
            "`python3` resolves through PATH and picks a different one under "
            "another shell.",
        ),
    ),
    Host(
        id="codex",
        label="Codex",
        start="codex",
        # A PROJECT config, found by walking up from the cwd — not only the user
        # one at ~/.codex/config.toml (codex-rs/config/src/loader/mod.rs).
        config_path=".codex/config.toml",
        config_format="toml",
        context_file="AGENTS.md",
        # Its own `.agents/skills/` symlinks, from `install-skills --host codex`
        # (install-agents is a different thing: Claude Code subagents).
        reads_skills=True,
        skills_path=".agents/skills/",
        sign_in="codex login",
        caveats=(
            "Codex does NOT inherit the shell environment, so the key has to be "
            "written into the config rather than exported.",
            "Its sandbox has no network by default; tools that reach Firestore "
            "need it enabled.",
            "`AGENTS.override.md` wins over `AGENTS.md`, so a project with both "
            "reads only the first.",
        ),
    ),
    Host(
        id="pi",
        label="Pi",
        start="pi",
        # Pi's official MCP adapter reads the SAME file Claude Code does.
        config_path=".mcp.json",
        config_format="json",
        # Pi takes the first match in a directory: AGENTS.override.md,
        # AGENTS.md, AGENTS.MD, then CLAUDE.md — so the CLAUDE.md the Setup tab
        # generates is read verbatim and no Pi-specific file is written.
        context_file="CLAUDE.md",
        reads_skills=True,
        skills_path="~/.pi/agent/skills | .pi/skills",
        sign_in="(the provider Pi is configured with)",
        caveats=(
            "Do not add an AGENTS.md beside CLAUDE.md: Pi reads the first match "
            "and would stop seeing the generated one.",
            "Its skills live apart from Claude Code's, so a Pi-only project "
            "keeps no .claude/ directory at all.",
        ),
    ),
    Host(
        id="harness",
        label="scivo (harness)",
        start="scivo -c",
        config_path=".mcp.json",
        config_format="json",
        context_file="CLAUDE.md",
        reads_skills=True,
        sign_in="claude auth login",
        caveats=(
            "`scivo setup` writes the config, links the skills and verifies the "
            "key against the project in one command.",
            "The control page (`/scivo-control`, or `scivo -c --control`) is "
            "what puts the session in the dashboard's sidebar.",
        ),
    ),
)

BY_ID: dict[str, Host] = {h.id: h for h in HOSTS}


def host(host_id: str) -> Host:
    try:
        return BY_ID[host_id]
    except KeyError:
        raise ValueError(
            f"unknown host {host_id!r}; known: {', '.join(BY_ID)}") from None


def catalog() -> list[dict]:
    """The table as plain data — what the JSON and TS copies are built from."""
    return [asdict(h) | {"caveats": list(h.caveats)} for h in HOSTS]


def cli(argv: list[str]) -> int:
    """`python -m co_scientist_local hosts [--json]`."""
    import json
    if "--json" in argv:
        print(json.dumps(catalog(), indent=2, ensure_ascii=False))
        return 0
    for h in HOSTS:
        skills = "skills" if h.reads_skills else "tools only"
        print(f"{h.id:9} {h.label:18} {h.config_path:22} {skills}")
    return 0

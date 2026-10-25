"""Wire a project directory to a host, from the host table.

`python -m co_scientist_local wire --host claude --project <pid> --key <key>`

This is the branching the one-line installer needs, kept in Python rather than
in shell: it is a per-host table lookup plus two file writes, and in a shell
script it would be a `case` statement that nothing tests. The installer stays
thin — a virtualenv, a symlink, and a call to this.

What differs per host comes from `hosts.py`, which is the one copy. What is the
same for every host lives here: the server name (`scivo`), the key in the
environment rather than on a command line in the shell's history, the skills
linked where that host looks for them, and the config kept out of git.

The harness is deliberately NOT handled here: `scivo setup` already writes the
same file AND verifies that the key binds to the project it was given, which is
the check that catches a key pasted from another project's Setup tab. Having
two code paths write the same file, one of them weaker, is how they drift.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from .hosts import host as get_host

SERVER_NAME = "scivo"

# Environment variable NAMES forwarded to the MCP under Codex, which hands a
# server only HOME/PATH/LANG/… and never the shell's environment. The same list
# lives in apps/web/src/lib/codexEnv.ts; tests/test_skill_audit.py derives the
# truth from what the MCP source actually reads and fails if either copy drifts.
CODEX_FORWARDED_ENV = (
    "CO_SCIENTIST_CHECKOUT",
    "CO_SCIENTIST_DASHBOARD_URL",
    "CO_SCIENTIST_ENABLE_VIDEO",
    "CO_SCIENTIST_EXCHANGE_URL",
    "CO_SCIENTIST_FIRESTORE_TIMEOUT",
    "CO_SCIENTIST_GENERATE_IMAGE_URL",
    "CO_SCIENTIST_PROJECT_ID",
    "CO_SCIENTIST_SERVERS_CACHE",
    "CO_SCIENTIST_SKIP_AGENT_INSTALL",
    "CO_SCIENTIST_SKIP_SKILL_INSTALL",
    "CO_SCIENTIST_SKIP_VERSION_CHECK",
    "CO_SCIENTIST_UID",
    "CO_SCIENTIST_USE_MEMORY",
    "CO_SCIENTIST_YOUTUBE_TOKEN",
    "FIREBASE_PROJECT_ID",
    "FIREBASE_STORAGE_BUCKET",
    "FIREBASE_WEB_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
)


def mcp_json(api_key: str, interpreter: str) -> str:
    """The `.mcp.json` Claude Code and Pi both read.

    `command` is the interpreter that HAS the package, never a bare `python3`:
    that resolves through PATH and picks a different one under another shell,
    which is the single most common way a working install stops working.
    """
    return json.dumps(
        {"mcpServers": {SERVER_NAME: {
            "type": "stdio",
            "command": interpreter,
            "args": ["-m", "co_scientist_local"],
            "env": {"CO_SCIENTIST_API_KEY": api_key},
        }}},
        indent=2,
    ) + "\n"


def codex_toml(api_key: str, interpreter: str) -> str:
    """The `.codex/config.toml` Codex reads, walking up from the cwd."""
    q = json.dumps                      # TOML basic strings share JSON escapes
    names = "\n".join(f"  {q(name)}," for name in CODEX_FORWARDED_ENV)
    return f"""# Scivo — Codex project config. Holds this project's API key in
# clear text: keep it out of git.

[mcp_servers.{SERVER_NAME}]
command = {q(interpreter)}
args = ["-m", "co_scientist_local"]
env = {{ CO_SCIENTIST_API_KEY = {q(api_key)} }}
# Codex gives a server 10 s to start by default. This one exchanges the API key
# for a token and links the skills first, which on a slow network is longer —
# and the failure reads as "no scivo tools", not as a timeout.
startup_timeout_sec = 30
# Codex hands an MCP server only HOME/PATH/LANG/… — not your shell's
# environment. Names only; values come from your shell, and a name that is not
# set is skipped.
env_vars = [
{names}
]

# The skills run ssh, pip and curl through Codex's shell tool. The default
# workspace-write sandbox has no network, so without this every remote job and
# every install is a sandbox denial rather than a run.
[sandbox_workspace_write]
network_access = true
"""


def _ignore(root: pathlib.Path, *entries: str) -> None:
    """Add entries to .gitignore once. A config holding an API key that is also
    tracked is the loudest way to leak one."""
    path = root / ".gitignore"
    have = path.read_text().splitlines() if path.is_file() else []
    missing = [e for e in entries if e not in have]
    if not missing:
        return
    text = ("\n".join(have) + "\n" if have and have[-1].strip() else "".join(
        line + "\n" for line in have))
    path.write_text(text + "\n".join(
        ["# Scivo — holds this project's API key"] + missing) + "\n")


def wire(host_id: str, *, api_key: str, project: str | None, root: pathlib.Path,
         interpreter: str, force: bool = False) -> dict:
    """Write the host's config and link its skills. Returns what it did."""
    spec = get_host(host_id)
    if host_id == "harness":
        raise SystemExit(
            "the harness wires itself, and verifies the key against the "
            "project while doing it:\n"
            f"  scivo setup --project {project or '<pid>'} --key <key>")

    target = root / spec.config_path
    if target.exists() and not force:
        raise SystemExit(
            f"{target} already exists — pass --force to replace it, or edit it "
            "by hand. Refusing to overwrite a config that may hold another "
            "project's key.")
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (codex_toml(api_key, interpreter) if spec.config_format == "toml"
            else mcp_json(api_key, interpreter))
    target.write_text(body)
    _ignore(root, spec.config_path)

    # Skills, where this host looks for them. `install-skills --host` knows the
    # layouts (SKILL_DEST): .claude/skills for Claude Code and Pi, .agents/skills
    # for Codex. Codex also wants the hooks, which carry the session-start
    # banner and the ssh provenance guard — the dashboard's setup script runs
    # both, and the first version of this ran `install-agents` instead, which
    # installs Claude Code SUBAGENTS into .claude/agents and left a Codex
    # project with an empty skills directory and a `.claude/` it never reads.
    skill_host = "codex" if host_id == "codex" else "claude"
    steps = [["install-skills", "--host", skill_host]]
    if host_id == "codex":
        steps.append(["install-hooks", "--host", "codex"])
    linked = []
    for step in steps:
        done = subprocess.run(
            [interpreter, "-m", "co_scientist_local", *step, "--dir", str(root)],
            capture_output=True, text=True)
        linked.append({"command": " ".join(step), "ok": done.returncode == 0,
                       "detail": (done.stdout or done.stderr).strip()[-200:]})
    return {"host": host_id, "config": str(target), "skills": linked,
            "next": [spec.sign_in, spec.start], "caveats": list(spec.caveats)}


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m co_scientist_local wire",
        description="wire this directory to an agent host, from the host table")
    parser.add_argument("--host", required=True)
    parser.add_argument("--key", help="the project API key (else $CO_SCIENTIST_API_KEY)")
    parser.add_argument("--project", help="the project id, for the reply only")
    parser.add_argument("--dir", default=".", help="the project directory")
    parser.add_argument("--python", default=sys.executable,
                        help="the interpreter that HAS the package")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    import os
    api_key = args.key or os.environ.get("CO_SCIENTIST_API_KEY") or ""
    if not api_key:
        print("no key: pass --key or set CO_SCIENTIST_API_KEY", file=sys.stderr)
        return 2
    out = wire(args.host, api_key=api_key, project=args.project,
               root=pathlib.Path(args.dir).expanduser().resolve(),
               interpreter=args.python, force=args.force)
    print(f"wrote {out['config']}")
    for row in out["skills"]:
        if row["ok"]:
            print(f"{row['command']}: ok")
            continue
        # Not fatal — the config is written and the tools work — but a session
        # with no skills looks like a session with no workflows, and the line
        # that said only "FAILED" gave nothing to do about it.
        print(f"\n  !! {row['command']} did not link the skills: {row['detail']}")
        print("     The tools work without them; the /paper-export, /analysis-run "
              "… workflows do not.")
        print(f"     Retry:  {args.python} -m co_scientist_local {row['command']} "
              f"--dir {args.dir}\n")
    print("\nnext:")
    for line in out["next"]:
        print(f"  {line}")
    for caveat in out["caveats"]:
        print(f"  · {caveat}")
    return 0

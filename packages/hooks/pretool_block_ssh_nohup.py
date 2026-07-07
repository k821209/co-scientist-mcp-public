#!/usr/bin/env python3
"""PreToolUse(Bash) hook: block raw `ssh <alias> ... nohup …` patterns.

Forces users into `mcp__co_scientist__submit_remote_job` so jobs are
tracked in `analysis_runs` and visible in the dashboard's Running Jobs
panel.

The hook reads server aliases from a *local cache file*
(~/.co-scientist/cache/servers.json), refreshed by the local MCP at
startup and after add_server/update_server. The hook deliberately avoids
network calls — they'd slow down every Bash invocation.

Cache file format:
    { "servers": [{"alias": "gpu-box", "host": "192.0.2.10", "user": "alice"}, ...] }

Override prefixes (allow legitimate non-job ssh work):
    `# setup`, `# manual`, or `# allow-untracked` anywhere in the command.

Fail-open: if the cache is missing/unreadable, the hook does NOT block —
better to let a possibly-buggy job through than to break every Bash call.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CACHE_PATH = Path(
    os.environ.get(
        "CO_SCIENTIST_SERVERS_CACHE",
        str(Path.home() / ".co-scientist" / "cache" / "servers.json"),
    )
)

OVERRIDE_PREFIXES = ("# setup", "# manual")
OVERRIDE_INLINE = "# allow-untracked"

_BG_RE = re.compile(
    r"\bnohup\b|"
    r"\bdisown\b|"
    # standalone trailing & — whitespace-preceded so `2>&1` doesn't trigger
    r"\s&\s*[\"']?\s*$",
    re.MULTILINE,
)
_SSH_RE = re.compile(
    r"^\s*ssh\b\s+(?:-\S+\s+)*([A-Za-z0-9_.@-]+)",
    re.MULTILINE,
)


def load_aliases() -> set[str]:
    if not CACHE_PATH.is_file():
        return set()
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for s in data.get("servers", []):
        if s.get("alias"): out.add(s["alias"])
        if s.get("host"): out.add(s["host"])
        if s.get("user") and s.get("host"):
            out.add(f"{s['user']}@{s['host']}")
    return out


def has_override(command: str) -> bool:
    head = command.lstrip()
    if any(head.startswith(p) for p in OVERRIDE_PREFIXES):
        return True
    return OVERRIDE_INLINE in command


def is_blocked(command: str, aliases: set[str]) -> tuple[bool, str | None]:
    if has_override(command):
        return False, None
    if not _BG_RE.search(command):
        return False, None
    for m in _SSH_RE.finditer(command):
        target = m.group(1)
        if target in aliases:
            return True, target
    return False, None


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "").strip()
    if not command:
        sys.exit(0)
    aliases = load_aliases()
    if not aliases:
        sys.exit(0)  # fail-open
    blocked, target = is_blocked(command, aliases)
    if not blocked:
        sys.exit(0)
    print(
        f"Blocked: raw `ssh {target} … nohup …` bypasses Running Jobs and "
        f"loses provenance.\n\n"
        f"Use the MCP tool instead:\n\n"
        f"  mcp__co_scientist__submit_remote_job(\n"
        f"    slug=..., analysis=..., command=...,\n"
        f"    server_alias=\"{target}\", env_name=..., workers=...,\n"
        f"  )\n\n"
        f"It records the run in analysis_runs and surfaces it in the dashboard.\n\n"
        f"Override (setup work like mkdir / env create): prefix the command with\n"
        f"`# setup` or include `# allow-untracked` anywhere in the command.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

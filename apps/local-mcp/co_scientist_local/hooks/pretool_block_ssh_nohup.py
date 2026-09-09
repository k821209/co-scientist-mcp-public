#!/usr/bin/env python3
"""PreToolUse(Bash) hook: two rules for ssh to a REGISTERED server.

1. No raw `ssh <alias> ... nohup …` — use `submit_remote_job`, so the job is
   tracked in `analysis_runs` and visible in the dashboard's Running Jobs.
2. No `mkdir` / `rsync` / `scp` targeting a path OUTSIDE this project's root
   on that server. Work on servers was landing in folders made up on the
   spot, with no project in the path; the root is
   `<default_workdir>/<project-slug>` (or the project's set_project_workdir
   binding) and `remote_workdir(alias)` tells the agent what it is. Override
   with `# outside-project` in the command, and say why.

The hook reads server aliases from a *local cache file*
(~/.co-scientist/cache/servers.json), refreshed by the local MCP at
startup and after add_server/update_server. The hook deliberately avoids
network calls — they'd slow down every Bash invocation.

Cache file format:
    { "servers": [{"alias": "gpu-box", "host": "192.0.2.10", "user": "alice"}, ...] }

Override prefixes for rule 1 (allow legitimate non-job ssh work):
    `# setup`, `# manual`, or `# allow-untracked` anywhere in the command.
Rule 2 is NOT lifted by `# setup` — setup is exactly when a folder is made —
only by `# outside-project`.

Which project: the id in the CLAUDE.md / AGENTS.md found walking up from cwd
(the same file the MCP checks at startup); the cache carries each project's
root per server under `projects`.

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
OUTSIDE_OVERRIDE = "# outside-project"
_PROJECT_ID_RE = re.compile(r"[Pp]roject\s+id\s*:\s*`([a-zA-Z0-9_-]+)`")
_CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")
# A shell segment that makes a directory or copies files, and the absolute
# paths in it. Segments are split on ; && || | so that `cd /x && mkdir a` is
# judged on the mkdir alone.
_SEG_SPLIT_RE = re.compile(r"\s*(?:;|&&|\|\||\|)\s*")
_MKDIR_RE = re.compile(r"\bmkdir\b(.*)$")
_COPY_RE = re.compile(r"\b(?:rsync|scp)\b(.*)$")
# A path token that starts at a "/" not inside a longer token (`./x`, `a/b`,
# `user@host/x`); `alias:/abs` is allowed through so a copy destination is seen.
_ABS_PATH_RE = re.compile(r"(?<![\w.@/])(/[^\s\"';|&]+)")
_REMOTE_DEST_RE = re.compile(r"^([A-Za-z0-9_.@-]+):(/[^\s\"';|&]*)$")

_BG_RE = re.compile(
    r"\bnohup\b|"
    r"\bdisown\b|"
    # standalone trailing & — whitespace-preceded so `2>&1` doesn't trigger
    r"\s&\s*[\"']?\s*$",
    re.MULTILINE,
)
# Positional parsing of the ssh target was WRONG: `(?:-\S+\s+)*` cannot know
# which options take a separate value, so `ssh -i key alias …`, `ssh -p 2222
# alias …` and `ssh -o k=v alias …` all failed to find the alias and the guard
# silently allowed an untracked job through. Instead: confirm it IS an ssh
# invocation, then look for a registered alias among ALL tokens. Over-matching
# (an alias named as an argument rather than the target) still blocks a
# backgrounded ssh job touching a registered host, which is the thing being
# guarded — and `# allow-untracked` covers the rest.
_SSH_CMD_RE = re.compile(r"^\s*ssh\b", re.MULTILINE)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.@-]+")


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


def load_project_roots() -> dict[str, dict[str, str]]:
    """{project_id: {alias: root}} from the cache; {} when absent."""
    if not CACHE_PATH.is_file():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("projects") or {}


def detect_project_id(cwd: Path) -> str | None:
    for d in [cwd, *cwd.parents]:
        for name in _CONTEXT_FILES:
            f = d / name
            if f.is_file():
                try:
                    m = _PROJECT_ID_RE.search(f.read_text(encoding="utf-8"))
                except OSError:
                    continue
                if m:
                    return m.group(1)
    return None


def _strip_quoted_ssh_payload(command: str) -> str:
    """The remote command is usually one quoted argument; judge its contents
    too, so `ssh box "mkdir -p /elsewhere"` is seen."""
    return command.replace('"', " ").replace("'", " ")


def outside_project(command: str, aliases: set[str], roots: dict[str, str]) -> tuple[str, str, str] | None:
    """(alias, offending path, root) for an ssh mkdir/rsync/scp that leaves the
    project's root on that server; None to allow. Fail-open whenever the root
    for the alias is unknown or the path is not absolute."""
    if OUTSIDE_OVERRIDE in command:
        return None
    if not _SSH_CMD_RE.search(command) and not _COPY_RE.search(command):
        return None
    tokens = _TOKEN_RE.findall(command)
    alias = next((t for t in tokens if t in aliases), None)
    if not alias:
        return None
    root = (roots.get(alias) or "").rstrip("/")
    if not root.startswith("/"):
        return None
    def _outside(path: str) -> bool:
        p = path.rstrip("/") or "/"
        return not (p == root or p.startswith(root + "/"))

    flat = _strip_quoted_ssh_payload(command)
    for seg in _SEG_SPLIT_RE.split(flat):
        m = _COPY_RE.search(seg)
        if m:
            # rsync/scp: the DESTINATION is the last argument, and only a remote
            # one on this alias is ours to judge. Pulling from a shared path is
            # reading, not making a folder.
            args = m.group(1).split()
            if not args:
                continue
            d = _REMOTE_DEST_RE.match(args[-1])
            if d and d.group(1) == alias and d.group(2) and _outside(d.group(2)):
                return alias, d.group(2), root
            continue
        m = _MKDIR_RE.search(seg)
        if not m:
            continue
        for path in _ABS_PATH_RE.findall(m.group(1)):
            if _outside(path):
                return alias, path, root
    return None


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
    if not _SSH_CMD_RE.search(command):
        return False, None
    for token in _TOKEN_RE.findall(command):
        if token in aliases:
            return True, token
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
    # Rule 2: a directory outside this project's root on a registered server.
    pid = detect_project_id(Path(data.get("cwd") or os.getcwd()))
    roots = load_project_roots().get(pid or "", {})
    hit = outside_project(command, aliases, roots) if roots else None
    if hit:
        alias, path, root = hit
        print(
            f"Blocked: `{path}` on {alias} is outside this project's directory "
            f"there, `{root}`.\n\n"
            f"Every folder this project makes on a server lives under that root "
            f"(runs in {root}/analysis/<name>). Ask "
            f"mcp__co_scientist__remote_workdir(\"{alias}\") for the path and use it; "
            f"to bind a different root for this project, set_project_workdir(...).\n\n"
            f"If this really must live elsewhere (shared reference data, say), add "
            f"`# outside-project` to the command and say why.",
            file=sys.stderr,
        )
        sys.exit(2)
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

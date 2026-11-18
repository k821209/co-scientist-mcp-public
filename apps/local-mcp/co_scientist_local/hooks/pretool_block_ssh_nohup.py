#!/usr/bin/env python3
"""PreToolUse(Bash) hook: two rules for ssh to a REGISTERED server.

1. No raw `ssh <alias> ... nohup …` — use `submit_remote_job`, so the job has
   a run record and is visible in the dashboard's Running Jobs.
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
from typing import Any

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

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.@-]+")
# Rule 2 only: is there an ssh or a copy on the line at all.
_SSH_CMD_RE = re.compile(r"^\s*ssh\b", re.MULTILINE)

# ── what a line RUNS through ssh ─────────────────────────────────────────────
# This used to ask two questions of the whole text: is there a line that
# STARTS with `ssh`, and is there a `nohup` / `disown` / trailing `&` anywhere.
# Replayed over the scenario corpus the scivo-harness guard is measured with
# (tests/data/guard_scenarios.json, 2026-11-19), it stopped nothing it should
# not have — and let 16 of 29 launches through: `cd x && ssh gpu "nohup …"`,
# a launch in a loop or an `if`, behind `timeout` or an environment
# assignment, through `bash -c`, `gcloud compute ssh`, `sshpass`, a detached
# tmux or screen, `setsid`. A session that put anything before the `ssh` on
# the line was not guarded at all.
#
# So the line is read the way the shell reads it — the same reader as the
# harness's guardrails.py, carried here because a hook is one file with no
# imports beyond the standard library. It is cut into commands at the unquoted
# `;`, `|`, `&&`, `&`, newlines, `$( )` and backticks; a command is a remote
# call when `ssh` stands in it as a word of its own; and what follows that
# word, with a heredoc fed to it, is what is checked. The two copies are held
# together by the corpus, which both test suites replay.
#
# A heredoc written to a FILE is data, and is dropped before any of this.
_HEREDOC = re.compile(
    r"""<<-?\s*(['"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1   # <<EOF / <<'EOF' / <<-EOF
        (?P<body>.*?)                                     # everything up to …
        ^[ \t]*(?P=tag)[ \t]*$                            # … the closing tag on its own line
    """,
    re.DOTALL | re.MULTILINE | re.VERBOSE,
)


# Where one command ends and the next begins, so the head of the heredoc's own
# command can be read.
_SEPARATOR = re.compile(r"(?:\n|;|\|\||&&|\|)")


def executable_text(command: str) -> str:
    """The command with heredoc bodies removed, for the pattern checks.

    A body is removed only when it is DATA. `ssh host bash <<EOF … EOF` feeds
    its body to a remote shell, so there the body IS the command and stripping
    it would hide the very thing the guard exists for — which is what the first
    attempt at this did, caught by the suite.
    """
    def keep_or_drop(match: re.Match) -> str:
        head = command[:match.start()]
        last = _SEPARATOR.split(head)[-1] if head else ""
        if re.search(r"\bssh\b", last):
            return match.group(0)          # the body is the remote command
        return "<<" + match.group("tag") + "\n" + match.group("tag")

    return _HEREDOC.sub(keep_or_drop, command)




_REMOTE_PROGRAMS = frozenset({"ssh", "autossh", "mosh"})
# Programs whose arguments are text to show or to look for, never to run.
_TEXT_PROGRAMS = frozenset({
    "echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "man", "which", "type", "whatis",
    "apropos", "apt", "apt-get", "dnf", "yum", "brew", "pip", "pip3",
})
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_KEYWORDS = frozenset({"do", "then", "else", "elif", "if", "while", "until", "time", "!", "{", "}"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_DETACHES = re.compile(
    r"\bnohup\b|\bsetsid\b|\bdisown\b|\bscreen\s+-d\w*"
    r"|\btmux\s+new(?:-session)?\b[^\n]*?\s-d\b|(?<![&|<>])&(?![&|>])",
    re.IGNORECASE)
_PATTERN_MATCH = re.compile(
    r"\b(pgrep|pkill)\s+(?:-{1,2}[\w-]+\s+)*(?:-\w*f\w*|--full)(?=\s|$)", re.IGNORECASE)
_NESTING_LIMIT = 4


class _Unreadable(Exception):
    """The line cannot be cut into commands with any confidence."""


def _commands(line: str) -> list[dict[str, Any]]:
    """The line as the shell would cut it: one entry per simple command.

    `words` are (text with its quotes removed, whether any of it was quoted,
    where it starts); `stop` is where the command ends in the line;
    `background` says an unquoted `&` ended it; `payload` is the heredoc fed to it; `inner` holds what stands in
    `$( )` or backticks inside its double-quoted words, to be read in turn.
    """
    out: list[dict[str, Any]] = []
    n = len(line)
    i = 0
    start = 0
    words: list[tuple[str, bool, int]] = []
    inner: list[str] = []
    pending: list[tuple[str, bool]] = []     # heredocs opened on this line: (tag, body kept?)
    word: list[str] | None = None
    quoted = False
    word_at = 0

    def end_word() -> None:
        nonlocal word, quoted
        if word is not None:
            words.append(("".join(word), quoted, word_at))
        word, quoted = None, False

    def end_command(stop: int, background: bool = False) -> None:
        nonlocal words, inner, start
        end_word()
        if words:
            out.append({"words": words, "stop": stop, "background": background,
                        "inner": inner, "payload": ""})
        words, inner, start = [], [], stop

    def substitution(at: int) -> int:
        """`at` is just past `$(`: the index just past its closing `)`."""
        depth, j = 1, at
        while j < n:
            if line[j] == "\\":
                j += 2
                continue
            if line[j] == "(":
                depth += 1
            elif line[j] == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        raise _Unreadable("a $( that never closes")

    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n:
            if word is None:
                word, word_at = [], i
            if line[i + 1] != "\n":
                word.append(line[i + 1])
            i += 2
            continue
        if ch == "'":
            close = line.find("'", i + 1)
            if close < 0:
                raise _Unreadable("a ' that never closes")
            if word is None:
                word, word_at = [], i
            word.append(line[i + 1:close])
            quoted = True
            i = close + 1
            continue
        if ch == '"':
            if word is None:
                word, word_at = [], i
            quoted = True
            j = i + 1
            while True:
                if j >= n:
                    raise _Unreadable('a " that never closes')
                if line[j] == "\\" and j + 1 < n:
                    word.append(line[j + 1])
                    j += 2
                elif line[j] == '"':
                    break
                elif line.startswith("$(", j):
                    close = substitution(j + 2)
                    inner.append(line[j + 2:close - 1])
                    word.append(line[j:close])
                    j = close
                elif line[j] == "`":
                    close = line.find("`", j + 1)
                    if close < 0:
                        raise _Unreadable("a ` that never closes")
                    inner.append(line[j + 1:close])
                    word.append(line[j:close + 1])
                    j = close + 1
                else:
                    word.append(line[j])
                    j += 1
            i = j + 1
            continue
        if ch == "#" and word is None:
            stop = line.find("\n", i)
            i = n if stop < 0 else stop
            continue
        if line.startswith("$(", i):
            close = substitution(i + 2)
            inner.append(line[i + 2:close - 1])
            if word is None:
                word, word_at = [], i
            word.append(line[i:close])
            quoted = True                       # a substituted word is not a literal one
            i = close
            continue
        if ch == "`":
            close = line.find("`", i + 1)
            if close < 0:
                raise _Unreadable("a ` that never closes")
            inner.append(line[i + 1:close])
            if word is None:
                word, word_at = [], i
            word.append(line[i:close + 1])
            quoted = True
            i = close + 1
            continue
        if line.startswith("<<", i) and not line.startswith("<<<", i):
            match = re.match(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line[i:])
            if match:
                end_word()
                pending.append((match.group(2), True))
                i += match.end()
                continue
        if ch == "\n":
            if pending:
                # The lines up to each tag are the heredoc's, not commands.
                # They belong to the command that opened it.
                end_word()
                body_from = i + 1
                at = body_from
                for tag, _kept in pending:
                    found = re.compile(rf"^[ \t]*{re.escape(tag)}[ \t]*$", re.M).search(line, at)
                    if not found:
                        raise _Unreadable("a heredoc that never closes")
                    at = found.end()
                if words:
                    out.append({"words": words, "stop": i, "background": False,
                                "inner": inner, "payload": line[body_from:at]})
                words, inner, pending = [], [], []
                i = start = at
                continue
            end_command(i)
            i += 1
            start = i
            continue
        if ch in " \t":
            end_word()
            i += 1
            continue
        if ch == ";":
            end_command(i)
            i += 1
            start = i
            continue
        if ch == "|":
            end_command(i)
            i += 1
            start = i
            continue
        if ch == "&":
            before = line[i - 1] if i else ""
            after = line[i + 1] if i + 1 < n else ""
            if after == "&":
                end_command(i)
                i += 2
                start = i
                continue
            if before in "<>" or after == ">":
                if word is None:
                    word, word_at = [], i
                word.append(ch)                  # part of a redirection: 2>&1, &>file
                i += 1
                continue
            end_command(i, background=True)
            i += 1
            start = i
            continue
        if ch in "()":
            end_command(i)
            i += 1
            start = i
            continue
        if word is None:
            word, word_at = [], i
        word.append(ch)
        i += 1
    if pending:
        raise _Unreadable("a heredoc that never closes")
    end_command(n)
    return out


def remote_calls(line: str, _depth: int = 0) -> list[dict[str, Any]]:
    """What this line hands to a remote machine, one entry per `ssh` it runs:
    `remote` is the text that goes with it, `background` whether the ssh
    itself is left running here. Raises `_Unreadable` when it cannot tell."""
    if _depth > _NESTING_LIMIT:
        raise _Unreadable("nested too deep to follow")
    found: list[dict[str, Any]] = []
    for command in _commands(line):
        for text in command["inner"]:
            found += remote_calls(text, _depth + 1)
        words = list(command["words"])
        # `do ssh …`, `VAR=value ssh …`: the command proper starts after these.
        while words and ((words[0][0] in _KEYWORDS and not words[0][1])
                         or _ASSIGNMENT.match(words[0][0])):
            words.pop(0)
        if not words:
            continue
        program = words[0][0].rsplit("/", 1)[-1].lower()
        if program in _SHELLS or program == "eval":
            # One shell deeper: its `-c` string (or eval's arguments) is a line to read.
            rest = [text for text, _quoted, _at in words[1:]]
            scripts = rest if program == "eval" else [
                rest[k + 1] for k, text in enumerate(rest[:-1]) if re.fullmatch(r"-[a-z]*c", text)]
            for script in scripts:
                found += remote_calls(script, _depth + 1)
        if program in _TEXT_PROGRAMS:
            continue
        for position, (text, was_quoted, at) in enumerate(words):
            if text.rsplit("/", 1)[-1].lower() not in _REMOTE_PROGRAMS:
                continue
            # As an argument, a quoted "ssh" is a string someone is passing
            # along. As the program, quoted or not, it is what runs: `"ssh"
            # host …` is still an ssh.
            if was_quoted and position:
                continue
            # `nohup ssh …`, `setsid ssh …`: left running from this side.
            ahead = " ".join(w for w, q, a in words if a < at and not q)
            found.append({
                "remote": line[at:command["stop"]] + "\n" + command["payload"],
                "background": command["background"]
                              or bool(re.search(r"\b(nohup|setsid)\b", ahead, re.I)),
            })
            break
    return found




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
    """(blocked, the registered server it reaches). A launch on a machine that
    is not in the registry is not this hook's to stop: it has no Runs tab row
    to be missing from."""
    if has_override(command):
        return False, None
    text = executable_text(command)
    everywhere = _TOKEN_RE.findall(text)
    try:
        calls = remote_calls(text)
    except Exception:  # noqa: BLE001 — a line that cannot be read, or a reader that fails
        # Never a pass: the whole line, by the words alone.
        if re.search(r"\bssh\b", text, re.I) and _DETACHES.search(text):
            return next(((True, token) for token in everywhere if token in aliases), (False, None))
        return False, None
    for call in calls:
        if not (call["background"] or _DETACHES.search(call["remote"])):
            continue
        tokens = _TOKEN_RE.findall(call["remote"])
        # `ssh $h …` in a loop names its machines somewhere else on the line.
        if "$" in call["remote"]:
            tokens += everywhere
        for token in tokens:
            if token in aliases:
                return True, token
    return False, None


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)
    # scivo-harness enforces these rules itself, in process, and more of them.
    # A project wired for Claude Code is often opened in the harness too; both
    # running would refuse one command twice, in two wordings.
    if os.environ.get("SCIVO_HARNESS"):
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
            f"mcp__scivo__remote_workdir(\"{alias}\") for the path and use it; "
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
        f"  mcp__scivo__submit_remote_job(\n"
        f"    slug=..., analysis=..., command=...,\n"
        f"    server_alias=\"{target}\", env_name=..., workers=...,\n"
        f"  )\n\n"
        f"It records the run (list_analysis_runs shows it) and surfaces it in the dashboard.\n\n"
        f"Override (setup work like mkdir / env create): prefix the command with\n"
        f"`# setup` or include `# allow-untracked` anywhere in the command.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

"""Whose exit status a job's exit code is.

A run row's `exit_code` is the status of the shell line that was launched, and
a shell line's status is the status of its LAST command. So

    boltz predict in.yaml; ls out/*; echo ALL DONE

exits 0 when `boltz` died with a traceback: `;` runs the next command whatever
the one before did, and `echo` does not fail. The row then says "finished,
exit 0", and nothing downstream — the Runs tab, `wait_for_run`, an export's
provenance — can tell it from a run that worked (feedback 99b682e3ce17).

This reads a command line far enough to say when that is the case, for three
shapes that are unambiguous:

    … ; echo done          the last command only reports
    … || true              a failure is turned into success
    … | tee log            the status is tee's, not the program's

It does not run a shell and does not try to: a line it cannot read (a heredoc,
an unbalanced quote) gets no verdict, and no verdict is not "fine" — the caller
says nothing rather than "checked".
"""
from __future__ import annotations

import re

# Commands that say something and cannot fail in a way that is about the work.
_REPORTERS = frozenset({
    "echo", "printf", "ls", "date", "true", ":", "pwd", "hostname", "sync",
    "touch", "sleep", "du", "df", "wc", "cat", "head", "tail",
})
_SET_E = re.compile(r"^set\s+(?:-[a-zA-Z]*e[a-zA-Z]*\b|(?:-[a-zA-Z]+\s+)*-o\s+errexit\b)")
_PIPEFAIL = re.compile(r"^set\s+.*\bpipefail\b")


def _split(line: str) -> list[tuple[str, str]] | None:
    """Top-level pieces of a shell line as (text, separator after it), where
    the separator is one of `;` `&&` `||` `|` `&` or "" at the end. Newlines
    count as `;`. None when the line cannot be read."""
    if "<<" in line:
        return None
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    quote = ""
    depth = 0
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < n:
                buf.append(line[i:i + 2]); i += 2; continue
            if c == quote:
                quote = ""
            buf.append(c); i += 1; continue
        if c == "\\" and i + 1 < n:
            buf.append(line[i:i + 2]); i += 2; continue
        if c in "'\"`":
            quote = c; buf.append(c); i += 1; continue
        if c in "({":
            # `{` opens a group only as a word of its own; `${x}` and `a{b,c}`
            # are not groups, and counting them is harmless: they close.
            depth += 1; buf.append(c); i += 1; continue
        if c in ")}":
            depth -= 1
            if depth < 0:
                return None
            buf.append(c); i += 1; continue
        if depth == 0:
            two = line[i:i + 2]
            if two in ("&&", "||"):
                out.append(("".join(buf).strip(), two)); buf = []; i += 2; continue
            if c in ";\n|&":
                if c == "&" and (buf and buf[-1] in "<>" or line[i + 1:i + 2] == ">"):
                    buf.append(c); i += 1; continue          # 2>&1, &>file
                out.append(("".join(buf).strip(), ";" if c == "\n" else c)); buf = []; i += 1; continue
        buf.append(c); i += 1
    if quote or depth != 0:
        return None
    out.append(("".join(buf).strip(), ""))
    # `a; ;` and a trailing `;` leave empty pieces: the separator before them
    # is what matters, and it is already on the piece before.
    return [(text, sep) for text, sep in out if text]


def _word(command: str) -> str:
    """The command's name: past any `VAR=value` in front of it."""
    for token in command.split():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            continue
        return token
    return ""


def status_is_of(command: str | None) -> dict | None:
    """When the line's exit status says nothing about the work, which command
    it belongs to and why. None when it is the work's own — or when the line
    could not be read."""
    pieces = _split(command or "")
    if not pieces or len(pieces) < 2:
        return None
    texts = [text for text, _sep in pieces]
    before_last = pieces[-2][1]
    last = texts[-1]
    errexit = any(_SET_E.match(text) for text in texts[:-1])
    pipefail = any(_PIPEFAIL.match(text) for text in texts[:-1])
    if before_last == "|" and _word(last) == "tee" and not pipefail:
        return {"of": last[:80], "how": "pipe",
                "why": (f"a pipeline's status is its last command's — `{_word(last)}`, "
                        "not the program writing into it")}
    if before_last == "||" and _word(last) in _REPORTERS:
        return {"of": last[:80], "how": "or",
                "why": f"`|| {last[:40]}` turns a failure into exit 0"}
    if before_last == ";" and _word(last) in _REPORTERS and not errexit:
        return {"of": last[:80], "how": "last",
                "why": (f"`;` runs `{last[:40]}` whatever the command before it did, "
                        "and the line's status is that last command's")}
    return None


def launch_warning(command: str | None) -> str | None:
    """Said when a job is launched."""
    found = status_is_of(command)
    if not found:
        return None
    fix = {"last": "join the steps with `&&`, or start the line with `set -e;`",
           "or": "drop it, or let the failure through",
           "pipe": "start the line with `set -o pipefail;`, or redirect to the file instead"}[found["how"]]
    return (f"this run's exit code will NOT say whether the work succeeded: {found['why']}. "
            f"A crash will be recorded as exit 0. To have the row tell the truth, {fix}.")


def finished_caution(command: str | None, exit_code) -> str | None:
    """Said when a run that exited 0 is read back."""
    if exit_code != 0:
        return None
    found = status_is_of(command)
    if not found:
        return None
    return (f"exit 0 here is the status of `{found['of']}`, not of the work — {found['why']}. "
            "Read the log before reporting a result; if it failed, correct the row with "
            "update_analysis_run(exit_code=…, notes=…).")

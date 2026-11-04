"""One line per outbound call we make, so a dropped link has evidence.

The wifi drops, repeatedly, and the honest answer to "are we flooding it?" is
that nobody knows: the tools make short SSH calls, a wait polls `ps` every 15
seconds, OpenSSH's own master sends a keepalive every 15 seconds for half an
hour after any call, and none of it is recorded anywhere. So the fix is not a
fix yet — it is a log, and then a measurement (todo d27e0606a7bb).

What a line carries: when, what kind of call, which host, how long it took,
whether it worked, and — the one that matters here — whether the multiplexed
master was already up or this call paid for a login. A run of `fresh` lines
means the master keeps dying, which is the expensive case on a flaky link.

What a line NEVER carries: the command. A command we send can contain a run's
report token (the reporter script is written over SSH with a heredoc), and a
local log is exactly where a secret should not end up. Only a short KIND, read
off the command by `classify`, and its length.

Off by default is wrong here — the drop is already happening and the log is
cheap — so it is on, and `SCIVO_NETLOG=off` turns it off. It never raises: a
logging failure that breaks a remote job would be worse than no log.
"""
from __future__ import annotations

import os
import pathlib
import re
import time

_MAX_BYTES = 2_000_000          # ~20k lines, then it starts a new file
_OFF = ("off", "0", "no", "false")

# Read off the command, longest first. Anything unrecognised is "other" — a
# name is for finding a pattern in the log, not for describing the command.
_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ps-probe", re.compile(r"__cosci_ps__|\bps -p\b")),
    ("status", re.compile(r"---uptime---|\buptime\b")),
    ("write-reporter", re.compile(r"SCIVO_REPORTER_EOF")),
    ("hash-probe", re.compile(r"maxdepth 1 -type f|sha256sum")),
    ("launch", re.compile(r"\bnohup bash\b")),
    ("tail", re.compile(r"\btail -n\b")),
    ("mkdir", re.compile(r"\bmkdir -p\b")),
    ("kill", re.compile(r"\bkill -\b|\bpkill\b")),
    ("nvidia", re.compile(r"\bnvidia-smi\b")),
)


def classify(command: str) -> str:
    """A short kind for a command, carrying none of its text."""
    text = command or ""
    for name, pattern in _KINDS:
        if pattern.search(text):
            return name
    return "other"


def enabled() -> bool:
    return (os.environ.get("SCIVO_NETLOG", "").strip().lower() or "on") not in _OFF


def path() -> pathlib.Path:
    # The literal, not a constant: tests/test_skill_audit.py reads this file
    # to check that every host forwards every variable the MCP reads, and an
    # indirection hides the read from it.
    override = os.environ.get("SCIVO_NETLOG_PATH")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path.home() / ".co-scientist" / "net.log"


def record(channel: str, *, host: str = "", kind: str = "", ms: int = 0,
           rc: int | None = None, fresh: bool | None = None,
           note: str = "") -> None:
    """Append one line. Never raises, never writes a command or a secret."""
    if not enabled():
        return
    try:
        line = "\t".join((
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
            channel,
            host[:40],
            kind[:20],
            str(int(ms)),
            "-" if rc is None else str(rc),
            "-" if fresh is None else ("fresh" if fresh else "reused"),
            re.sub(r"\s+", " ", note)[:120],
        ))
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.stat().st_size > _MAX_BYTES:
                target.replace(target.with_suffix(target.suffix + ".1"))
        except OSError:
            pass
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — a log must not break a remote job
        return

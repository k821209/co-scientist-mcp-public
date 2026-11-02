"""Is this working directory the Scivo source checkout?

`list_feedback` lists ONE project's items, which is the right answer for the
person whose project it is and the wrong answer for whoever maintains Scivo:
users file feedback from their own projects, so the maintainer's queue is
account-wide and lives behind a collectionGroup (the dashboard's Admin tab).
The two callers type the same session-start protocol — the generated CLAUDE.md
— so nothing distinguished them, and four open reports were answered with "0
open" twice in one session.

The distinction is the FOLDER. A marker file at the top of the source checkout
designates it, so the maintainer's protocol can differ without a privileged
branch in anyone's install: the code below ships to everyone and is inert
without the marker, and the marker is not published.

The marker carries NO credential. Reading the account-wide queue needs a
service account that lives outside the repo and never enters it; the marker
only says which protocol applies and where the queue reader is.
"""
from __future__ import annotations

import pathlib
import socket

MARKER = ".scivo-maintainer"
_MAX_PARENTS = 6


def _parse(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def find_marker(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """The marker at or above `start` (default: the process's cwd).

    Walks up a bounded number of parents so a session opened in `apps/web` or
    `tests` still finds it, and so a session anywhere else does not pay for a
    walk to the filesystem root.
    """
    here = (start or pathlib.Path.cwd()).resolve()
    for d in [here, *list(here.parents)[:_MAX_PARENTS]]:
        candidate = d / MARKER
        if candidate.is_file():
            return candidate
    return None


def detect(start: pathlib.Path | None = None, *, hostname: str | None = None) -> dict | None:
    """What the marker says, or None when this is an ordinary project folder.

    `canonical_path` / `canonical_host` are how a MOVED or CLONED checkout is
    caught: a stale clone carries the marker too, and acting as the maintainer
    from one has already reverted shipped work. A mismatch is reported, not
    silently honoured — and `canonical_path` is the one line to edit when the
    real checkout moves.
    """
    marker = find_marker(start)
    if marker is None:
        return None
    try:
        fields = _parse(marker.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None

    root = marker.parent
    out: dict = {"checkout": str(root), "queue": fields.get("queue") or None}
    mismatches: list[str] = []

    canonical_path = fields.get("canonical_path")
    if canonical_path and str(root) != str(pathlib.Path(canonical_path)):
        mismatches.append(f"this checkout is {root}, the marker names {canonical_path}")
    canonical_host = fields.get("canonical_host")
    if canonical_host and (hostname or socket.gethostname()) != canonical_host:
        mismatches.append(
            f"this host is {hostname or socket.gethostname()}, "
            f"the marker names {canonical_host}")

    if mismatches:
        out["canonical"] = False
        out["note"] = (
            "NOT the canonical Scivo checkout — " + "; ".join(mismatches)
            + ". Work published from a stale clone has reverted shipped changes "
              "before. Verify before deploying, or update canonical_path/"
              "canonical_host in " + MARKER + " if the checkout really moved.")
    else:
        out["canonical"] = True
        queue = out["queue"] or "scripts/triage_feedback.py"
        out["note"] = (
            "This is the Scivo source checkout, so you are the MAINTAINER here. "
            f"A feedback check means the whole account's queue — `{queue}` — not "
            "`list_feedback`, which lists this project only and will say 0 open "
            "while other projects' reports wait.")
    return out

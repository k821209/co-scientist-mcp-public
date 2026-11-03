"""Project to-do list — shared task tracker in Firestore.

A lightweight checklist scoped to the whole project (not a single paper), so
the agent and the human collaborator share one view of what's planned, in
progress, and done. Surfaced on the dashboard's Activity tab alongside the
timeline.

Path:
    /projects/{pid}/todos/{id}

Each entry: { text, status, paper_slug, actor, created_at, updated_at }
where status is one of "open" | "in_progress" | "done".

Adding a todo and marking one done also drop an entry on the project timeline
(via activity.log_timeline), so progress shows up in the unified feed.
"""
from __future__ import annotations

from ..state import State
from ..util import new_id, now_iso
from .activity import log_timeline

_STATUSES = {"open", "in_progress", "done"}


def add_todo(state: State, text: str, paper_slug: str | None = None) -> dict:
    """Create a to-do item for the project. Returns the created item."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    now = now_iso()
    tid = new_id()
    doc = {
        "text": text,
        "status": "open",
        "paper_slug": paper_slug,
        "actor": "claude",
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(state.project_path("todos", tid), doc)
    log_timeline(state, event_type="todo_added", title=text, paper_slug=paper_slug)
    return {"id": tid, **doc}


def list_todos(state: State, status: str | None = None) -> list[dict]:
    """List the project's to-do items, oldest first. Optionally filter by
    status ("open" | "in_progress" | "done")."""
    if status is not None and status not in _STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    items = state.backend.list_collection(state.project_path("todos"))
    out = [{"id": i, **d} for i, d in items]
    if status is not None:
        out = [t for t in out if t.get("status") == status]
    out.sort(key=lambda t: t.get("created_at") or "")
    return out


def update_todo(
    state: State,
    todo_id: str,
    status: str | None = None,
    text: str | None = None,
) -> dict:
    """Update a to-do's status and/or text. Returns the updated item."""
    if status is None and text is None:
        raise ValueError("nothing to update: pass status and/or text")
    path = state.project_path("todos", todo_id)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise ValueError(f"todo {todo_id!r} not found")
    fields: dict = {"updated_at": now_iso()}
    if status is not None:
        if status not in _STATUSES:
            raise ValueError(f"invalid status: {status!r}")
        fields["status"] = status
    if text is not None:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text cannot be empty")
        fields["text"] = cleaned
    state.backend.update_doc(path, fields)
    merged = {**existing, **fields, "id": todo_id}
    if status == "done":
        log_timeline(
            state, event_type="todo_done",
            title=merged.get("text", ""), paper_slug=merged.get("paper_slug"),
        )
    return merged


# ── a promise nobody can check is a promise that does not get kept ────────

PROMISE_STALE_DAYS = 3.0


def _latest_run_at(state: State) -> str | None:
    """When anything was last recorded as RUN in this project, across papers."""
    from . import analyses as _analyses
    from . import runs as _runs

    latest = None
    for slug, name in _analyses.iter_analyses(state):
        for row in _runs.list_analysis_runs(state, slug, name):
            when = row.get("started_at") or row.get("created_at")
            if when and (latest is None or when > latest):
                latest = when
    return latest


def promise_check(state: State, *, stale_days: float = PROMISE_STALE_DAYS) -> dict:
    """Open to-dos old enough that work was promised and not done.

    The failure this exists for: the paper's central question was memory, 160
    hifiasm runs went out with no `/usr/bin/time -v`, and "we have to measure
    max RSS" was written into FOUR places — a run note, a concept graph, two
    discussion comments — and never run (feedback 89a37dd28ffc). Prose cannot
    be checked by anything; a to-do row can. The convention that makes this
    work lives in the guide: a sentence that promises work becomes a to-do in
    the SAME turn.

    The harness already lists open to-dos at session start, flat and without
    ages, where a six-day-old promise reads exactly like a note made a minute
    ago. This is the other half: at the export gate, with how long it has been
    open and whether anything has run since.

    Reported, not forbidden. A to-do is project-wide and can be legitimately
    open at export ("email the coauthors"), so this names the oldest and says
    what it knows — it is not a judgement about whether the paper may ship.
    """
    from datetime import datetime, timezone

    def _dt(value) -> "datetime | None":
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    open_items = [t for t in list_todos(state) if (t.get("status") or "open") != "done"]
    aged = []
    for item in open_items:
        created = _dt(item.get("created_at"))
        if created is None:
            continue
        days = (now - created).total_seconds() / 86400.0
        if days >= stale_days:
            aged.append({"text": item.get("text") or "", "days_open": round(days, 1),
                         "created_at": item.get("created_at"),
                         "paper_slug": item.get("paper_slug")})
    aged.sort(key=lambda a: a["days_open"], reverse=True)
    base = {"name": "open_promises",
            "label": "Work promised in a to-do and still open",
            "kind": "promise", "open_todos": len(open_items),
            "stale_days": stale_days, "stale": aged}
    if not aged:
        return {**base, "ok": True, "message": None}

    oldest = aged[0]
    last_run = _latest_run_at(state)
    created = _dt(oldest["created_at"])
    nothing_since = bool(created) and (not last_run or (_dt(last_run) or now) <= created)
    since = ("and NOTHING has been recorded as run in this project since it was "
             "written" if nothing_since else
             f"(the last recorded run was {str(last_run)[:10]})")
    shown = "; ".join(f"{a['days_open']:.0f}d: {a['text'][:70]}" for a in aged[:3])
    return {**base, "ok": False, "message": (
        f"{len(aged)} to-do(s) open for {stale_days:.0f}+ days — {shown}"
        + (f" (+{len(aged) - 3} more)" if len(aged) > 3 else "")
        + f". The oldest has been open {oldest['days_open']:.0f} days {since}. "
        f"Close what is done (`update_todo(status=\"done\")`) and do, or "
        f"explicitly drop, what is not: a measurement promised and never taken "
        f"leaves no trace in the manuscript that any other check can find.")}

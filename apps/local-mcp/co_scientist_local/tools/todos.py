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

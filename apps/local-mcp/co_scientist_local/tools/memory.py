"""Per-project memory — durable project knowledge in Firestore.

A co-scientist project accumulates 'soft' knowledge that the structured
data (papers, sections, reviews, figures) doesn't capture: the user's
writing preferences, decisions taken and why, approaches tried and
rejected, domain gotchas, target-journal history.

This module stores that as a single markdown document at
  /projects/{pid}/memory/main
so it survives a machine change / reinstall, is shared across the
project, and is visible + editable in the dashboard's Memory tab.

It is the cloud-backed *source of truth* for project knowledge — the
agent guide directs the agent to read it at session start and append to
it. (Claude Code's own local auto-memory is a separate harness feature;
project knowledge belongs here.)
"""
from __future__ import annotations

from ..state import State
from ..util import now_iso

_MEMORY_DOC = ("memory", "main")


def get_project_memory(state: State) -> dict:
    """Return the project memory: {content, updated_at, updated_by}.
    `content` is "" when nothing has been recorded yet."""
    doc = state.backend.get_doc(state.project_path(*_MEMORY_DOC))
    if doc is None:
        return {"content": "", "updated_at": None, "updated_by": None}
    return {
        "content": doc.get("content", ""),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


def update_project_memory(state: State, content: str) -> dict:
    """Replace the whole project memory document with `content`."""
    path = state.project_path(*_MEMORY_DOC)
    existing = state.backend.get_doc(path) or {}
    now = now_iso()
    state.backend.set_doc(path, {
        "content": content,
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "updated_by": "claude",
    })
    return get_project_memory(state)


def append_project_memory(state: State, note: str) -> dict:
    """Append `note` to the project memory as a new line. Convenience over
    get + update when you're just adding one durable fact."""
    if not note or not note.strip():
        raise ValueError("note is empty")
    current = get_project_memory(state)["content"]
    note = note.strip()
    combined = f"{current.rstrip()}\n{note}" if current.strip() else note
    return update_project_memory(state, combined)

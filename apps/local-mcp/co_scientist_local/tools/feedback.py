"""Project feedback — bug / error / feature reports.

Filed by the human (dashboard) OR the agent (`report_feedback`), collected per
project at /projects/{pid}/feedback/{id} and triaged by an admin across every
project (collectionGroup). `project_id` is denormalized so the admin view
knows where each item came from.

Each item: { feedback_id, project_id, source, reporter, type, title, body,
status, priority, dev_note, created_at, updated_at, addressed_at }.
"""
from __future__ import annotations

from ..state import State
from ..util import new_id, now_iso

_VALID_TYPES = {"bug", "error", "feature", "other"}


def _feedback_path(state: State, feedback_id: str) -> str:
    return state.project_path("feedback", feedback_id)


def report_feedback(
    state: State,
    *,
    type: str,
    title: str,
    body: str | None = None,
) -> dict:
    """File a feedback item for this project as the agent (source='agent').

    `type` is one of bug | error | feature | other. Use when you hit a tool
    bug, a missing capability, or the user reports a problem you want the
    developer to triage. It shows in the dashboard's Feedback tab and the
    admin triage view."""
    t = (type or "").strip().lower()
    if t not in _VALID_TYPES:
        raise ValueError(f"type must be one of {sorted(_VALID_TYPES)}, got {type!r}")
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    fid = new_id()
    now = now_iso()
    doc = {
        "feedback_id": fid,
        "project_id": state.project_id,
        "source": "agent",
        "reporter": "Claude Code",
        "type": t,
        "title": title,
        "body": (body or "").strip(),
        "status": "open",
        "priority": "none",
        "dev_note": None,
        "created_at": now,
        "updated_at": now,
        "addressed_at": None,
    }
    state.backend.set_doc(_feedback_path(state, fid), doc)
    return {**doc, "dashboard_url": state.dashboard_url("feedback")}


def list_feedback(state: State, status: str | None = None) -> list[dict]:
    """List this project's feedback items, newest first. Optionally filter by
    status (open | in_progress | addressed | declined). Check before filing a
    duplicate."""
    items = state.backend.list_collection(state.project_path("feedback"))
    out = [{"id": i, **d} for i, d in items]
    if status is not None:
        out = [f for f in out if f.get("status") == status]
    out.sort(key=lambda f: f.get("created_at") or "", reverse=True)
    return out

"""Project feedback — bug / error / feature reports.

Filed by the human (dashboard) OR the agent (`report_feedback`), collected per
project at /projects/{pid}/feedback/{id} and triaged by an admin across every
project (collectionGroup). `project_id` is denormalized so the admin view
knows where each item came from.

Each item: { feedback_id, project_id, source, reporter, type, title, body,
status, priority, dev_note, operating_version, created_at, updated_at,
addressed_at }. `operating_version` (agent-filed) records the reporter's MCP +
guide build so the triager can tell "already fixed in a newer build" from a
real current gap.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..guide import GUIDE_VERSION
from ..state import State
from ..util import new_id, now_iso
from ..version_check import git_sha, installed_version


def _operating_version() -> str:
    """Reporter's operating version — MCP package (+ git sha) + guide — so the
    triager can tell "already fixed in a newer build" from "real current gap".
    The sha is what actually pins the build (pyproject version is 0.0.1 for
    source installs and collides for same-day publishes)."""
    pkg = installed_version() or "unknown"
    sha = git_sha()
    mcp = f"{pkg}+g{sha}" if sha else pkg
    return f"mcp={mcp} guide={GUIDE_VERSION}"

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
        "operating_version": _operating_version(),
        "created_at": now,
        "updated_at": now,
        "addressed_at": None,
    }
    state.backend.set_doc(_feedback_path(state, fid), doc)
    return {**doc, "dashboard_url": state.dashboard_url("feedback")}


def update_feedback(
    state: State,
    feedback_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    type: str | None = None,
) -> dict:
    """Edit an agent-filed feedback item — fix a mistake or, importantly, remove
    sensitive info you included by accident (a secret, a private host/SSH
    address). Only `source='agent'` items can be edited; priority / dev_note are
    admin-managed and left untouched. Editing an already-addressed/declined item
    RE-OPENS it (status→open, addressed_at cleared) so the update re-enters
    triage — a report edited with new info shouldn't stay hidden."""
    path = _feedback_path(state, feedback_id)
    doc = state.backend.get_doc(path)
    if doc is None:
        raise NotFound(f"feedback not found: {feedback_id!r}")
    if doc.get("source") != "agent":
        raise ValueError("can only edit agent-filed feedback (source='agent')")
    fields: dict = {}
    if type is not None:
        t = type.strip().lower()
        if t not in _VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(_VALID_TYPES)}, got {type!r}")
        fields["type"] = t
    if title is not None:
        title = title.strip()
        if not title:
            raise ValueError("title cannot be empty")
        fields["title"] = title
    if body is not None:
        fields["body"] = body.strip()
    if not fields:
        raise ValueError("nothing to update (pass title, body, and/or type)")
    fields["updated_at"] = now_iso()
    # A content update RE-OPENS an already-handled report so it re-enters the
    # triage queue — new info on an addressed/declined item shouldn't stay
    # hidden behind its old status.
    if doc.get("status") in ("addressed", "declined"):
        fields["status"] = "open"
        fields["addressed_at"] = None
        fields["reopened_at"] = fields["updated_at"]
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def delete_feedback(state: State, feedback_id: str) -> bool:
    """Retract (delete) an agent-filed feedback item — e.g. it contained a
    mistake or sensitive info. Only `source='agent'` items can be deleted.
    Returns False if it doesn't exist."""
    path = _feedback_path(state, feedback_id)
    doc = state.backend.get_doc(path)
    if doc is None:
        return False
    if doc.get("source") != "agent":
        raise ValueError("can only delete agent-filed feedback (source='agent')")
    state.backend.delete_doc(path)
    return True


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

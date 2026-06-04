"""Activity log writer.

Lightweight per-paper feed of significant actions, surfaced on the dashboard
so the human collaborator can see what's happening without diving into
specific subcollections. Path:

    /projects/{pid}/papers/{slug}/activity_log/{auto_id}

Each entry: { action, detail, actor, created_at }

This module is callable from anywhere in the tool layer; only a handful of
"signal" actions are logged for v0 (paper_created, section_updated,
review_added, review_resolved). Future: every write through the MCP could
emit one for full audit.
"""
from __future__ import annotations

from ..state import State
from ..util import new_id, now_iso


def log_event(
    state: State,
    paper_slug: str,
    *,
    action: str,
    detail: dict | None = None,
    actor: str = "claude",
) -> None:
    """Append an activity entry. Best-effort — failures are swallowed so a
    bad activity write never blocks the primary tool operation."""
    try:
        state.backend.set_doc(
            state.project_path(
                "papers", paper_slug, "activity_log", new_id(),
            ),
            {
                "action": action,
                "detail": detail or {},
                "actor": actor,
                "created_at": now_iso(),
            },
        )
    except Exception:  # pragma: no cover — non-critical path
        pass

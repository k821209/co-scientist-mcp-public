"""Activity log + project timeline.

Two feeds, both surfaced on the dashboard so the human collaborator can see
what's happening without diving into subcollections:

  - Per-paper activity log:  /projects/{pid}/papers/{slug}/activity_log/{id}
        { action, detail, actor, created_at }
  - Project-level timeline:  /projects/{pid}/timeline/{id}
        { type, title, detail, actor, paper_slug, ts }

`log_event` writes the per-paper entry AND mirrors it into the project
timeline, so the project's Activity tab shows a unified, reverse-chronological
feed across all papers. The timeline also carries explicit todo events and any
ad-hoc notes the agent logs.
"""
from __future__ import annotations

from ..state import State
from ..util import new_id, now_iso


def log_timeline(
    state: State,
    *,
    event_type: str,
    title: str | None = None,
    detail: dict | None = None,
    actor: str = "claude",
    paper_slug: str | None = None,
) -> None:
    """Append one entry to the project-level timeline. Best-effort: a failed
    timeline write never blocks the primary operation."""
    try:
        state.backend.set_doc(
            state.project_path("timeline", new_id()),
            {
                "type": event_type,
                "title": title,
                "detail": detail or {},
                "actor": actor,
                "paper_slug": paper_slug,
                "ts": now_iso(),
            },
        )
    except Exception:  # pragma: no cover — non-critical path
        pass


def list_timeline(state: State, limit: int = 50) -> list[dict]:
    """Return the most recent timeline entries, newest first."""
    try:
        items = state.backend.list_collection(state.project_path("timeline"))
    except Exception:  # pragma: no cover — empty collection is fine
        return []
    out = [{"id": i, **d} for i, d in items]
    out.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return out[:limit]


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
    now = now_iso()
    try:
        state.backend.set_doc(
            state.project_path(
                "papers", paper_slug, "activity_log", new_id(),
            ),
            {
                "action": action,
                "detail": detail or {},
                "actor": actor,
                "created_at": now,
            },
        )
    except Exception:  # pragma: no cover — non-critical path
        pass

    # Mirror into the project-level timeline so the Activity tab shows a unified
    # feed across all papers.
    log_timeline(
        state, event_type=action, detail=detail, actor=actor, paper_slug=paper_slug,
    )

    # Bump the project's own updated_at so the dashboard can sort projects by
    # recent activity. Guard on existence (the doc is created by the web app)
    # to avoid phantom project docs and NotFound; best-effort, never blocks.
    try:
        project_path = state.project_path()
        if state.backend.get_doc(project_path) is not None:
            state.backend.update_doc(project_path, {"updated_at": now})
    except Exception:  # pragma: no cover — non-critical path
        pass

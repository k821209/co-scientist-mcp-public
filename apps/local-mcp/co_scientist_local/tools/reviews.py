"""Reviews / comments — the bidirectional loop.

Source values:
    'user'      — comment authored by the human via the web dashboard
    'ai'        — comment produced by /paper-review (virtual reviewer)
    'external'  — imported from journal reviewer feedback

Status flow:
    open → accepted | rejected | resolved
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso
from .activity import log_event
from .papers import _paper_path

_VALID_SOURCES = {"user", "ai", "external"}
_VALID_SEVERITY = {"major", "minor", "suggestion"}
_VALID_STATUS = {"open", "accepted", "rejected", "resolved"}


def _reviews_path(state: State, slug: str) -> str:
    return state.project_path("papers", slug, "reviews")


def _review_path(state: State, slug: str, review_id: str) -> str:
    return state.project_path("papers", slug, "reviews", review_id)


def add_review(
    state: State,
    slug: str,
    *,
    comment: str,
    source: str = "user",
    reviewer_name: str = "User",
    section: str | None = None,
    severity: str = "minor",
    manuscript_ref: str | None = None,
    anchor_text: str | None = None,
    anchor_prefix: str | None = None,
    anchor_suffix: str | None = None,
    manuscript_snapshot: str | None = None,
) -> dict:
    """Create a new review/comment. Returns the created doc."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    if source not in _VALID_SOURCES:
        raise ValueError(f"invalid source: {source!r}")
    if severity not in _VALID_SEVERITY:
        raise ValueError(f"invalid severity: {severity!r}")
    if not comment or not comment.strip():
        raise ValueError("comment is required")

    review_id = new_id()
    now = now_iso()
    doc = {
        "id": review_id,
        "source": source,
        "reviewer_name": reviewer_name,
        "section": section,
        "severity": severity,
        "status": "open",
        "comment": comment,
        "response": None,
        "manuscript_ref": manuscript_ref,
        "anchor_text": anchor_text,
        "anchor_prefix": anchor_prefix,
        "anchor_suffix": anchor_suffix,
        "manuscript_snapshot": manuscript_snapshot,
        "created_at": now,
        "resolved_at": None,
    }
    state.backend.set_doc(_review_path(state, slug, review_id), doc)
    log_event(
        state, slug, action="review_added",
        detail={"id": review_id, "source": source, "section": section, "severity": severity},
        actor="user" if source == "user" else "claude",
    )
    return doc


def list_reviews(
    state: State,
    slug: str,
    *,
    status: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """List reviews for a paper, optionally filtered by status and/or source.

    Sorted by created_at descending (most recent first).
    """
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(_reviews_path(state, slug))
    # The document key is the authoritative id (resolve_paper_comment needs it).
    # Comments written by the web dashboard via addDoc carry no `id` field in
    # their data — only the Firestore doc key — so surface the key as both
    # `id` and `review_id` (dev-todo CMT-3).
    reviews = [{**data, "id": doc_id, "review_id": doc_id} for doc_id, data in pairs]
    if status is not None:
        reviews = [r for r in reviews if r.get("status") == status]
    if source is not None:
        reviews = [r for r in reviews if r.get("source") == source]
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return reviews


def update_review(
    state: State,
    slug: str,
    review_id: str,
    *,
    status: str | None = None,
    response: str | None = None,
) -> dict:
    """Update a review's status and/or response text.

    Setting status to a terminal value (accepted/rejected/resolved) stamps
    resolved_at automatically.
    """
    path = _review_path(state, slug, review_id)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"review not found: {slug!r}/{review_id!r}")
    fields: dict = {}
    if status is not None:
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status: {status!r}")
        fields["status"] = status
        if status in ("accepted", "rejected", "resolved"):
            fields["resolved_at"] = now_iso()
        else:
            fields["resolved_at"] = None
    if response is not None:
        fields["response"] = response
    if not fields:
        return existing
    state.backend.update_doc(path, fields)
    if status and status in ("accepted", "rejected", "resolved"):
        log_event(
            state, slug, action="review_resolved",
            detail={"id": review_id, "status": status,
                    "response_preview": (response or "")[:120]},
        )
    return state.backend.get_doc(path)


def count_open_user_comments(state: State, slug: str) -> int:
    """Open, human-authored comments — both dashboard ('user') and shared/public
    page ('external') feedback. Excludes 'ai' (virtual reviewer) comments.

    Used by the SessionStart hook to surface 'you have N new comments'.
    """
    open_reviews = list_reviews(state, slug, status="open")
    return sum(1 for r in open_reviews if r.get("source") != "ai")

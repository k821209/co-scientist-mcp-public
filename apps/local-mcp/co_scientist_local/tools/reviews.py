"""Reviews / comments — the bidirectional loop.

Source values:
    'user'      — comment authored by the human via the web dashboard
    'ai'        — comment produced by /paper-review (internal self-review)
    'reviewer'  — a REAL journal reviewer's point, from a decision letter.
                  This is the only source a response letter is built from
                  (/response-letter). Carries `reviewer_name` ("Reviewer 1")
                  and an optional `round` (submission round, 1-based).
    'external'  — anonymous share-link visitor comment (collaborator), NOT a
                  journal reviewer.

Status flow:
    open → accepted | rejected | resolved
"""
from __future__ import annotations

import re

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso
from .activity import log_event
from .papers import _paper_path

_VALID_SOURCES = {"user", "ai", "reviewer", "external"}
_VALID_SEVERITY = {"major", "minor", "suggestion"}
_VALID_STATUS = {"open", "accepted", "rejected", "resolved"}
# User triage, orthogonal to status: does the author intend to act on this
# comment? Set from the dashboard; new comments start "pending".
_VALID_DECISION = {"pending", "accepted", "rejected"}

# ── anchor normalization (mirrors the web renderer's stripRenderArtifacts +
#    placeAnchors matching) so reconcile finds a sentence wherever it lives,
#    tolerant of markdown markers, citation tokens, smart quotes and dashes. ──
_DOI_TOKEN = re.compile(r"\{(?:doi|fig|tab):[^}]*\}")
_BARE_DOI = re.compile(r"\bdoi:[^\s)\]}]+", re.IGNORECASE)
_MD_MARKERS = re.compile(r"[*_~`]")
_WS = re.compile(r"\s+")
_SMART = str.maketrans({
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", " ": " ", " ": " ",
})


def _normalize_anchor(text: str) -> str:
    s = _DOI_TOKEN.sub(" ", text or "")
    s = _BARE_DOI.sub(" ", s)
    s = s.translate(_SMART)
    s = _MD_MARKERS.sub("", s)
    s = _WS.sub(" ", s).strip()
    return s


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
    anchor_occurrence: int | None = None,
    manuscript_snapshot: str | None = None,
    round: int | None = None,
) -> dict:
    """Create a new review/comment. Returns the created doc.

    `round` (submission round, 1-based) is for source='reviewer' comments so a
    response letter can group / scope by review round; leave None otherwise."""
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
        "decision": "pending",
        "comment": comment,
        "response": None,
        "manuscript_ref": manuscript_ref,
        "anchor_text": anchor_text,
        "anchor_prefix": anchor_prefix,
        "anchor_suffix": anchor_suffix,
        "anchor_occurrence": anchor_occurrence,
        "manuscript_snapshot": manuscript_snapshot,
        "round": round,
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
    decision: str | None = None,
) -> list[dict]:
    """List reviews for a paper, optionally filtered by status, source, and/or
    the user's triage `decision` ("pending" | "accepted" | "rejected"; comments
    with no stored decision count as "pending").

    Sorted by created_at descending (most recent first).
    """
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(_reviews_path(state, slug))
    # The document key is the authoritative id (resolve_paper_comment needs it).
    # Comments written by the web dashboard via addDoc carry no `id` field in
    # their data — only the Firestore doc key — so surface the key as both
    # `id` and `review_id` (dev-todo CMT-3).
    #
    # ALWAYS emit an explicit `decision`. Older / dashboard-created comments may
    # not store the field; omitting it from the output is a silent-failure trap
    # (an agent can't distinguish "pending" from "field missing" and may treat
    # an untriaged comment as approved). Normalize absent → "pending".
    reviews = [
        {**data, "id": doc_id, "review_id": doc_id,
         "decision": data.get("decision") or "pending"}
        for doc_id, data in pairs
    ]
    if status is not None:
        reviews = [r for r in reviews if r.get("status") == status]
    if source is not None:
        reviews = [r for r in reviews if r.get("source") == source]
    if decision is not None:
        reviews = [r for r in reviews if (r.get("decision") or "pending") == decision]
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return reviews


def update_review(
    state: State,
    slug: str,
    review_id: str,
    *,
    status: str | None = None,
    response: str | None = None,
    decision: str | None = None,
    section: str | None = None,
    anchor_text: str | None = None,
    anchor_prefix: str | None = None,
    anchor_suffix: str | None = None,
    anchor_occurrence: int | None = None,
    anchors: list[str] | None = None,
) -> dict:
    """Update a review's status, response, and/or its anchor placement.

    Setting status to a terminal value (accepted/rejected/resolved) stamps
    resolved_at automatically. The `section` and `anchor_*` arguments let an
    operator correct where a comment points — e.g. fix a wrong `section` or
    re-anchor a moved sentence (see also reconcile_review_anchors, which does
    this in bulk).

    `anchors` re-anchors a comment to SEVERAL passages at once — pass it when
    one comment was addressed across multiple spots so each gets its own
    highlight/jump. The first becomes the primary `anchor_text`. Any argument
    left None is unchanged.
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
    if decision is not None:
        if decision not in _VALID_DECISION:
            raise ValueError(f"invalid decision: {decision!r}")
        fields["decision"] = decision
    if section is not None:
        fields["section"] = section
    if anchor_text is not None:
        fields["anchor_text"] = anchor_text
    if anchor_prefix is not None:
        fields["anchor_prefix"] = anchor_prefix
    if anchor_suffix is not None:
        fields["anchor_suffix"] = anchor_suffix
    if anchor_occurrence is not None:
        fields["anchor_occurrence"] = anchor_occurrence
    if anchors is not None:
        cleaned = [a for a in anchors if a and a.strip()]
        if cleaned:
            fields["anchors"] = cleaned
            fields["anchor_text"] = cleaned[0]  # first is the primary anchor
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


def delete_review(state: State, slug: str, review_id: str) -> bool:
    """Permanently delete a review/comment. Returns True if it existed.

    Use for removing an AI reviewer comment that is wrong or obsolete — there
    is otherwise no way to retract an 'ai' comment from the agent side.
    """
    path = _review_path(state, slug, review_id)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"review not found: {slug!r}/{review_id!r}")
    deleted = state.backend.delete_doc(path)
    log_event(state, slug, action="review_deleted", detail={"id": review_id})
    return deleted


def reconcile_review_anchors(state: State, slug: str, dry_run: bool = True) -> dict:
    """Re-align every open comment's stored `section` with where its anchor
    text actually lives in the current manuscript.

    A comment's `section` can be wrong (e.g. /paper-review stamped the wrong
    one) or hold a section *title* where the renderer expects a *key*; after a
    manuscript edit this leaves the highlight unresolved even though the
    sentence is present verbatim. This scans each open comment, finds the
    section(s) whose current body contains the (normalized) anchor text, and:

      - leaves it alone when `section` already names the right key (`ok`);
      - rewrites `section` to the correct key when it was wrong or a title
        (`relocated`);
      - reports it as `truly_missing` when the text is in no section at all
        (genuinely edited/deleted away — left untouched for human review).

    Pass dry_run=True (default) to preview the plan without writing.
    Returns {dry_run, relocated:[{review_id,from,to,anchor_preview}],
             ok:[review_id], truly_missing:[{review_id,section,anchor_preview}]}.
    """
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")

    pairs = state.backend.list_collection(
        state.project_path("papers", slug, "sections"))
    sections = [
        {
            "key": data.get("key", doc_id),
            "title": data.get("title"),
            "norm_body": _normalize_anchor(data.get("body") or ""),
            "sort_order": data.get("sort_order", 999),
        }
        for doc_id, data in pairs
    ]
    sections.sort(key=lambda s: s["sort_order"])
    keys = {s["key"] for s in sections}
    title_to_key = {s["title"]: s["key"] for s in sections if s.get("title")}

    relocated: list[dict] = []
    ok: list[str] = []
    missing: list[dict] = []

    for r in list_reviews(state, slug, status="open"):
        rid = r.get("id") or r.get("review_id")
        sec = r.get("section")
        if sec and str(sec).startswith("figure:"):
            continue
        text = r.get("anchor_text")
        if not text or len(text) < 2:
            continue
        na = _normalize_anchor(text)
        if len(na) < 2:
            continue

        matched = [s["key"] for s in sections if na and na in s["norm_body"]]
        preview = (text[:60] + "…") if len(text) > 60 else text
        if not matched:
            missing.append({"review_id": rid, "section": sec, "anchor_preview": preview})
            continue

        stated_key = sec if sec in keys else title_to_key.get(sec)
        target = stated_key if stated_key in matched else matched[0]
        if sec == target:
            ok.append(rid)
            continue

        relocated.append({"review_id": rid, "from": sec, "to": target,
                          "anchor_preview": preview})
        if not dry_run:
            state.backend.update_doc(
                _review_path(state, slug, rid), {"section": target})

    if not dry_run and relocated:
        log_event(state, slug, action="reviews_reconciled",
                  detail={"relocated": len(relocated), "missing": len(missing)})
    return {"dry_run": dry_run, "relocated": relocated, "ok": ok,
            "truly_missing": missing}


def review_triage_summary(state: State, slug: str) -> dict:
    """One-call snapshot of where every comment sits in the triage lifecycle,
    for the submission gate and the "remaining work" check at session start.

    A comment is "rejected" if either its `decision` or its `status` is
    'rejected' (the dashboard sets both; an agent-rejected comment may carry
    only the status). Rejected comments need a rebuttal in `response` — academic
    response letters must say *why* a reviewer point was not adopted — so a
    rejected comment with an empty `response` is flagged. Accepted comments
    still open are not yet reflected in the manuscript.

    Returns counts plus the offending review_ids so callers can act:
        {
          accepted, accepted_unresolved, rejected, rejected_without_rationale,
          pending,                         # plain counts
          accepted_unresolved_items: [...],
          rejected_without_rationale_items: [{review_id, section, reviewer, comment}],
        }
    """
    reviews = list_reviews(state, slug)  # validates the paper exists
    accepted = accepted_unresolved = rejected = pending = 0
    unresolved_items: list[dict] = []
    no_rationale_items: list[dict] = []
    for r in reviews:
        decision = r.get("decision") or "pending"
        status = r.get("status")
        is_rejected = decision == "rejected" or status == "rejected"
        has_response = bool((r.get("response") or "").strip())
        rid = r.get("id") or r.get("review_id")
        preview = (r.get("comment") or "")[:80]
        if is_rejected:
            rejected += 1
            if not has_response:
                no_rationale_items.append({
                    "review_id": rid,
                    "section": r.get("section"),
                    "reviewer": r.get("reviewer_name"),
                    "comment": preview,
                })
        elif decision == "accepted":
            accepted += 1
            if status == "open":
                accepted_unresolved += 1
                unresolved_items.append({
                    "review_id": rid, "section": r.get("section"), "comment": preview,
                })
        elif status == "open":
            pending += 1
    return {
        "accepted": accepted,
        "accepted_unresolved": accepted_unresolved,
        "rejected": rejected,
        "rejected_without_rationale": len(no_rationale_items),
        "pending": pending,
        "accepted_unresolved_items": unresolved_items,
        "rejected_without_rationale_items": no_rationale_items,
    }


def count_open_user_comments(state: State, slug: str) -> int:
    """Open, human-authored comments — both dashboard ('user') and shared/public
    page ('external') feedback. Excludes 'ai' (virtual reviewer) comments.

    Used by the SessionStart hook to surface 'you have N new comments'.
    """
    open_reviews = list_reviews(state, slug, status="open")
    return sum(1 for r in open_reviews if r.get("source") != "ai")

"""Discussion: comments on a drawn graph, and the decisions that came out.

    doc: projects/{pid}/discussion_comments/{comment_id}
    doc: projects/{pid}/decisions/{decision_id}

The loop this exists for is: draw the thing, argue about it, write down what was
settled. The agent is a participant, not a spectator — it reads the graph, it
can answer a question in the thread, and it can record what the discussion
decided.

Two shapes, deliberately different:

  comments  attach to ONE graph. They are about the drawing in front of you and
            they stop mattering once the question is settled.
  decisions attach to the PROJECT, with a pointer back to the graph that
            produced them. A decision outlives the diagram that occasioned it;
            filing it under the drawing would bury it there.

A superseded decision is never deleted. The dangerous entry in a record of
decisions is not a wrong one — it is one everybody still believes.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

AGENT_NAME = "Claude Code"


def _comments_col(state: State) -> str:
    return state.project_path("discussion_comments")


def _comment_path(state: State, cid: str) -> str:
    return state.project_path("discussion_comments", cid)


def _decisions_col(state: State) -> str:
    return state.project_path("decisions")


def _decision_path(state: State, did: str) -> str:
    return state.project_path("decisions", did)


# ─────────────────────────── comments ───────────────────────────


def list_discussion(state: State, graph_id: str | None = None) -> list[dict]:
    """Comments, oldest first. Pass `graph_id` for one graph's thread."""
    rows = [d for _, d in state.backend.list_collection(_comments_col(state))]
    if graph_id:
        rows = [r for r in rows if r.get("graph_id") == graph_id]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return rows


def post_comment(
    state: State, *, graph_id: str, body: str, parent_id: str | None = None,
) -> dict:
    """Add a comment, or a reply when `parent_id` is given."""
    text = (body or "").strip()
    if not text:
        raise ValueError("body is required")
    if not (graph_id or "").strip():
        raise ValueError("graph_id is required — a comment is about a graph")
    if parent_id and state.backend.get_doc(_comment_path(state, parent_id)) is None:
        # Refused rather than silently promoted to a top-level comment: a reply
        # that lost its question reads as a statement nobody asked for.
        raise NotFound(f"comment {parent_id!r} not found — cannot reply to it")
    cid = new_id()
    doc = {
        "comment_id": cid,
        "graph_id": graph_id,
        "parent_id": parent_id or None,
        "body": text,
        "author_name": AGENT_NAME,
        "author_kind": "agent",
        "created_at": now_iso(),
    }
    state.backend.set_doc(_comment_path(state, cid), doc)
    return {**doc, "dashboard_url": state.dashboard_url("discussion")}


# ─────────────────────────── decisions ───────────────────────────


def list_decisions(state: State, *, include_superseded: bool = False) -> list[dict]:
    """Decisions that still hold, newest first.

    `include_superseded=True` adds the reversed ones, each carrying
    `superseded_by`. Read this at session start: it is the standing record of
    what the project has already settled, and re-opening a settled question is
    the most expensive thing an agent can do here."""
    rows = [d for _, d in state.backend.list_collection(_decisions_col(state))]
    if not include_superseded:
        rows = [r for r in rows if not r.get("superseded_by")]
    rows.sort(key=lambda r: r.get("decided_at") or "", reverse=True)
    return rows


def record_decision(
    state: State,
    *,
    text: str,
    rationale: str | None = None,
    from_graph: str | None = None,
    supersedes: str | None = None,
) -> dict:
    """Write down what was decided.

    `rationale` is the one line that is worth having in a year — the decision
    says WHAT, the rationale says why the alternatives lost.

    `supersedes` reverses an earlier decision. The old one is kept and marked,
    never deleted: a bulletin that can quietly lose an entry is a bulletin
    nobody can rely on."""
    body = (text or "").strip()
    if not body:
        raise ValueError("text is required")
    old = None
    if supersedes:
        old = state.backend.get_doc(_decision_path(state, supersedes))
        if old is None:
            raise NotFound(f"decision {supersedes!r} not found")
        if old.get("superseded_by"):
            raise ValueError(
                f"decision {supersedes!r} was already superseded by "
                f"{old['superseded_by']!r} — supersede that one instead, so the "
                "chain stays followable"
            )
    did = new_id()
    now = now_iso()
    doc = {
        "decision_id": did,
        "text": body,
        "rationale": (rationale or "").strip() or None,
        "from_graph": from_graph or None,
        "supersedes": supersedes or None,
        "superseded_by": None,
        "superseded_at": None,
        "decided_by": AGENT_NAME,
        "decided_at": now,
    }
    state.backend.set_doc(_decision_path(state, did), doc)
    if old is not None:
        state.backend.update_doc(_decision_path(state, supersedes), {
            "superseded_by": did, "superseded_at": now,
        })
    # Reversing a decision makes every study that cited it out of date. That
    # already shows up in `list_studies`, but saying it HERE puts it in front of
    # whoever just did the reversing, which is the one moment they can act on
    # it without being told twice.
    affected = []
    try:
        from . import studies as _studies
        for st in _studies.list_studies(state):
            if st.get("stale") or st.get("decisions_since_count"):
                affected.append({
                    "study_id": st.get("study_id"), "title": st.get("title"),
                    "stale": bool(st.get("stale")),
                    "decisions_since_count": st.get("decisions_since_count", 0),
                })
    except Exception:
        affected = []
    return {**doc, "studies_to_review": affected,
            "dashboard_url": state.dashboard_url("discussion")}


def get_decision(state: State, decision_id: str) -> dict:
    doc = state.backend.get_doc(_decision_path(state, decision_id))
    if doc is None:
        raise NotFound(f"decision {decision_id!r} not found")
    return doc

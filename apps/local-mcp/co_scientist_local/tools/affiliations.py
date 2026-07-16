"""Account-wide affiliation library — one store per USER, shared across projects.

Affiliations recur across authors, papers, and projects (a lab's full
department string is typed once and reused), so they live at
`users/{uid}/affiliations/{id}` (owner-only), mirroring the author library
(authors.py). A paper keeps its OWN ordered, de-duplicated affiliation list
(see papers.py); each author references affiliation ids — which is what lets
export render the standard journal author block (Name^{1,2} + numbered
affiliations) instead of repeating a free-text string per author.
"""
from __future__ import annotations

import uuid

from ..state import State
from ..util import now_iso


def _affiliations_path(state: State) -> str:
    return f"users/{state.owner_uid}/affiliations"


def _affiliation_path(state: State, aff_id: str) -> str:
    aid = (aff_id or "").strip()
    if not aid or "/" in aid:
        raise ValueError("affiliation id must be non-empty and contain no '/'")
    return f"users/{state.owner_uid}/affiliations/{aid}"


def add_affiliation(state: State, text: str) -> dict:
    """Add a reusable affiliation to the account library. Idempotent on the
    (whitespace-normalised) text: an existing entry with the same text is
    returned unchanged so repeated calls don't duplicate it."""
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("affiliation text is required")
    for aid, data in state.backend.list_collection(_affiliations_path(state)):
        if " ".join((data.get("text", "") or "").split()) == text:
            return {"id": aid, **data, "existing": True}
    aid = uuid.uuid4().hex[:12]
    now = now_iso()
    doc = {"id": aid, "text": text, "created_at": now, "updated_at": now}
    state.backend.set_doc(_affiliation_path(state, aid), doc)
    return {**doc, "existing": False}


def list_affiliations(state: State) -> list[dict]:
    """List every affiliation in the account library, sorted by text."""
    out = [{"id": aid, **data}
           for aid, data in state.backend.list_collection(_affiliations_path(state))]
    out.sort(key=lambda a: a.get("text", "").lower())
    return out


def resolve_texts(state: State, affiliation_ids) -> list[str]:
    """Institution strings for the given account-library affiliation ids —
    order preserved, unknown ids skipped. Used to derive a display affiliation
    for an author who's linked only via affiliation_ids (no free-text)."""
    lib = {a["id"]: a["text"] for a in list_affiliations(state)}
    return [lib[i] for i in (affiliation_ids or []) if i in lib]


def update_affiliation(state: State, aff_id: str, text: str) -> dict:
    """Change a library affiliation's text. This updates the LIBRARY entry only.
    Papers deliberately keep the affiliation text captured when it was added (a
    point-in-time record — an author moving institutions must not retroactively
    rewrite a submitted/published paper). To pull a corrected text into an
    in-progress DRAFT, use the opt-in resync (papers.resync_paper_affiliations)."""
    path = _affiliation_path(state, aff_id)
    doc = state.backend.get_doc(path)
    if doc is None:
        raise ValueError(f"affiliation {aff_id!r} not found")
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("affiliation text is required")
    doc["text"] = text
    doc["updated_at"] = now_iso()
    state.backend.set_doc(path, doc)
    return doc


def delete_affiliation(state: State, aff_id: str) -> bool:
    """Delete a library affiliation. Returns whether it existed."""
    path = _affiliation_path(state, aff_id)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

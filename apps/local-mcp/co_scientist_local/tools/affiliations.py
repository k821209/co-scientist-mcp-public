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


def papers_using(state: State, aff_id: str) -> list[dict]:
    """Papers in THIS project whose author block references `aff_id`.

    The library is account-wide while papers are per project, so this answers
    for the project the session is bound to — said in the reply rather than
    implied.
    """
    out: list[dict] = []
    for slug, paper in state.backend.list_collection(state.project_path("papers")):
        for entry in (paper.get("affiliations") or []):
            if not isinstance(entry, dict) or entry.get("id") != aff_id:
                continue
            out.append({
                "slug": paper.get("slug") or slug,
                "cached_text": entry.get("text"),
            })
            break
    out.sort(key=lambda r: r["slug"])
    return out


def update_affiliation(state: State, aff_id: str, text: str) -> dict:
    """Change a library affiliation's text. This updates the LIBRARY entry only.
    Papers deliberately keep the affiliation text captured when it was added (a
    point-in-time record — an author moving institutions must not retroactively
    rewrite a submitted/published paper). To pull a corrected text into an
    in-progress DRAFT, use the opt-in resync (papers.resync_paper_affiliations).

    So the reply says WHO this edit reaches. A library with five near-identical
    rows for one department invites editing the wrong one, and matching by the
    text in a rendered manuscript picks whichever variant the paper happens to
    cache: three edits returned success, the export was unchanged, and the only
    signal was the diff of a .docx (feedback 3f1ed9ac0012).
    """
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
    users = papers_using(state, aff_id)
    stale = [u["slug"] for u in users if u.get("cached_text") != text]
    out = {**doc,
           "used_by": [u["slug"] for u in users],
           "used_by_scope": "papers in this project",
           "needs_resync": stale}
    if not users:
        out["note"] = (
            "No paper in this project references this record, so nothing "
            "downstream changed. get_paper_affiliations(slug) lists the ids a "
            "paper actually uses — match by id, not by the text in the "
            "rendered header: near-duplicate rows differ only in trailing "
            "address detail.")
    elif stale:
        out["note"] = (
            f"{len(stale)} paper(s) still carry the old text: "
            + ", ".join(stale)
            + ". resync_paper_affiliations(slug) pulls it in — a paper keeps a "
            "point-in-time snapshot on purpose, so nothing does it for you.")
    return out


def delete_affiliation(state: State, aff_id: str) -> bool:
    """Delete a library affiliation. Returns whether it existed."""
    path = _affiliation_path(state, aff_id)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

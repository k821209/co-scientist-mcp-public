"""Account-wide author library — one store per USER, shared across all of
their projects.

Authors (name + affiliation + email + ORCID) recur across papers and
projects, so they live at `users/{uid}/authors/{id}` (Firestore rule:
owner-only), NOT on any single paper or project. Set an author once and
reuse them on every manuscript — the paper's own author *list* (order,
corresponding-author flag) is stored per-paper (see papers.py); this is the
reusable address book those entries are picked from.

Mirror of the account-wide secrets store (see secrets.py).
"""
from __future__ import annotations

import uuid

from ..state import State
from ..util import now_iso

_FIELDS = ("name", "affiliation", "email", "orcid")


def _authors_path(state: State) -> str:
    return f"users/{state.owner_uid}/authors"


def _author_path(state: State, author_id: str) -> str:
    aid = (author_id or "").strip()
    if not aid or "/" in aid:
        raise ValueError("author id must be non-empty and contain no '/'")
    return f"users/{state.owner_uid}/authors/{aid}"


def _clean(name: str, affiliation: str = "", email: str = "",
           orcid: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("author name is required")
    return {
        "name": name,
        "affiliation": (affiliation or "").strip(),
        "email": (email or "").strip(),
        "orcid": (orcid or "").strip(),
    }


def add_author(state: State, name: str, affiliation: str = "",
               email: str = "", orcid: str = "") -> dict:
    """Add a reusable author to the account library. Idempotent on
    (name, affiliation): if an entry with the same name + affiliation
    already exists it is returned unchanged (email/orcid NOT overwritten —
    use update_author for that) so repeated calls don't create duplicates."""
    fields = _clean(name, affiliation, email, orcid)
    for aid, data in state.backend.list_collection(_authors_path(state)):
        if (data.get("name", "").strip().lower() == fields["name"].lower()
                and data.get("affiliation", "").strip().lower()
                == fields["affiliation"].lower()):
            return {"id": aid, **data, "existing": True}
    aid = uuid.uuid4().hex[:12]
    now = now_iso()
    doc = {"id": aid, **fields, "created_at": now, "updated_at": now}
    state.backend.set_doc(_author_path(state, aid), doc)
    return {**doc, "existing": False}


def list_authors(state: State) -> list[dict]:
    """List every author in the account library, sorted by name."""
    out = [{"id": aid, **data}
           for aid, data in state.backend.list_collection(_authors_path(state))]
    out.sort(key=lambda a: a.get("name", "").lower())
    return out


def update_author(state: State, author_id: str, *, name: str | None = None,
                  affiliation: str | None = None, email: str | None = None,
                  orcid: str | None = None) -> dict:
    """Update fields on an existing library author. Only the arguments you
    pass are changed; the rest are left as-is."""
    path = _author_path(state, author_id)
    doc = state.backend.get_doc(path)
    if doc is None:
        raise ValueError(f"author {author_id!r} not found")
    updates = {"name": name, "affiliation": affiliation,
               "email": email, "orcid": orcid}
    for key, val in updates.items():
        if val is not None:
            doc[key] = val.strip() if key != "name" else (val.strip() or doc[key])
    doc["updated_at"] = now_iso()
    state.backend.set_doc(path, doc)
    return doc


def delete_author(state: State, author_id: str) -> bool:
    """Delete an author from the account library. Returns whether it existed."""
    path = _author_path(state, author_id)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

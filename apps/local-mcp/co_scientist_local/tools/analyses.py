"""Analyses (records only).

Each analysis is a named group within a paper (e.g. `pca_analysis`). It
collects scripts + outputs that will be promoted to figures/tables.

Paths:
    doc: users/{uid}/papers/{slug}/analyses/{name}

For v0 we only support CRUD on the analysis record itself. The downstream
pieces — `analysis_runs` (SSH submissions), `analysis_results` (file scan
& panel mapping), `analysis_outputs` (figure/table provenance links) — get
ported in the next session along with the SSH/server tools, because they
all share infrastructure.

Auto-slugifies the supplied name (matches the original `create_analysis`
behavior described in the architecture doc).
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso, slugify
from .papers import _paper_path


def _analysis_path(state: State, slug: str, name: str) -> str:
    return state.project_path("papers", slug, "analyses", name)


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


def create_analysis(
    state: State,
    slug: str,
    *,
    name: str,
    description: str | None = None,
    status: str = "active",
) -> dict:
    _ensure_paper(state, slug)
    if not name or not name.strip():
        raise ValueError("name is required")
    norm_name = slugify(name) or name.strip()
    path = _analysis_path(state, slug, norm_name)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"analysis {norm_name!r} already exists for {slug!r}")
    now = now_iso()
    doc = {
        "name": norm_name,
        "description": description,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def update_analysis(
    state: State,
    slug: str,
    name: str,
    *,
    description: str | None = None,
    status: str | None = None,
) -> dict:
    _ensure_paper(state, slug)
    path = _analysis_path(state, slug, name)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"analysis {name!r} not found for {slug!r}")
    fields: dict = {"updated_at": now_iso()}
    if description is not None: fields["description"] = description
    if status is not None: fields["status"] = status
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_analysis(state: State, slug: str, name: str) -> dict:
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_analysis_path(state, slug, name))
    if doc is None:
        raise NotFound(f"analysis {name!r} not found for {slug!r}")
    return doc


def list_analyses(state: State, slug: str, *, status: str | None = None) -> list[dict]:
    """List analyses sorted by created_at desc. Optional status filter."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "analyses"))
    items = [data for _, data in pairs]
    if status is not None:
        items = [a for a in items if a.get("status") == status]
    items.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return items


def delete_analysis(state: State, slug: str, name: str) -> bool:
    _ensure_paper(state, slug)
    path = _analysis_path(state, slug, name)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

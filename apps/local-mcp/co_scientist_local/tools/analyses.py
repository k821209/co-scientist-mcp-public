"""Analyses (records only).

Each analysis is a named group within a paper (e.g. `pca_analysis`). It
collects scripts + outputs that will be promoted to figures/tables.

Paths:
    doc: projects/{pid}/papers/{slug}/analyses/{name}

This module owns CRUD on the analysis record itself. Execution and output
mapping live alongside it: run records in `runs.py` (`launch_local_job`)
and `ssh_ops.py` (`submit_remote_job`); figure/table promotion in the
figures/tables tools.

Auto-slugifies the supplied name (matches the original `create_analysis`
behavior described in the architecture doc).
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso, slugify
from .papers import _paper_path


# A project with no paper — a video project, a tooling project — still runs
# jobs, and a job with no run record is the provenance gap every other rule
# here exists to close. Analyses were keyed under a paper, so such a project
# could not register one and raw ssh+nohup was blocked by the harness: video
# jobs could not be launched with a record at all (feedback fb5f2b270d84).
# This sentinel slug scopes an analysis to the PROJECT instead.
PROJECT_SCOPE = "_project"


def is_project_scope(slug: str | None) -> bool:
    return not slug or slug == PROJECT_SCOPE


def analyses_base(state: State, slug: str | None) -> str:
    """The collection an analysis lives in: under its paper, or under the
    project when `slug` is the project-scope sentinel."""
    if is_project_scope(slug):
        return state.project_path("analyses")
    return state.project_path("papers", slug, "analyses")


def iter_analyses(state: State):
    """Every (slug, analysis_name) in the project — each paper's, then the
    project-scoped ones — for the sweeps that walk all runs."""
    for slug, _ in state.backend.list_collection(state.project_path("papers")):
        for name, _ in state.backend.list_collection(
                state.project_path("papers", slug, "analyses")):
            yield slug, name
    for name, _ in state.backend.list_collection(state.project_path("analyses")):
        yield PROJECT_SCOPE, name


def _analysis_path(state: State, slug: str, name: str) -> str:
    return f"{analyses_base(state, slug)}/{name}"


def _ensure_paper(state: State, slug: str) -> None:
    if is_project_scope(slug):
        return
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


def resolve_analysis(state: State, slug: str, name: str) -> str:
    """The id an analysis is STORED under, from whatever the caller calls it.

    `create_analysis` slugifies the name it is given — "civitai 분석" is stored
    as "civitai-분석" — and every other entry point looked the name up
    verbatim, so the author's own string failed with "analysis not found" on
    the very next call. The session that hit it worked out that it had to
    slugify by hand and retried; nothing in the error said so
    (feedback bdd2d6dc8798).

    Verbatim first, then slugified: a name stored before the slugifying
    existed still resolves. Raises NotFound naming both forms tried.
    """
    for candidate in (name, slugify(name or "")):
        if candidate and state.backend.get_doc(
                _analysis_path(state, slug, candidate)) is not None:
            return candidate
    slugged = slugify(name or "")
    extra = f" (also tried {slugged!r})" if slugged and slugged != name else ""
    raise NotFound(f"analysis {name!r} not found for {slug!r}{extra}")


def update_analysis(
    state: State,
    slug: str,
    name: str,
    *,
    description: str | None = None,
    status: str | None = None,
) -> dict:
    _ensure_paper(state, slug)
    path = _analysis_path(state, slug, resolve_analysis(state, slug, name))
    fields: dict = {"updated_at": now_iso()}
    if description is not None: fields["description"] = description
    if status is not None: fields["status"] = status
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_analysis(state: State, slug: str, name: str) -> dict:
    _ensure_paper(state, slug)
    return state.backend.get_doc(
        _analysis_path(state, slug, resolve_analysis(state, slug, name)))


def list_analyses(state: State, slug: str, *, status: str | None = None) -> list[dict]:
    """List analyses sorted by created_at desc. Optional status filter."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(analyses_base(state, slug))
    items = [data for _, data in pairs]
    if status is not None:
        items = [a for a in items if a.get("status") == status]
    items.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return items


def delete_analysis(state: State, slug: str, name: str) -> bool:
    _ensure_paper(state, slug)
    try:
        stored = resolve_analysis(state, slug, name)
    except NotFound:
        return False          # deleting what is not there stays a quiet False
    state.backend.delete_doc(_analysis_path(state, slug, stored))
    return True

"""Read the user's OTHER projects, for reference.

The MCP session is bound to one project: `state.project_id` is fixed at process
start and every tool builds its paths from it. That is the right default — the
overwhelmingly common mistake is writing into the wrong project, not failing to
read another one.

But a researcher's projects are not independent. Methods carry over, a dataset
registered in one project is the same dataset in the next, and the phrasing that
survived review last time is the phrasing to reuse. So this module opens a
READING window onto the other projects the SAME USER owns.

Three properties hold it together:

1.  **Read-only, enforced, not promised.** The re-scoped view wraps the backend
    in something that raises on every write. The danger is not malice; it is an
    agent that reads a neighbouring paper and then helpfully "fixes" a sentence
    in it. A write into a project the user is not looking at would be very hard
    to notice.

2.  **Ownership is checked here, not just in the rules.** The security rule
    already grants a project only to its owner, so a foreign pid fails anyway —
    as an opaque PERMISSION_DENIED from deep inside the SDK. Checking first
    turns that into a sentence that says what happened.

3.  **Nothing is copied implicitly.** These tools hand back text. Moving
    anything into the active project is a normal write through the normal
    tools, so it shows up in the activity log of the project that received it.
"""
from __future__ import annotations

import dataclasses

from ..backends.base import NotFound
from ..state import State
from . import materials as _materials
from . import papers as _papers


class ReadOnlyViolation(RuntimeError):
    """A write was attempted through a cross-project reading view."""


class _ReadOnlyBackend:
    """Every read passes through; every write raises.

    Deliberately not a Protocol subclass with `pass`-ed writers: the point is a
    loud failure at the moment of the attempt, naming the project, rather than a
    silent no-op that leaves the caller believing it saved something."""

    def __init__(self, inner, project_id: str):
        self._inner = inner
        self._pid = project_id

    def _refuse(self, op: str, path: str):
        raise ReadOnlyViolation(
            f"{op} refused: {path!r} is in project {self._pid!r}, which this "
            f"session is only READING. Switch the MCP to that project to change it."
        )

    # reads
    def get_doc(self, path): return self._inner.get_doc(path)
    def list_collection(self, path): return self._inner.list_collection(path)
    def query_collection(self, path, field, value):
        return self._inner.query_collection(path, field, value)
    def get_blob(self, path): return self._inner.get_blob(path)

    # writes
    def set_doc(self, path, data): self._refuse("set_doc", path)
    def set_doc_merge(self, path, data): self._refuse("set_doc_merge", path)
    def update_doc(self, path, fields): self._refuse("update_doc", path)
    def delete_doc(self, path): self._refuse("delete_doc", path)
    def put_blob(self, path, content): self._refuse("put_blob", path)
    def delete_blob(self, path): self._refuse("delete_blob", path)


def _project_doc(state: State, project_id: str) -> dict:
    pid = (project_id or "").strip()
    if not pid:
        raise ValueError("project_id is required")
    doc = state.backend.get_doc(f"projects/{pid}")
    if doc is None:
        raise NotFound(f"project {pid!r} not found (or not yours)")
    if doc.get("owner_uid") != state.owner_uid:
        # The rules would refuse this too. Saying so here is the difference
        # between a sentence and a PERMISSION_DENIED stack.
        raise PermissionError(
            f"project {pid!r} belongs to another account — cross-project reading "
            f"covers only projects you own"
        )
    return doc


def reading_view(state: State, project_id: str) -> State:
    """A State pointed at another of the user's projects, writes disabled."""
    _project_doc(state, project_id)
    return dataclasses.replace(
        state,
        project_id=project_id,
        backend=_ReadOnlyBackend(state.backend, project_id),
    )


def list_my_projects(state: State) -> list[dict]:
    """Every project this account owns, newest activity first.

    The `projects` collection is not listable — the rule grants a project only
    to its owner, so an unfiltered stream is denied. The owner filter is what
    makes the query legal."""
    rows = state.backend.query_collection("projects", "owner_uid", state.owner_uid)
    out = [
        {
            "project_id": doc_id,
            "name": data.get("name"),
            "description": data.get("description"),
            "archived": bool(data.get("archived")),
            "updated_at": data.get("updated_at"),
            "active": doc_id == state.project_id,
        }
        for doc_id, data in rows
    ]
    out.sort(key=lambda p: (p["active"], p.get("updated_at") or ""), reverse=True)
    return out


def list_project_papers(state: State, project_id: str) -> list[dict]:
    """Papers in another of your projects — slug, title, type, status."""
    view = reading_view(state, project_id)
    return [
        {
            "slug": data.get("slug") or doc_id,
            "title": data.get("title"),
            "doc_type": data.get("doc_type"),
            "journal": data.get("journal"),
            "status": data.get("status"),
            "updated_at": data.get("updated_at"),
        }
        for doc_id, data in view.backend.list_collection(view.project_path("papers"))
    ]


def read_project_paper(
    state: State, project_id: str, slug: str, *, section_key: str | None = None,
) -> dict:
    """Read a paper from another of your projects.

    Returns the paper doc, its sections, and the compiled manuscript. Pass
    `section_key` to get one section instead of the whole thing — a Methods
    section you are adapting is usually all you want, and the whole manuscript
    is a lot of context to spend on it."""
    view = reading_view(state, project_id)
    bundle = _papers.get_paper_state(view, slug)
    if section_key:
        sec = next((s for s in bundle["sections"] if s.get("key") == section_key), None)
        if sec is None:
            raise NotFound(
                f"section {section_key!r} not in {slug!r} — has: "
                + ", ".join(s.get("key", "?") for s in bundle["sections"])
            )
        return {"project_id": project_id, "slug": slug, "section": sec,
                "paper_title": bundle["paper"].get("title")}
    return {
        "project_id": project_id,
        "slug": slug,
        "paper": bundle["paper"],
        "sections": bundle["sections"],
        "manuscript": bundle["manuscript"],
    }


def read_project_memory(state: State, project_id: str) -> dict:
    """The other project's memory document — its accumulated working notes."""
    view = reading_view(state, project_id)
    doc = view.backend.get_doc(view.project_path("memory", "main")) or {}
    return {"project_id": project_id, "content": doc.get("content") or "",
            "updated_at": doc.get("updated_at")}


def list_project_materials(state: State, project_id: str) -> list[dict]:
    """Materials in another of your projects. Fetch one with
    get_project_material."""
    return _materials.list_materials(reading_view(state, project_id))


def get_project_material(
    state: State, project_id: str, material_id: str, *,
    dest_dir: str = ".", dest_path: str | None = None,
) -> dict:
    """Download a material from another of your projects to local disk.

    The local write is yours to make; the read-only guard covers the CLOUD, not
    your working directory."""
    view = reading_view(state, project_id)
    out = _materials.get_material(
        view, material_id, dest_dir=dest_dir, dest_path=dest_path)
    return {**out, "project_id": project_id}


def search_my_papers(state: State, query: str) -> list[dict]:
    """Find papers across ALL your projects by title/journal substring.

    The lookup you actually need when you remember writing something but not
    where: it answers "which project", which is the question every other tool
    here assumes you have already answered."""
    needle = (query or "").strip().lower()
    if not needle:
        raise ValueError("query is required")
    hits: list[dict] = []
    for proj in list_my_projects(state):
        pid = proj["project_id"]
        try:
            papers = list_project_papers(state, pid)
        except (PermissionError, NotFound):   # racing a delete, or not ours
            continue
        for p in papers:
            haystack = " ".join(str(p.get(k) or "")
                                for k in ("title", "slug", "journal")).lower()
            if needle in haystack:
                hits.append({**p, "project_id": pid, "project_name": proj["name"],
                             "active": proj["active"]})
    return hits

"""Paper-level CRUD: create, list, get state, update, delete.

Paths used:
    users/{uid}/papers/{slug}                          ← paper doc
    users/{uid}/papers/{slug}/sections/{key}           ← section docs
    blob users/{uid}/papers/{slug}/manuscript.md       ← regenerated on write
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..manuscript import DOC_TYPES, compile_manuscript, sections_for_doc_type
from ..state import State
from ..util import now_iso, slugify, word_count
from .activity import log_event


def _paper_path(state: State, slug: str) -> str:
    return state.project_path("papers", slug)


def _section_path(state: State, slug: str, key: str) -> str:
    return state.project_path("papers", slug, "sections", key)


def _manuscript_blob_path(state: State, slug: str) -> str:
    return state.project_path("papers", slug, "manuscript.md")


def _regenerate_manuscript(state: State, slug: str) -> None:
    """Read all section docs for `slug` and rewrite the manuscript blob."""
    paper = state.backend.get_doc(_paper_path(state, slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    sections = [data for _, data in state.backend.list_collection(
        state.project_path("papers", slug, "sections")
    )]
    text = compile_manuscript(paper, sections)
    state.backend.put_blob(_manuscript_blob_path(state, slug), text)


def create_paper(
    state: State,
    *,
    title: str,
    slug: str | None = None,
    authors: list[str] | None = None,
    journal: str | None = None,
    abstract: str | None = None,
    target_date: str | None = None,
    doc_type: str = "paper",
) -> dict:
    """Create a new document and seed its sections.

    `doc_type` is one of "paper", "report", "other". Only "paper" seeds the
    canonical section scaffold (abstract/intro/methods/results/discussion/
    conclusion); reports and other docs start with no sections so the author
    structures them freely. doc_type also drives the export engine
    (paper → pandoc, others → python-docx).

    Returns the created paper doc (without sections).
    """
    if not title or not title.strip():
        raise ValueError("title is required")
    doc_type = (doc_type or "paper").strip().lower()
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}, got {doc_type!r}")
    slug = (slug or slugify(title)).strip("-")
    if not slug:
        raise ValueError("could not derive a valid slug from title")

    path = _paper_path(state, slug)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"paper already exists: {slug!r}")

    now = now_iso()
    paper = {
        "owner_uid": state.owner_uid,
        "project_id": state.project_id,
        "slug": slug,
        "title": title.strip(),
        "authors": list(authors or []),
        "journal": journal,
        "doc_type": doc_type,
        "status": "draft",
        "target_date": target_date,
        "abstract": abstract,
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(path, paper)

    # Seed sections per type (papers get the canonical scaffold; others none).
    for i, (key, section_title) in enumerate(sections_for_doc_type(doc_type)):
        body = abstract if (key == "abstract" and abstract) else ""
        state.backend.set_doc(
            _section_path(state, slug, key),
            {
                "key": key,
                "title": section_title,
                "body": body,
                "word_count": word_count(body),
                "status": "pending",
                "sort_order": i,
                "updated_at": now,
            },
        )

    _regenerate_manuscript(state, slug)
    log_event(state, slug, action="paper_created",
              detail={"title": title, "journal": journal, "doc_type": doc_type})
    return {**paper, "dashboard_url": state.dashboard_url("papers", slug)}


def list_papers(state: State) -> list[dict]:
    """List all papers for the active user, ordered by `updated_at` desc."""
    pairs = state.backend.list_collection(state.project_path("papers"))
    papers = [data for _, data in pairs]
    papers.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return papers


def get_paper_state(state: State, slug: str) -> dict:
    """Return paper doc + sections + manuscript text in one bundle."""
    paper = state.backend.get_doc(_paper_path(state, slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    sections = [
        data
        for _, data in state.backend.list_collection(
            state.project_path("papers", slug, "sections")
        )
    ]
    sections.sort(key=lambda s: s.get("sort_order", 999))
    manuscript_bytes = state.backend.get_blob(_manuscript_blob_path(state, slug))
    return {
        "paper": paper,
        "sections": sections,
        "manuscript": manuscript_bytes.decode("utf-8") if manuscript_bytes else "",
    }


def update_paper(
    state: State,
    slug: str,
    *,
    title: str | None = None,
    journal: str | None = None,
    status: str | None = None,
    target_date: str | None = None,
    authors: list[str] | None = None,
    abstract: str | None = None,
    doc_type: str | None = None,
) -> dict:
    """Patch a paper's metadata fields. Only non-None values are applied.

    `abstract` updates the paper-doc metadata field AND mirrors into the
    `abstract` section body (the source of truth the dashboard renders and
    export/word-count read), so the two never drift apart.
    """
    path = _paper_path(state, slug)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    fields: dict = {"updated_at": now_iso()}
    if title is not None: fields["title"] = title.strip()
    if journal is not None: fields["journal"] = journal
    if status is not None: fields["status"] = status
    if target_date is not None: fields["target_date"] = target_date
    if authors is not None: fields["authors"] = list(authors)
    if abstract is not None: fields["abstract"] = abstract
    if doc_type is not None:
        dt = doc_type.strip().lower()
        if dt not in DOC_TYPES:
            raise ValueError(f"doc_type must be one of {DOC_TYPES}, got {doc_type!r}")
        fields["doc_type"] = dt
    state.backend.update_doc(path, fields)
    if abstract is not None:
        sec_path = _section_path(state, slug, "abstract")
        if state.backend.get_doc(sec_path) is not None:
            state.backend.update_doc(sec_path, {
                "body": abstract,
                "word_count": word_count(abstract),
                "updated_at": fields["updated_at"],
            })
    if title is not None or abstract is not None:
        _regenerate_manuscript(state, slug)
    return state.backend.get_doc(path)


def delete_paper(state: State, slug: str) -> bool:
    """Delete a paper, all its sections, reviews, and manuscript blob.

    Returns True if the paper existed.
    """
    path = _paper_path(state, slug)
    if state.backend.get_doc(path) is None:
        return False
    # Subcollections first — include activity_log so delete is fully clean
    for col in ("sections", "reviews", "activity_log", "figures", "tables",
                "references", "analyses", "exports", "assets"):
        for doc_id, _ in state.backend.list_collection(
            state.project_path("papers", slug, col)
        ):
            state.backend.delete_doc(state.project_path("papers", slug, col, doc_id))
    state.backend.delete_blob(_manuscript_blob_path(state, slug))
    state.backend.delete_doc(path)
    return True

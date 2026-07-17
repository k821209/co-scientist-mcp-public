"""Paper-level CRUD: create, list, get state, update, delete.

Paths used:
    users/{uid}/papers/{slug}                          ← paper doc
    users/{uid}/papers/{slug}/sections/{key}           ← section docs
    blob users/{uid}/papers/{slug}/manuscript.md       ← regenerated on write
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..manuscript import (
    DOC_TYPES, compile_manuscript, sections_for_doc_type,
    format_author_block, normalize_affiliations, normalize_authors,
)
from ..state import State
from ..util import new_id, now_iso, slugify, word_count
from . import affiliations as _affiliations
from . import authors as _authors
from . import limits as _limits
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
    # Non-Latin titles now slugify to their own letters (한글 등); only a title
    # with no letters/digits at all (emoji/punctuation) yields "" — fall back to
    # a generated id so creation never fails on an otherwise-valid title.
    slug = (slug or slugify(title)).strip("-") or f"paper-{new_id()[:8]}"

    path = _paper_path(state, slug)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"paper already exists: {slug!r}")

    _limits.enforce_cap(
        len(state.backend.list_collection(state.project_path("papers"))),
        _limits.PAPERS_PER_PROJECT, "papers per project",
    )

    now = now_iso()
    paper = {
        "owner_uid": state.owner_uid,
        "project_id": state.project_id,
        "slug": slug,
        "title": title.strip(),
        "authors": normalize_authors(authors),
        "affiliations": [],
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
    """List all papers for the active user, ordered by `updated_at` desc.

    Authors + affiliations are normalized to the same canonical (stored-order)
    shape get_paper_state returns, so the author order is consistent everywhere
    (list == detail == export)."""
    pairs = state.backend.list_collection(state.project_path("papers"))
    papers = [data for _, data in pairs]
    for p in papers:
        p["authors"] = normalize_authors(p.get("authors"))
        p["affiliations"] = normalize_affiliations(p.get("affiliations"))
    papers.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return papers


def get_paper_state(state: State, slug: str) -> dict:
    """Return paper doc + sections + manuscript text in one bundle."""
    paper = state.backend.get_doc(_paper_path(state, slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    # Normalize legacy list[str] authors + the affiliation list on read.
    paper["authors"] = normalize_authors(paper.get("authors"))
    paper["affiliations"] = normalize_affiliations(paper.get("affiliations"))
    paper["author_block"] = format_author_block(paper)
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
    if authors is not None: fields["authors"] = normalize_authors(authors)
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
    if title is not None or abstract is not None or authors is not None:
        _regenerate_manuscript(state, slug)
    return state.backend.get_doc(path)


def set_paper_authors(state: State, slug: str, authors: list) -> dict:
    """Replace a paper's ordered author list. `authors` is a list of dicts
    (`name` required; optional `affiliation`/`affiliation_ids`/`email`/`orcid`/
    `corresponding`) or plain name strings. Each author is also upserted into
    the account author library by name — carrying their affiliation mapping —
    so reusing them on another paper brings it along. Returns the paper doc."""
    path = _paper_path(state, slug)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    normalized = normalize_authors(authors)
    # Derive a display affiliation from affiliation_ids when the free-text is
    # empty, so list_authors / dashboard / export never show a blank for an
    # author linked only via the numbered list (feedback 147c27455598).
    for a in normalized:
        if not a.get("affiliation") and a.get("affiliation_ids"):
            texts = _affiliations.resolve_texts(state, a["affiliation_ids"])
            if texts:
                a["affiliation"] = "; ".join(texts)
    state.backend.update_doc(path, {"authors": normalized, "updated_at": now_iso()})
    # Keep the account author library in sync (upsert by name).
    for a in normalized:
        try:
            _authors.upsert_author_by_name(
                state, a["name"], affiliation=a.get("affiliation", ""),
                email=a.get("email", ""), orcid=a.get("orcid", ""),
                affiliation_ids=a.get("affiliation_ids"))
        except Exception:
            pass  # library sync is best-effort; never fail the paper write
    # Recompile the manuscript blob so the exported author block reflects the
    # new list (export reads the stored blob — feedback 001ed42b1fee).
    _regenerate_manuscript(state, slug)
    log_event(state, slug, action="paper_authors_set",
              detail={"count": len(normalized)})
    doc = state.backend.get_doc(path)
    doc["authors"] = normalize_authors(doc.get("authors"))
    return doc


def set_paper_affiliations(state: State, slug: str, affiliations: list) -> dict:
    """Replace a paper's ordered affiliation list (the numbered list authors
    reference by id). `affiliations` is a list of dicts ({id?, text}) or plain
    strings; de-duplicated by text, order preserved. Returns the updated paper."""
    path = _paper_path(state, slug)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    # Unify id spaces: upsert each affiliation into the account library by text
    # and use the LIBRARY id, so a paper affiliation IS a library entry — then
    # update_affiliation propagates, and the same text never gets two ids.
    unified: list[dict] = []
    seen: set = set()
    for a in normalize_affiliations(affiliations):
        lib = _affiliations.add_affiliation(state, a["text"])   # idempotent on text
        if lib["id"] in seen:
            continue
        seen.add(lib["id"])
        unified.append({"id": lib["id"], "text": a["text"]})
    state.backend.update_doc(path, {"affiliations": unified, "updated_at": now_iso()})
    _regenerate_manuscript(state, slug)   # refresh the exported author block
    log_event(state, slug, action="paper_affiliations_set",
              detail={"count": len(unified)})
    doc = state.backend.get_doc(path)
    doc["affiliations"] = normalize_affiliations(doc.get("affiliations"))
    return doc


SUBMISSION_STATUSES = (
    "submitted", "under_review", "major_revision", "minor_revision",
    "accepted", "in_press", "published", "rejected",
)


def set_paper_submission(state: State, slug: str, *, status: str,
                         journal: str | None = None, submitted_at: str | None = None,
                         manuscript_id: str | None = None, url: str | None = None,
                         decision_at: str | None = None, notes: str | None = None) -> dict:
    """Set (or clear) a paper's journal-submission status — the peer-review
    pipeline stage shown on the paper card + Paper tab. `status` is one of
    SUBMISSION_STATUSES, or "" / "none" to clear (mark not submitted). Optional
    metadata (journal, submitted_at, manuscript_id, url, decision_at, notes) is
    merged in. Distinct from the writing `status` (draft/complete)."""
    path = _paper_path(state, slug)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    status = (status or "").strip().lower()
    if status in ("", "none", "not_submitted"):
        state.backend.update_doc(path, {"submission": {}, "updated_at": now_iso()})
        return state.backend.get_doc(path)
    if status not in SUBMISSION_STATUSES:
        raise ValueError(f"status must be one of {SUBMISSION_STATUSES} (or empty to clear)")
    sub = dict(existing.get("submission") or {})
    sub["status"] = status
    for k, v in {"journal": journal, "submitted_at": submitted_at,
                 "manuscript_id": manuscript_id, "url": url,
                 "decision_at": decision_at, "notes": notes}.items():
        if v is not None:
            sub[k] = v.strip() if isinstance(v, str) else v
    sub["updated_at"] = now_iso()
    state.backend.update_doc(path, {"submission": sub, "updated_at": now_iso()})
    log_event(state, slug, action="paper_submission_set", detail={"status": status})
    return state.backend.get_doc(path)


def resync_paper_affiliations(state: State, slug: str) -> dict:
    """Opt-in: refresh a paper's cached affiliation TEXT from the account
    library by id. Papers snapshot the text at insert time (a point-in-time
    record — a corrected/renamed institution must NOT silently rewrite a
    submitted/published paper), so this is user-triggered and never automatic.
    Only entries whose id still exists in the library are updated; ids are
    unchanged, so author superscript mappings are preserved. Returns the paper."""
    path = _paper_path(state, slug)
    paper = state.backend.get_doc(path)
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    affs = normalize_affiliations(paper.get("affiliations"))
    lib = {a["id"]: a["text"] for a in _affiliations.list_affiliations(state)}
    changed = 0
    for a in affs:
        if a["id"] in lib and lib[a["id"]] != a["text"]:
            a["text"] = lib[a["id"]]
            changed += 1
    state.backend.update_doc(path, {"affiliations": affs, "updated_at": now_iso()})
    if changed:
        _regenerate_manuscript(state, slug)   # refresh the exported author block
    log_event(state, slug, action="paper_affiliations_resynced",
              detail={"changed": changed})
    doc = state.backend.get_doc(path)
    doc["affiliations"] = normalize_affiliations(doc.get("affiliations"))
    doc["resynced"] = changed
    return doc


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

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


# What a session-start "which papers exist?" call actually needs. The full doc
# carries the whole journal-requirements notes blob per paper, so seven papers
# cost a large slice of context to answer a question the summary answers
# (feedback 68c41dc91fef).
SUMMARY_FIELDS = ("slug", "title", "journal", "doc_type", "status",
                  "updated_at", "created_at")


def list_papers(
    state: State,
    *,
    summary: bool = False,
    fields: list[str] | None = None,
) -> list[dict]:
    """List all papers for the active user, ordered by `updated_at` desc.

    Authors + affiliations are normalized to the same canonical (stored-order)
    shape get_paper_state returns, so the author order is consistent everywhere
    (list == detail == export).

    `summary=True` returns only SUMMARY_FIELDS; `fields=[...]` picks explicitly
    (`slug` is always kept, so a row is always identifiable). Both exist because
    the full record includes the journal-requirements notes, which makes a
    seven-paper project an expensive way to ask "what is here".
    """
    pairs = state.backend.list_collection(state.project_path("papers"))
    papers = [data for _, data in pairs]
    for p in papers:
        p["authors"] = normalize_authors(p.get("authors"))
        p["affiliations"] = normalize_affiliations(p.get("affiliations"))
    papers.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    keep = set(fields) | {"slug"} if fields else (
        set(SUMMARY_FIELDS) if summary else None)
    if keep is None:
        return papers
    return [{k: v for k, v in p.items() if k in keep} for p in papers]


def _sentences_for_drop_check(text: str) -> list[str]:
    """Sentence-ish pieces of an abstract, for noticing what an overwrite
    would delete. Deliberately crude: it only has to recognise a clause that
    vanished, not parse prose."""
    import re
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [" ".join(p.split()) for p in parts if len(" ".join(p.split())) >= 25]


def abstract_drop_warnings(current: str, incoming: str) -> list[str]:
    """Sentences the section has that `incoming` does not.

    `paper.abstract` and the `abstract` section used to drift — the section
    could be edited without the field following — and then
    `update_paper(abstract=…)` wrote the stale field over the section and an
    author's clause from months earlier was gone, with a plausible word count
    and no warning (feedback 5862140d9f73). Both directions now mirror, so
    they cannot drift again; this catches the other way to lose text, which is
    writing from something read before someone else edited it."""
    if not (current or "").strip():
        return []
    incoming_flat = " ".join((incoming or "").split())
    dropped = [s for s in _sentences_for_drop_check(current) if s not in incoming_flat]
    if not dropped:
        return []
    shown = "; ".join(f'"{s[:90]}…"' if len(s) > 90 else f'"{s}"' for s in dropped[:3])
    more = f" (+{len(dropped) - 3} more)" if len(dropped) > 3 else ""
    return [
        f"{len(dropped)} sentence(s) present in the abstract section are missing from "
        f"the text just written, and have been replaced: {shown}{more}. If that was "
        f"not intended, the previous text is above — put it back with "
        f"update_section(slug, 'abstract', body=…)."
    ]


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
    if not paper.get("submission_sync"):
        # Papers whose submission was registered before the flag existed have
        # nothing here, and would read as "no submission to reconcile" — the
        # opposite of true. Derived on read, not backfilled on write: a
        # migration would stamp `unreconciled` over papers someone had already
        # reconciled by hand, re-asking a question they had answered.
        from .submissions import _derive_sync
        derived = _derive_sync(state, slug)
        if derived:
            paper["submission_sync"] = derived
    # A paper that drifted BEFORE both directions mirrored still has two
    # different abstracts, and `paper.abstract` is the natural place for an
    # agent to read one from. Say so rather than let it be read as current.
    section_abstract = next(
        (sec.get("body") or "" for sec in sections if sec.get("key") == "abstract"), None)
    if section_abstract is not None:
        field = " ".join((paper.get("abstract") or "").split())
        body = " ".join(section_abstract.split())
        if field and body and field != body:
            paper["abstract_sync"] = {
                "state": "diverged",
                "note": ("paper.abstract and the abstract SECTION hold different text. "
                         "The section is what the dashboard renders and what export and "
                         "word counts read, so treat it as the live one. Writing either "
                         "now mirrors into the other; update_section(slug, 'abstract') "
                         "settles it."),
            }
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
    export/word-count read). `update_section(slug, "abstract")` mirrors back
    the other way, so the two cannot drift — they did, and then this call
    wrote the stale field over a months-old author edit (feedback
    5862140d9f73).

    Returns `warnings` when the incoming abstract drops whole sentences the
    section had: replacing text is a legitimate edit, writing from a copy that
    someone else has since edited is not, and the two look identical from here.
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
    warnings: list[str] = []
    if abstract is not None:
        sec_path = _section_path(state, slug, "abstract")
        section = state.backend.get_doc(sec_path)
        if section is not None:
            warnings = abstract_drop_warnings(section.get("body") or "", abstract)
            state.backend.update_doc(sec_path, {
                "body": abstract,
                "word_count": word_count(abstract),
                "updated_at": fields["updated_at"],
            })
    if title is not None or abstract is not None or authors is not None:
        _regenerate_manuscript(state, slug)
    out = state.backend.get_doc(path)
    if warnings:
        return {**out, "warnings": warnings}
    return out


def set_paper_authors(state: State, slug: str, authors: list) -> dict:
    """Replace a paper's ordered author list. `authors` is a list of dicts
    (`name` required; optional `affiliation`/`affiliation_ids`/`email`/`orcid`/
    `corresponding`/`equal_contribution`) or plain name strings. In the exported
    author block `corresponding` renders a † (all corresponding emails are
    listed) and `equal_contribution` renders a * with a shared "contributed
    equally" footnote — distinct symbols so an author can carry both. Each
    author is also upserted into the account author library by name — carrying
    their affiliation mapping — so reusing them on another paper brings it
    along. Returns the paper doc."""
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


def get_paper_affiliations(state: State, slug: str) -> list[dict]:
    """The affiliation records THIS paper references — read-only.

    `list_affiliations` is account-wide (29 rows on one account, five of them
    the same department with different trailing address detail), and the only
    way to learn which ones a paper used was `resync_paper_affiliations` — a
    WRITE. So the safe question could only be asked by mutating, and matching
    by text against the rendered header picks whichever variant the paper
    happens to cache (feedback 3f1ed9ac0012).

    Each entry carries the paper's cached text, the library's current text, and
    whether the two agree — a `needs_resync` that is visible before an export
    rather than after diffing one.
    """
    paper = state.backend.get_doc(_paper_path(state, slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    lib = {a["id"]: a.get("text") for a in _affiliations.list_affiliations(state)}
    authors = paper.get("authors") or []
    out: list[dict] = []
    for index, entry in enumerate(normalize_affiliations(paper.get("affiliations")), 1):
        aff_id = entry.get("id")
        library_text = lib.get(aff_id)
        out.append({
            "id": aff_id,
            # The superscript a reader sees, so a correction can be aimed by eye.
            "number": index,
            "text": entry.get("text"),
            "library_text": library_text,
            "in_library": aff_id in lib,
            "needs_resync": bool(library_text and library_text != entry.get("text")),
            "authors": [a.get("name") for a in authors
                        if aff_id in (a.get("affiliation_ids") or [])],
        })
    return out


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

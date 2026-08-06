"""Tables: pure-doc; the content is a markdown table inside the doc.

No blob storage — table content is small (~KB) and lives entirely in
Firestore. Mirrors the original `paper_tables` schema.

Supplementary tables follow the same offset convention as figures
(`table_number >= 101` are STables).
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from . import limits as _limits
from .figures import SUPPLEMENTARY_NUMBER_OFFSET
from .papers import _paper_path


def _table_path(state: State, slug: str, table_number: int) -> str:
    return state.project_path("papers", slug, "tables", str(table_number))


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


def add_table(
    state: State,
    slug: str,
    *,
    table_number: int,
    title: str,
    content: str,
    caption: str | None = None,
    status: str = "pending",
    source_analysis: str | None = None,
) -> dict:
    """Create a table. `source_analysis` names the analysis whose outputs this
    table is built from; setting it lets `prepare_export` warn when the analysis
    has re-run since the table was last updated (see exports.prepare_export)."""
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"table {table_number} already exists for {slug!r}")
    _limits.enforce_cap(
        len(state.backend.list_collection(state.project_path("papers", slug, "tables"))),
        _limits.TABLES_PER_PAPER, "tables per paper",
    )
    now = now_iso()
    doc = {
        "table_number": table_number,
        "title": title,
        "content": content,
        "caption": caption,
        "status": status,
        "source_analysis": source_analysis,
        "created_at": now,
        "updated_at": now,
        # When the DATA last changed, as opposed to any field on the row. The
        # staleness check in prepare_export compares against this, because
        # `updated_at` moves for a caption fix or for adding the provenance link
        # itself — which would mark a stale artifact fresh. See update_table.
        "content_updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def update_table(
    state: State,
    slug: str,
    table_number: int,
    *,
    title: str | None = None,
    content: str | None = None,
    caption: str | None = None,
    status: str | None = None,
    source_analysis: str | None = None,
) -> dict:
    """Update a table. `source_analysis` links it to the analysis that generates
    it, which is what lets `prepare_export` catch a table left behind by a rerun."""
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"table {table_number} not found for {slug!r}")
    now = now_iso()
    fields: dict = {"updated_at": now}
    if title is not None: fields["title"] = title
    if content is not None: fields["content"] = content
    if caption is not None: fields["caption"] = caption
    if status is not None: fields["status"] = status
    if source_analysis is not None: fields["source_analysis"] = source_analysis

    # Keep "when the data changed" separate from "when the row changed".
    #
    # Rows created before this field existed have no content_updated_at, so seed
    # it from the CURRENT updated_at *before* overwriting that — otherwise the
    # very call that adds the provenance link (a metadata-only edit) would assert
    # the artifact is fresh and permanently mask the staleness it was added to
    # detect. Retro-linking existing artifacts is the normal path, not an edge
    # case, so this seeding is what makes the check usable at all.
    if not existing.get("content_updated_at"):
        fields["content_updated_at"] = (
            existing.get("updated_at") or existing.get("created_at") or now
        )
    if content is not None:          # the data itself was replaced
        fields["content_updated_at"] = now
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_table(state: State, slug: str, table_number: int) -> dict:
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_table_path(state, slug, table_number))
    if doc is None:
        raise NotFound(f"table {table_number} not found for {slug!r}")
    return doc


def list_tables(state: State, slug: str, *, supplementary: bool | None = False) -> list[dict]:
    """List tables. supplementary=False → main only (default), True → STables
    only, None → all (main + supplementary)."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "tables"))
    tables = [data for _, data in pairs]
    if supplementary is not None:
        tables = [t for t in tables
                  if (supplementary and t["table_number"] >= SUPPLEMENTARY_NUMBER_OFFSET)
                  or (not supplementary and t["table_number"] < SUPPLEMENTARY_NUMBER_OFFSET)]
    tables.sort(key=lambda t: t["table_number"])
    return tables


def delete_table(state: State, slug: str, table_number: int) -> bool:
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

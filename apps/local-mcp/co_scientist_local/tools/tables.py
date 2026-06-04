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
) -> dict:
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"table {table_number} already exists for {slug!r}")
    now = now_iso()
    doc = {
        "table_number": table_number,
        "title": title,
        "content": content,
        "caption": caption,
        "status": status,
        "created_at": now,
        "updated_at": now,
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
) -> dict:
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"table {table_number} not found for {slug!r}")
    fields: dict = {"updated_at": now_iso()}
    if title is not None: fields["title"] = title
    if content is not None: fields["content"] = content
    if caption is not None: fields["caption"] = caption
    if status is not None: fields["status"] = status
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_table(state: State, slug: str, table_number: int) -> dict:
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_table_path(state, slug, table_number))
    if doc is None:
        raise NotFound(f"table {table_number} not found for {slug!r}")
    return doc


def list_tables(state: State, slug: str, *, supplementary: bool = False) -> list[dict]:
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "tables"))
    tables = [data for _, data in pairs]
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

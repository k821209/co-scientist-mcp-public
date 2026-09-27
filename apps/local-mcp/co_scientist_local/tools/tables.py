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
from .figures import SUPPLEMENTARY_NUMBER_OFFSET, is_supplementary_number
from .papers import _paper_path
from .provenance import NO_PROVENANCE_HINT as _NO_PROVENANCE_HINT, is_linked, is_manual, normalize_varies


def _table_path(state: State, slug: str, table_number: int) -> str:
    return state.project_path("papers", slug, "tables", str(table_number))


# The registration hint lives in tools/provenance.py (one copy for tables and
# figures). Returned, never stored, and never an error at registration time —
# check_requirements is where a numeric table without a link fails.


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
    source_runs: list[str] | None = None,
    varies: list[str] | str | None = None,
) -> dict:
    """Create a table. `source_analysis` names the analysis whose outputs this
    table is built from; setting it lets `prepare_export` warn when the analysis
    has re-run since the table was last updated (see exports.prepare_export).
    `source_runs` names the run(s) whose outputs are the rows, and `varies` the
    param key(s) the rows are supposed to differ in — see compare_run_params."""
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
        "source_runs": list(source_runs) if source_runs else None,
        "varies": normalize_varies(varies),
        "created_at": now,
        "updated_at": now,
        # When the DATA last changed, as opposed to any field on the row. The
        # staleness check in prepare_export compares against this, because
        # `updated_at` moves for a caption fix or for adding the provenance link
        # itself — which would mark a stale artifact fresh. See update_table.
        "content_updated_at": now,
    }
    state.backend.set_doc(path, doc)
    if not is_linked(source_analysis) and not is_manual(source_analysis):
        return {**doc, "provenance_hint": _NO_PROVENANCE_HINT}
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
    source_runs: list[str] | None = None,
    varies: list[str] | str | None = None,
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
    if source_runs is not None: fields["source_runs"] = list(source_runs) or None
    if varies is not None: fields["varies"] = normalize_varies(varies)

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


def get_table(state: State, slug: str, table_number: int, *,
              fields: list[str] | None = None) -> dict:
    """`fields` narrows the doc to those keys (plus `table_number`): a legend
    audit across eleven supplementary tables should not pull every grid."""
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_table_path(state, slug, table_number))
    if doc is None:
        raise NotFound(f"table {table_number} not found for {slug!r}")
    if fields:
        keep = set(fields) | {"table_number"}
        return {k: v for k, v in doc.items() if k in keep}
    return doc


_TABLE_TEXT_FIELDS = ("title", "content", "caption")


def replace_in_table(
    state: State, slug: str, table_number: int, *, field: str, old: str, new: str,
    count: int | None = 1,
) -> dict:
    """A partial edit of one text field (title / content / caption) — exact
    match or fail, see util.exact_replace. A one-word fix in a 20-row grid
    used to cost re-sending the grid, the likeliest way to drop a row."""
    from ..util import exact_replace
    if field not in _TABLE_TEXT_FIELDS:
        raise ValueError(f"field must be one of {_TABLE_TEXT_FIELDS}")
    doc = get_table(state, slug, table_number)
    text, n = exact_replace(doc.get(field) or "", old, new, count)
    out = update_table(state, slug, table_number, **{field: text})
    return {**out, "replaced": n}


def search_tables(
    state: State, slug: str, pattern: str, *, supplementary: bool | None = None,
    regex: bool = False,
) -> list[dict]:
    """Which tables mention `pattern` (substring, or a regex), where, and how
    often — one call instead of get_table on every table. Each hit: table_number,
    title, `matches` = {field: count}, and one `snippet` per field."""
    import re
    rx = re.compile(pattern if regex else re.escape(pattern))
    out = []
    for t in list_tables(state, slug, supplementary=supplementary):
        matches, snippets = {}, {}
        for f in _TABLE_TEXT_FIELDS:
            text = t.get(f) or ""
            hits = list(rx.finditer(text))
            if hits:
                matches[f] = len(hits)
                a = hits[0].start()
                snippets[f] = text[max(0, a - 40):a + len(hits[0].group(0)) + 40].replace("\n", " ")
        if matches:
            out.append({"table_number": t["table_number"], "title": t.get("title"),
                        "matches": matches, "snippet": snippets})
    return out


def list_tables(state: State, slug: str, *, supplementary: bool | None = False) -> list[dict]:
    """List tables. supplementary=False → main only (default), True → STables
    only, None → all (main + supplementary)."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "tables"))
    tables = [data for _, data in pairs]
    if supplementary is not None:
        tables = [t for t in tables
                  if is_supplementary_number(t["table_number"]) == supplementary]
    tables.sort(key=lambda t: t["table_number"])
    return tables


def delete_table(state: State, slug: str, table_number: int) -> bool:
    _ensure_paper(state, slug)
    path = _table_path(state, slug, table_number)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

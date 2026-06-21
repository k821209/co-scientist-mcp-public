"""Reorder supplementary figures / tables — renumber + blob move + ref remap.

Supplementary items are keyed by their number (figure_number / table_number
≥ 101) — the Firestore doc id IS the number, and a figure's blob path embeds it
(`figure_{n}.png`). So "reordering" means moving each doc to a new number-keyed
id and, for figures, copying the stored image to the new number's blob path.
That copy happens server-side here (read bytes → write new path → delete old),
so NO human re-upload is needed.

Body cross-references are handled too:
  - deterministic, auto-rewritten: `{fig:N}` / `{tab:N}` tokens and
    `![](figure:N)` image embeds (collision-safe single pass);
  - freeform prose ("Supplementary Figure 1", "Fig. S2", "SFig 3", …): only
    DETECTED and reported — rewriting prose risks mangling formatting, so the
    caller (the /reorder-supplementary skill) updates those deliberately from
    the returned report.

The number move is done in two phases (old → temp → final) so an item never
collides with an id that's still occupied.
"""
from __future__ import annotations

import pathlib
import re

from ..backends.base import NotFound
from ..state import State
from .figures import SUPPLEMENTARY_NUMBER_OFFSET, _figure_blob_path, _figure_path
from . import sections as _sections
from .tables import _table_path

_TEMP_OFFSET = 900000


def _safe_int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def reorder_supplementary(
    state: State, slug: str, kind: str, order: list[int],
) -> dict:
    """Renumber the supplementary figures or tables of `slug` into the sequence
    given by `order` (a list of the CURRENT supplementary numbers, ≥101, in the
    desired new order). They are reassigned to 101, 102, … in that order.

    Returns a report:
        {
          reordered: bool,
          kind, mapping: {old: new},        # raw numbers (≥101)
          tokens_updated, embeds_updated,   # deterministic refs auto-rewritten
          sections_changed: [keys],
          prose_mentions: [{section, text, suggest}],  # review/fix manually
        }
    """
    if kind not in ("figure", "table"):
        raise ValueError("kind must be 'figure' or 'table'")
    if state.backend.get_doc(_sections._paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")

    coll = "figures" if kind == "figure" else "tables"
    num_field = "figure_number" if kind == "figure" else "table_number"

    items = state.backend.list_collection(state.project_path("papers", slug, coll))
    current = sorted(
        n for did, d in items
        if (n := (d.get(num_field) if isinstance(d.get(num_field), int) else _safe_int(did)))
        is not None and n >= SUPPLEMENTARY_NUMBER_OFFSET
    )
    if not current:
        raise ValueError(f"no supplementary {kind}s to reorder for {slug!r}")
    if sorted(order) != current:
        raise ValueError(
            f"order must be a permutation of the current supplementary "
            f"{kind} numbers {current}, got {sorted(order)}"
        )

    mapping = {old: SUPPLEMENTARY_NUMBER_OFFSET + 1 + i for i, old in enumerate(order)}
    moves = {o: n for o, n in mapping.items() if o != n}
    if not moves:
        return {
            "reordered": False, "kind": kind, "mapping": mapping,
            "tokens_updated": 0, "embeds_updated": 0,
            "sections_changed": [], "prose_mentions": [],
        }

    # Two-phase number move: old → temp → final (never collide with a live id).
    temp = {}
    for idx, old in enumerate(moves):
        t = _TEMP_OFFSET + idx
        temp[old] = t
        _move_item(state, slug, kind, old, t, num_field)
    for old, t in temp.items():
        _move_item(state, slug, kind, t, moves[old], num_field)

    report = _remap_references(state, slug, kind, mapping)
    return {"reordered": True, "kind": kind, "mapping": mapping, **report}


def _move_item(state: State, slug: str, kind: str, old: int, new: int, num_field: str) -> None:
    if kind == "figure":
        old_path, new_path = _figure_path(state, slug, old), _figure_path(state, slug, new)
    else:
        old_path, new_path = _table_path(state, slug, old), _table_path(state, slug, new)
    doc = state.backend.get_doc(old_path)
    if doc is None:
        raise NotFound(f"{kind} {old} not found for {slug!r}")
    doc = {**doc, num_field: new}
    if isinstance(doc.get("id"), str):
        doc["id"] = str(new)

    if kind == "figure":
        old_blob = doc.get("blob_path")
        if old_blob:
            ext = pathlib.Path(old_blob).suffix.lstrip(".") or "png"
            new_blob = _figure_blob_path(state, slug, new, ext)
            data = state.backend.get_blob(old_blob)
            if data is not None:
                state.backend.put_blob(new_blob, data)
                doc["blob_path"] = new_blob
                state.backend.delete_blob(old_blob)

    state.backend.set_doc(new_path, doc)
    state.backend.delete_doc(old_path)


def _remap_references(state: State, slug: str, kind: str, mapping: dict[int, int]) -> dict:
    """Auto-rewrite deterministic refs in section bodies; detect+report prose."""
    token = "fig" if kind == "figure" else "tab"
    tok_re = re.compile(r"\{" + token + r":(\d+)\}")
    embed_re = re.compile(r"(!\[[^\]]*\]\(figure:)(\d+)(\))")
    if kind == "figure":
        prose_re = re.compile(
            r"\b(?:Supplementary\s+Figure|Suppl\.?\s*Figure|SFig\.?|Figure\s*S|Fig\.?\s*S)\s*\d+",
            re.IGNORECASE,
        )
    else:
        prose_re = re.compile(
            r"\b(?:Supplementary\s+Table|Suppl\.?\s*Table|STable\.?|Table\s*S|Tab\.?\s*S)\s*\d+",
            re.IGNORECASE,
        )
    # index (S-number) mapping for the human-facing prose report.
    idx_map = {o - SUPPLEMENTARY_NUMBER_OFFSET: n - SUPPLEMENTARY_NUMBER_OFFSET
               for o, n in mapping.items()}
    trailing_num = re.compile(r"(\d+)\s*$")

    tokens_updated = 0
    embeds_updated = 0
    sections_changed: list[str] = []
    prose_mentions: list[dict] = []

    for did, d in state.backend.list_collection(
        state.project_path("papers", slug, "sections")
    ):
        body = d.get("body") or ""
        if not body:
            continue
        key = d.get("key", did)

        def tok_repl(m: re.Match) -> str:
            nonlocal tokens_updated
            new = mapping.get(int(m.group(1)))
            if new is None:
                return m.group(0)
            tokens_updated += 1
            return "{" + token + ":" + str(new) + "}"

        new_body = tok_re.sub(tok_repl, body)

        if kind == "figure":
            def embed_repl(m: re.Match) -> str:
                nonlocal embeds_updated
                new = mapping.get(int(m.group(2)))
                if new is None:
                    return m.group(0)
                embeds_updated += 1
                return f"{m.group(1)}{new}{m.group(3)}"

            new_body = embed_re.sub(embed_repl, new_body)

        # Detect (don't rewrite) prose supplementary mentions for manual fix.
        for m in prose_re.finditer(new_body):
            mn = trailing_num.search(m.group(0))
            old_idx = int(mn.group(1)) if mn else None
            new_idx = idx_map.get(old_idx) if old_idx is not None else None
            if new_idx is not None and new_idx != old_idx:
                prose_mentions.append({
                    "section": key, "text": m.group(0).strip(),
                    "suggest": f"S{old_idx} → S{new_idx}",
                })

        if new_body != body:
            _sections.update_section(state, slug, key, body=new_body)
            sections_changed.append(key)

    return {
        "tokens_updated": tokens_updated,
        "embeds_updated": embeds_updated,
        "sections_changed": sections_changed,
        "prose_mentions": prose_mentions,
    }

"""lint_results_grid — every accuracy-like number in the body must be one cell
of the paper's designated results grid.

Written for a paper that reported one quantity under four choices in eight
tables: every numerical error there was the same shape — a number from one
crossing quoted while describing another — and nothing could catch it,
because no table said which crossing a number belonged to and no check tied a
sentence to a cell (feedback 7b3d3cd452c1). With one grid per quantity, the
check is mechanical: parse the cells, find the numbers in the prose, look each
up. A miss is a typed, stale or breakdown number; a double hit is a sentence
that names a number without naming its crossing.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .sections import list_sections as _list_sections
from .tables import get_table as _get_table

# What counts as a result number by default: a decimal followed by a percent
# sign — the "NN.NN%" shape of the failure this exists for. A bare decimal
# would sweep in p-values, coefficients and versions; a bare integer, years
# and counts. Widen with `pattern` when the grid's quantity is not a percent.
DEFAULT_PATTERN = r"\d+(?:\.\d+)?\s?%"

_CELL_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
_SEP_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])|\n+")
_HELD_MARK = re.compile(r"[†‡*]")


def _norm(num: str) -> str | None:
    """'58.130' and '58.13' are the same number; '6,255' is 6255."""
    try:
        d = Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None
    s = format(d.normalize(), "f")
    return s


def grid_cells(content: str) -> list[dict]:
    """Every numeric cell of a markdown pipe table: {row, col, raw, value, held}.
    Row 0 is the header row; the separator row is skipped and not counted."""
    out: list[dict] = []
    row_i = 0
    for line in (content or "").splitlines():
        if "|" not in line:
            continue
        if _SEP_ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        for col_i, cell in enumerate(cells):
            for m in _CELL_NUMBER.finditer(cell):
                v = _norm(m.group(0))
                if v is None:
                    continue
                out.append({
                    "row": row_i, "col": col_i, "raw": cell, "value": v,
                    "held": bool(_HELD_MARK.search(cell)),
                })
        row_i += 1
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text or "") if s and s.strip()]


def lint_results_grid(
    state, slug: str, table_number: int, *, pattern: str | None = None,
    sections: list[str] | None = None,
) -> dict:
    """Check the body's result numbers against the cells of table `table_number`.

    Returns {not_in_grid, ambiguous, checked, cells, held_cells, summary,
    clean}. `not_in_grid` is the gate; `ambiguous` is advisory — the number is
    in the grid, but in more than one cell, so the sentence must name the
    crossing. `pattern` (regex) replaces DEFAULT_PATTERN; `sections` limits
    the scan to those section keys (default: every section except methods)."""
    table = _get_table(state, slug, table_number)
    cells = grid_cells(table.get("content") or "")
    by_value: dict[str, list[dict]] = {}
    for c in cells:
        by_value.setdefault(c["value"], []).append(c)
    rx = re.compile(pattern or DEFAULT_PATTERN)

    not_in_grid: list[dict] = []
    ambiguous: list[dict] = []
    checked = 0
    for sec in _list_sections(state, slug):
        key = sec.get("key") or ""
        if sections is not None and key not in sections:
            continue
        if sections is None and key == "methods":
            continue
        for sent in _sentences(sec.get("body") or ""):
            for m in rx.finditer(sent):
                num = _CELL_NUMBER.search(m.group(0))
                if not num:
                    continue
                v = _norm(num.group(0))
                if v is None:
                    continue
                checked += 1
                hits = by_value.get(v, [])
                item = {"section": key, "value": m.group(0).strip(), "sentence": sent[:300]}
                if not hits:
                    not_in_grid.append(item)
                elif len(hits) > 1:
                    ambiguous.append({**item, "cells": [
                        {"row": h["row"], "col": h["col"], "raw": h["raw"]} for h in hits]})
    held = [c for c in cells if c["held"]]
    return {
        "slug": slug,
        "table_number": table_number,
        "table_title": table.get("title"),
        "cells": len(cells),
        "held_cells": len(held),
        "checked": checked,
        "not_in_grid": not_in_grid,
        "ambiguous": ambiguous,
        "summary": {
            "total": len(not_in_grid),
            "by_kind": {"not_in_grid": len(not_in_grid), "ambiguous": len(ambiguous)},
        },
        "clean": not not_in_grid,
        "next": (
            None if not not_in_grid else
            "each not_in_grid number is typed, stale, or from a breakdown that "
            "should cite its grid row — regenerate the grid from the script or "
            "fix the sentence; see /result-tables"),
    }

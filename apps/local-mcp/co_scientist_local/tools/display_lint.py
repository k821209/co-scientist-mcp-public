"""Detect inline display objects (markdown tables/images) and dangling prose
references — the guardrail for authors who write pipe tables straight into a
section body instead of registering them with add_table / add_figure.

Two failure modes this catches (feedback 4cd03d45c221):
  1. An inline GFM pipe table renders in the manuscript but is NOT a registered
     Table object — it never shows in the Tables panel and can be silently lost
     on a later update_section rewrite.
  2. Prose says "Table 2" / "Figure 3" but no such registered object exists
     (dropped, never registered, or mis-numbered) — the prose analogue of the
     {tab:N}/{fig:N} token resolver.
"""
from __future__ import annotations

import re

SUPPLEMENTARY_NUMBER_OFFSET = 100

# A GFM table separator row: only | : - and spaces, with at least one pipe and
# one dash, sitting directly under a non-empty (header) line. One per table.
_SEP_CHARS = set("|:- ")
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_PROSE_TABLE_RE = re.compile(r"\bTable\s+(S?)(\d+)\b", re.IGNORECASE)
_PROSE_FIG_RE = re.compile(r"\b(?:Figure|Fig)\.?\s+(S?)(\d+)\b", re.IGNORECASE)


def count_inline_tables(text: str) -> int:
    """Count GFM pipe-table blocks (one separator row = one table)."""
    lines = text.splitlines()
    n = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if "|" in s and "-" in s and set(s) <= _SEP_CHARS and i > 0 and lines[i - 1].strip():
            n += 1
    return n


def count_inline_images(text: str) -> int:
    """Count inline markdown images (![alt](src))."""
    return len(_IMG_RE.findall(text))


def label_for(number: int) -> str:
    """Registered object number → prose label: 3 -> '3', 101 -> 'S1'."""
    return (f"S{number - SUPPLEMENTARY_NUMBER_OFFSET}"
            if number > SUPPLEMENTARY_NUMBER_OFFSET else str(number))


def _prose_labels(text: str, regex: re.Pattern) -> set[str]:
    return {("S" if s else "") + n for s, n in regex.findall(text)}


def orphan_references(text: str, table_numbers, figure_numbers) -> dict[str, list[str]]:
    """Prose 'Table N' / 'Figure N' references with no matching registered
    object. Returns {'tables': [...], 'figures': [...]} of orphaned labels."""
    reg_tables = {label_for(n) for n in table_numbers}
    reg_figs = {label_for(n) for n in figure_numbers}
    return {
        "tables": sorted(_prose_labels(text, _PROSE_TABLE_RE) - reg_tables,
                         key=lambda x: (x.startswith("S"), x)),
        "figures": sorted(_prose_labels(text, _PROSE_FIG_RE) - reg_figs,
                          key=lambda x: (x.startswith("S"), x)),
    }


def inline_object_warnings(body: str) -> list[str]:
    """Warnings for inline markdown tables/images in a section body."""
    out: list[str] = []
    nt = count_inline_tables(body)
    ni = count_inline_images(body)
    if nt:
        out.append(
            f"{nt} inline markdown table(s) detected — these are NOT registered "
            f"Table objects: they won't appear in the Tables panel (list_tables) "
            f"and can be dropped on a later rewrite. Register them with add_table."
        )
    if ni:
        out.append(
            f"{ni} inline markdown image(s) detected — use add_figure so they're "
            f"tracked objects (won't show in the Figures panel / can be lost otherwise)."
        )
    return out

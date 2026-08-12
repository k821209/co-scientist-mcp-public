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
# `![](figure:3)` / `![](table:8)` are the REGISTERED-object embed schemes, not
# untracked inline images: they are how an author positions a tracked figure or
# table in the body. Counting them fired "use add_figure so they're tracked"
# precisely at the authors who had done exactly that, and hid a genuinely
# untracked `![](photo.png)` in the same inflated count.
_TRACKED_EMBED_RE = re.compile(r"!\[[^\]]*\]\((?:figure|table):\d+\)")
# The number ends with a non-digit lookahead, NOT `\b`: Korean is word-class to
# `re`, so `\b` after the digits failed on "Table 107에 있다" — every prose
# reference written in Korean text went unchecked, which reads as "no dangling
# references" rather than "not looked at".
_PROSE_TABLE_RE = re.compile(r"\bTable\s+(S?)(\d+)(?!\d)", re.IGNORECASE)
_PROSE_FIG_RE = re.compile(r"\b(?:Figure|Fig)\.?\s+(S?)(\d+)(?!\d)", re.IGNORECASE)
# The S-PREFIX spelling — "STable 5" / "SFigure 1" — which is the convention our
# own skills and rendered captions use, while the patterns above only recognised
# the S-suffix "Table S5". So a reference to a supplementary item that does not
# exist was never reported in the one spelling we tell authors to write.
# Case-SENSITIVE on purpose: an ignore-case `S?Table` also matches the ordinary
# word "stable" ("a stable 3 kb region" → STable 3).
_PROSE_STABLE_RE = re.compile(r"\bSTable\s+(\d+)(?!\d)")
_PROSE_SFIG_RE = re.compile(r"\bS(?:Figure|Fig)\.?\s+(\d+)(?!\d)")


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
    """Count UNTRACKED inline markdown images (![alt](src)).

    Embeds of a registered figure/table (`figure:N` / `table:N`) don't count —
    see `_TRACKED_EMBED_RE`.
    """
    return len(_IMG_RE.findall(_TRACKED_EMBED_RE.sub("", text)))


def label_for(number: int, *, number_supplementary: bool = True) -> str:
    """Registered object number → prose label: 3 -> '3', 101 -> 'S1'.

    `number_supplementary=False` turns the +100 convention off — in a report or
    proposal, table 107 is labelled "107". With it left on, a report's prose
    "Table 107" was compared against a registered label of "S7" and reported as
    a reference to a table that does not exist.
    """
    return (f"S{number - SUPPLEMENTARY_NUMBER_OFFSET}"
            if number_supplementary and number > SUPPLEMENTARY_NUMBER_OFFSET
            else str(number))


def _prose_labels(text: str, regex: re.Pattern, s_regex: re.Pattern) -> set[str]:
    """Referenced labels, normalized to the S-prefix form ("S5" / "3").

    `regex` reads the S-suffix spelling ("Table S5"), `s_regex` the S-prefix one
    ("STable 5"); both are in use and both must resolve to the same label.
    """
    return ({("S" if s else "") + n for s, n in regex.findall(text)}
            | {"S" + n for n in s_regex.findall(text)})


def orphan_references(text: str, table_numbers, figure_numbers,
                      *, number_supplementary: bool = True) -> dict[str, list[str]]:
    """Prose 'Table N' / 'Figure N' references with no matching registered
    object. Returns {'tables': [...], 'figures': [...]} of orphaned labels."""
    reg_tables = {label_for(n, number_supplementary=number_supplementary)
                  for n in table_numbers}
    reg_figs = {label_for(n, number_supplementary=number_supplementary)
                for n in figure_numbers}
    return {
        "tables": sorted(
            _prose_labels(text, _PROSE_TABLE_RE, _PROSE_STABLE_RE) - reg_tables,
            key=lambda x: (x.startswith("S"), x)),
        "figures": sorted(
            _prose_labels(text, _PROSE_FIG_RE, _PROSE_SFIG_RE) - reg_figs,
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

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

# Korean: "표 4", "표4", "<표 4>", "그림 2". Until 2026-11-15 these were not read
# at all, so in a Korean document this check passed without having looked — 31
# of the account's 187 documents name their tables this way.
#   - `(?<![가-힣])`: not the tail of 발표 / 목표 / 대표 / 좌표.
#   - not a compound number: "표 3-1" and "표 4.2" number a chapter's tables and
#     are not table 3. Measured before shipping: without this, five chapter
#     documents were each told their own chapter number was a missing table.
_KO_NUMBER = r"(\d+)(?!\d|[-–.]\d)"
_KO_TABLE_RE = re.compile(rf"(?<![가-힣])표\s?{_KO_NUMBER}")
_KO_FIG_RE = re.compile(rf"(?<![가-힣])그림\s?{_KO_NUMBER}")
# "보충 표 5" — what a Korean export labels a supplementary item (label_words).
_KO_SUPP_TABLE_RE = re.compile(rf"보충\s?표\s?{_KO_NUMBER}")
_KO_SUPP_FIG_RE = re.compile(rf"보충\s?그림\s?{_KO_NUMBER}")

# The spelled-out supplementary forms — "Supplementary Table 3",
# "Supplementary Fig. 2" — which is what Nature's house style requires. The
# patterns above are not anchored, so `\bTable\s+\d` matched the TAIL of these
# and reported a reference to main Table 3 that nobody wrote: one false warning
# per supplementary number, and they appeared the moment a paper was formatted
# correctly (feedback 26b56b0fd63b). A paper with eleven supplementary tables
# and no main-text tables got eleven, and the remedy they suggested — "register
# with add_table" — would have created eleven empty tables to silence it.
#
# A number RUN, not one number: "Supplementary Tables 7 and 8" and
# "Supplementary Figs. 3–5" are ordinary in the same house style, and reading
# only the first number left the rest unchecked.
_SUPP = r"Supp(?:lementary|l?\.)"
_NUM_RUN = r"(\d+(?:\s*(?:,|&|and|to|–|—|-)\s*\d+)*)(?!\d)"
_SUPP_TABLE_RE = re.compile(rf"\b{_SUPP}\s+Tables?\s+{_NUM_RUN}", re.IGNORECASE)
_SUPP_FIG_RE = re.compile(rf"\b{_SUPP}\s+(?:Figures?|Figs?\.?)\s+{_NUM_RUN}",
                          re.IGNORECASE)
# A range wider than this is a typo or a page range, not a list of display
# items; keep the endpoints rather than inventing thirty labels.
_MAX_RANGE = 30


def _numbers_in_run(run: str) -> list[str]:
    """The numbers a prose run names: "7 and 8" -> [7, 8], "3–5" -> [3, 4, 5]."""
    parts = re.split(r"\s*(,|&|and|to|–|—|-)\s*", run, flags=re.IGNORECASE)
    nums: list[int] = []
    i = 0
    while i < len(parts):
        if not parts[i].isdigit():
            i += 1
            continue
        n = int(parts[i])
        sep = parts[i + 1].lower() if i + 1 < len(parts) else ""
        nxt = parts[i + 2] if i + 2 < len(parts) else ""
        if sep in ("to", "–", "—", "-") and nxt.isdigit():
            m = int(nxt)
            nums.extend(range(n, m + 1) if 0 < m - n <= _MAX_RANGE else [n, m])
            i += 3
            continue
        nums.append(n)
        i += 1
    return [str(n) for n in dict.fromkeys(nums)]


def _split_supplementary(text: str) -> tuple[str, set[str], set[str]]:
    """(text with the supplementary references blanked, table labels, figure labels).

    Blanked rather than deleted, so nothing on either side of a removed span
    runs together into a new false match.
    """
    tables: set[str] = set()
    figures: set[str] = set()

    def take(match: re.Match, into: set[str]) -> str:
        into.update("S" + n for n in _numbers_in_run(match.group(1)))
        return " " * len(match.group(0))

    text = _SUPP_TABLE_RE.sub(lambda m: take(m, tables), text)
    text = _SUPP_FIG_RE.sub(lambda m: take(m, figures), text)
    text = _KO_SUPP_TABLE_RE.sub(lambda m: take(m, tables), text)
    text = _KO_SUPP_FIG_RE.sub(lambda m: take(m, figures), text)
    return text, tables, figures


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

    An embed of something the project already tracks does not count. The
    exemption was `figure:N` / `table:N` only, and `![](references)` — the
    bibliography embed that `prepare_export` RECOMMENDS in the same response —
    counted as an untracked image, so every document using it was told to
    "use add_figure" on its reference list, every export (feedback
    fbc093254a3e). The same repair had already been made once for figures and
    tables; `references` was missed because it has no `:N` and so never showed
    up when the covered set was eyeballed.

    The references pattern is imported rather than rewritten: a second
    definition of the same embed is the next bug, not the fix. What keeps this
    honest is a test that scans the package for every embed scheme it mentions
    anywhere and fails when a new one is not exempt here.
    """
    from .numbered_citations import _REFERENCES_EMBED_RE

    stripped = _TRACKED_EMBED_RE.sub("", text)
    stripped = _REFERENCES_EMBED_RE.sub("", stripped)
    return len(_IMG_RE.findall(stripped))


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
    # Read the spelled-out supplementary references first and take them out of
    # the way, so the unanchored main-text patterns cannot see their tails.
    text, supp_tables, supp_figs = _split_supplementary(text)
    if not number_supplementary:
        # With the +100 convention off there is no S-label to resolve against —
        # a report's "Table 107" IS table 107. Those references are removed
        # from the scan rather than checked against a label that cannot exist.
        supp_tables, supp_figs = set(), set()
    return {
        "tables": sorted(
            (_prose_labels(text, _PROSE_TABLE_RE, _PROSE_STABLE_RE) | supp_tables
             | set(_KO_TABLE_RE.findall(text)))
            - reg_tables,
            key=_label_sort),
        "figures": sorted(
            (_prose_labels(text, _PROSE_FIG_RE, _PROSE_SFIG_RE) | supp_figs
             | set(_KO_FIG_RE.findall(text)))
            - reg_figs,
            key=_label_sort),
    }


def _label_sort(label: str) -> tuple:
    """Main items before supplementary, and numerically inside each — "S10"
    sorted as a string landed between "S1" and "S2"."""
    supp = label.startswith("S")
    digits = label[1:] if supp else label
    return (supp, int(digits) if digits.isdigit() else 0, label)


def inline_object_warnings(body: str) -> list[str]:
    """Warnings for inline markdown tables/images in a section body."""
    out: list[str] = []
    nt = count_inline_tables(body)
    ni = count_inline_images(body)
    if nt:
        out.append(
            f"{nt} inline markdown table(s) detected — these are NOT registered "
            f"Table objects: they won't appear in the Tables panel (list_tables), "
            f"and the next agent to rewrite this section's body will not know they "
            f"were meant to survive. Nothing server-side deletes them. Register "
            f"them with add_table."
        )
    if ni:
        out.append(
            f"{ni} inline markdown image(s) detected — use add_figure so they're "
            f"tracked objects (won't show in the Figures panel / can be lost otherwise)."
        )
    return out


# ── where the items stand, against what they are numbered ────────────────────
#
# Feedback 727b3acec9da: seven registered tables and ten typed straight into
# the body, numbered in no order, and nothing said so until the author asked
# for the numbers to be put right. Each of these is decidable from the text.

_EMBED_RE = re.compile(r"!\[[^\]]*\]\((figure|table):(\d+)\)")
_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def placement(manuscript: str, table_numbers, figure_numbers,
              *, number_supplementary: bool = True) -> dict:
    """What the body's `![](table:N)` / `![](figure:N)` embeds say about the
    registered items. Per kind:

      unregistered: [N]     an embed naming an item that is not registered
      repeated:     {N: k}  an item embedded k > 1 times — it is drawn k times
      unplaced:     [N]     registered and not embedded, while others ARE: it
                            falls to the end of the document, out of sequence
      out_of_order: None, or {appear: [...], order: [...]} when the embedded
                    items are not numbered in the order they appear; `order`
                    is the argument that puts them right

    Only EMBEDDED items are held to an order: an embed is where the reader
    sees the table. Ordering by first MENTION instead was measured before
    choosing — out of order in 12 of the 35 documents on the account that
    mention two or more of their tables, most of them a forward reference in
    Methods — against 6 of 96 for the embedded rule, each a real disorder
    ("appear as 1, 8, 9, 10, 11, 12, 2, 3, …").
    In a journal paper main and supplementary items are two sequences.
    """
    text = _CODE_RE.sub(lambda m: " " * len(m.group(0)), manuscript or "")
    seen: dict[str, list[int]] = {"table": [], "figure": []}
    for match in _EMBED_RE.finditer(text):
        seen[match.group(1)].append(int(match.group(2)))
    out = {}
    for kind, registered in (("table", table_numbers), ("figure", figure_numbers)):
        registered = sorted({n for n in registered if isinstance(n, int)})
        embedded = seen[kind]
        first: list[int] = list(dict.fromkeys(embedded))
        known = [n for n in first if n in registered]
        sequences = ([[n for n in known if n <= SUPPLEMENTARY_NUMBER_OFFSET],
                      [n for n in known if n > SUPPLEMENTARY_NUMBER_OFFSET]]
                     if number_supplementary else [known])
        out_of_order = None
        for index, sequence in enumerate(sequences):
            if sequence == sorted(sequence):
                continue
            pool = [n for n in registered
                    if not number_supplementary
                    or (n > SUPPLEMENTARY_NUMBER_OFFSET) == bool(index)]
            out_of_order = {
                "appear": sequence,
                "scope": "supplementary" if number_supplementary and index else "main",
                # Embedded ones in the order they appear; the rest keep their
                # relative order after them.
                "order": sequence + [n for n in pool if n not in sequence],
            }
            break
        out[kind] = {
            "unregistered": sorted(set(first) - set(registered)),
            "repeated": {n: embedded.count(n) for n in first if embedded.count(n) > 1},
            "unplaced": [n for n in registered if n not in first] if known else [],
            "out_of_order": out_of_order,
            "embedded": len(known),
            "registered": len(registered),
        }
    return out


def placement_warnings(found: dict) -> list[str]:
    """`placement` as the lines `prepare_export` prints."""
    lines: list[str] = []
    for kind in ("table", "figure"):
        f = found[kind]
        if f["unregistered"]:
            lines.append(
                f"the body embeds {kind} " + ", ".join(str(n) for n in f["unregistered"])
                + f" (`![]({kind}:N)`) but no such {kind} is registered — the embed "
                "renders as nothing")
        if f["repeated"]:
            lines.append(
                "; ".join(f"{kind} {n} is embedded {k} times" for n, k in f["repeated"].items())
                + " — it is drawn each time")
        if f["unplaced"]:
            lines.append(
                f"{len(f['unplaced'])} registered {kind}(s) are not placed in the body ("
                + ", ".join(str(n) for n in f["unplaced"][:12])
                + ("…" if len(f["unplaced"]) > 12 else "")
                + f") while {f['embedded']} are — they are appended at the end, after the "
                f"others. Place each with `![]({kind}:N)` on its own line")
        if f["out_of_order"]:
            o = f["out_of_order"]
            tool = ("reorder_supplementary(slug, kind, order)" if o["scope"] == "supplementary"
                    else f"reorder_tables_figures(slug, '{kind}', order={o['order']})")
            lines.append(
                f"{kind} numbers do not follow the order the {kind}s appear in the body "
                f"(they appear as {', '.join(str(n) for n in o['appear'][:20])}"
                + ("…" if len(o["appear"]) > 20 else "")
                + f") — {tool} renumbers them and carries every reference")
    return lines

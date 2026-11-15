"""Reorder figures / tables — renumber, move the blobs, carry every reference.

An item is keyed by its number: the Firestore doc id IS the number, and a
figure's blob path embeds it (`figure_{n}.png`). So one number does three jobs
— the storage key, the order in the document, and what the prose points at —
and putting a table in at position 3 moves every table after it.

Until 2026-11-15 that could only be done for supplementary items. For the
tables of the body it was `delete_table` + `add_table` per table, each delete
discarding the caption, the provenance link and the run keys; then every
`![](table:N)` and "표 N" by hand, through a state in which two embeds carried
the same number (feedback 727b3acec9da: one table inserted into a report of
17 — 30 destructive calls and some thirty edits).

`reorder_items` does it in one call, for main items and supplementary ones:

  - the docs move (two phases through temporary numbers, so a number is never
    occupied twice; a failure part-way puts back what had moved);
  - figure images and panels are copied to the new number's path, here, so no
    re-upload is needed;
  - `{fig:N}` / `{tab:N}` tokens and `![](figure:N)` / `![](table:N)` embeds
    are rewritten in ONE pass over each text, which is what makes 3→4 and
    4→5 safe together;
  - in section bodies and in every caption, legend, title and table cell;
  - a comment attached to the item (`manuscript_ref = "table:3"`) follows it,
    and a comment's `anchor_text` is rewritten with the text it sits on;
  - a deck slide that shows the figure by number is pointed at the new one.

Prose — "Table 3", "표 3", "Fig. 2A" — is rewritten too for MAIN items, in the
same single pass, and every change is returned (`prose_rewritten`) so it can be
read. What is not a plain single reference is left and listed (`prose_left`):
"Tables 3 and 4", "표 3–5". For SUPPLEMENTARY items prose is only reported, as
before: its spellings ("Fig. S2", "SFig 3", "Supplementary Figure 1") are too
many to rewrite without mangling one.
"""
from __future__ import annotations

import pathlib
import re

from ..backends.base import NotFound
from ..state import State
from .figures import (SUPPLEMENTARY_NUMBER_OFFSET, _figure_blob_path, _figure_path,
                      is_supplementary_number)
from . import sections as _sections
from .tables import _table_path

MAX_REPORTED = 80

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
    return reorder_items(state, slug, kind, order=order, scope="supplementary")


def reorder_items(
    state: State, slug: str, kind: str, *,
    order: list[int] | None = None,
    move_from: int | None = None, move_to: int | None = None,
    scope: str = "main", rewrite_prose: bool = True,
) -> dict:
    """Renumber the figures or tables of `slug`. See the module docstring.

    `order`: the CURRENT numbers of the scope, in the sequence wanted; they
    become 1, 2, … (101, 102, … for the supplementary scope) — gaps close.
    `move_from` / `move_to`: one item to the number it should have; the ones
    between shift by one. Give `order`, or the pair, not both.
    """
    if kind not in ("figure", "table"):
        raise ValueError("kind must be 'figure' or 'table'")
    if scope not in ("main", "supplementary"):
        raise ValueError("scope must be 'main' or 'supplementary'")
    paper = state.backend.get_doc(_sections._paper_path(state, slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    from .exports import numbers_supplementary
    split = numbers_supplementary(paper)
    if scope == "supplementary" and not split:
        raise ValueError(
            "this document has no supplementary numbering (it is not a journal paper): "
            "its item 101 is the hundred-and-first — use scope='main'")

    coll = "figures" if kind == "figure" else "tables"
    num_field = "figure_number" if kind == "figure" else "table_number"
    items = state.backend.list_collection(state.project_path("papers", slug, coll))
    numbers = [n for did, d in items
               if (n := (d.get(num_field) if isinstance(d.get(num_field), int)
                         else _safe_int(did))) is not None]
    supp = scope == "supplementary"
    current = sorted(n for n in numbers if (split and is_supplementary_number(n)) == supp)
    label = ("supplementary " if supp else "") + kind
    if not current:
        raise ValueError(f"no {label}s to reorder for {slug!r}")

    if (move_from is None) != (move_to is None):
        raise ValueError("move_from and move_to go together")
    if order is not None and move_from is not None:
        raise ValueError("give `order` or `move_from`/`move_to`, not both")
    first = SUPPLEMENTARY_NUMBER_OFFSET + 1 if supp else 1
    if move_from is not None:
        if move_from not in current:
            raise ValueError(f"there is no {label} {move_from}; the current ones are {current}")
        if not first <= move_to < first + len(current):
            raise ValueError(
                f"move_to must be a number the {label}s will have, "
                f"{first}–{first + len(current) - 1}, got {move_to}")
        order = [n for n in current if n != move_from]
        order.insert(move_to - first, move_from)
    if order is None:
        raise ValueError("give `order`, or `move_from` and `move_to`")
    if sorted(order) != current:
        missing = sorted(set(current) - set(order))
        extra = sorted(set(order) - set(current))
        twice = sorted({n for n in order if order.count(n) > 1})
        raise ValueError(
            f"order must be a permutation of the current {label} numbers {current}, "
            f"got {sorted(order)}"
            + (f" — missing {missing}" if missing else "")
            + (f" — not a current number: {extra}" if extra else "")
            + (f" — given twice: {twice}" if twice else ""))

    mapping = {old: first + i for i, old in enumerate(order)}
    moves = {o: n for o, n in mapping.items() if o != n}
    empty = {"tokens_updated": 0, "embeds_updated": 0, "sections_changed": [],
             "prose_mentions": [], "prose_rewritten": [], "prose_rewritten_total": 0,
             "prose_left": [], "items_changed": [], "comments_moved": 0,
             "anchors_updated": 0, "slides_updated": 0}
    if not moves:
        return {"reordered": False, "kind": kind, "scope": scope, "mapping": mapping, **empty}

    # Everything that will be written is worked out BEFORE anything moves, from
    # the documents as they stand: a rewrite that cannot be computed must stop
    # the call while the numbers are still the old ones.
    plan = _plan_references(state, slug, kind, mapping, supp=supp,
                            rewrite_prose=rewrite_prose)

    # Two-phase number move: old → temp → final (never collide with a live id).
    # A failure part-way puts back what had moved — an item left at 900003 is
    # a table nobody can find.
    done: list[tuple[int, int]] = []
    try:
        temp = {}
        for idx, old in enumerate(moves):
            temp[old] = _TEMP_OFFSET + idx
            _move_item(state, slug, kind, old, temp[old], num_field)
            done.append((old, temp[old]))
        for old, t in temp.items():
            _move_item(state, slug, kind, t, moves[old], num_field)
            done.append((t, moves[old]))
    except Exception:
        for src, dst in reversed(done):
            try:
                _move_item(state, slug, kind, dst, src, num_field)
            except Exception:  # noqa: BLE001 — the original error is the one to raise
                pass
        raise

    report = _write_references(state, slug, kind, mapping, plan)
    return {"reordered": True, "kind": kind, "scope": scope, "mapping": mapping, **report}


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

        # Panel blobs move too. Their names embed the figure number, so without
        # this a reordered figure keeps panels named after the number it used to
        # hold — the blobs still resolve, so nothing looks wrong, while the names
        # now describe a different figure and the originals are orphaned. The
        # panel ids are unique, so this is a rename for legibility rather than a
        # correctness fix, and it keeps `panels[].blob_path` honest.
        panels = doc.get("panels") or []
        if panels:
            moved = []
            for panel in panels:
                src = panel.get("blob_path")
                if not src:
                    moved.append(panel)
                    continue
                ext = pathlib.Path(src).suffix.lstrip(".") or "png"
                dst = state.project_path(
                    "papers", slug, "figures",
                    f"figure_{new}_{panel.get('id', 'p')}.{ext}")
                data = state.backend.get_blob(src)
                if data is None or dst == src:
                    moved.append(panel)
                    continue
                state.backend.put_blob(dst, data)
                state.backend.delete_blob(src)
                moved.append({**panel, "blob_path": dst})
            doc["panels"] = moved

    state.backend.set_doc(new_path, doc)
    state.backend.delete_doc(old_path)


# ── references ───────────────────────────────────────────────────────────────

_PROTECTED = re.compile(r"```.*?```|`[^`\n]*`|https?://\S+", re.S)
_EN_SUPP = re.compile(r"\bSupp(?:lementary|l?\.)\s+(?:Tables?|Figures?|Figs?\.?)\s+[\d,&–—\- and]*\d",
                      re.IGNORECASE)
_KO_SUPP = re.compile(r"보충\s?(?:표|그림)\s?\d+")
# A plain single reference, and what follows it when it is not one.
#   - a range or a list ("표 3–5", "표 3~5", "Table 3 and 4") names more than
#     the number in hand: left, and listed;
#   - a compound number ("표 3-1", "Table 4.2") numbers a chapter's tables and
#     is not table 3 at all: not a reference, and not listed either.
# A hyphen is read as the second, a dash or a tilde as the first — which is how
# the two are written in the documents this was measured on.
_RANGE_TAIL = r"(?=\s*(?:[–—~]|and\b|및|와|과|,)\s*\d)"
_COMPOUND_TAIL = r"(?![\d]|[-.]\d)"


def _prose_patterns(kind: str) -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    """(a single reference, a plural / list form, a single one followed by a range)."""
    if kind == "table":
        en, ko, plural = r"Table", "표", r"Tables"
    else:
        en, ko, plural = r"Fig(?:ure|\.)?", "그림", r"Fig(?:ure)?s\.?"
    single = re.compile(
        rf"(?P<lead>\b{en}\s*|(?<![가-힣]){ko}\s?)(?P<num>\d+){_COMPOUND_TAIL}", re.IGNORECASE)
    listed = re.compile(rf"\b{plural}\s*\d[\d\s,&–—\-and]*", re.IGNORECASE)
    ranged = re.compile(
        rf"(?:\b{en}\s*|(?<![가-힣]){ko}\s?)\d+{_RANGE_TAIL}[^\n.;)]{{0,12}}", re.IGNORECASE)
    return single, listed, ranged


class _Rewriter:
    """One text, rewritten in one pass per kind of reference.

    One pass is the point: 3→4 and 4→5 applied one after the other turn every
    3 into a 5. Each pattern is substituted once, with the whole mapping.
    """

    def __init__(self, kind: str, mapping: dict[int, int], *, supp: bool, prose: bool):
        self.kind, self.mapping, self.supp, self.prose = kind, mapping, supp, prose
        token = "fig" if kind == "figure" else "tab"
        self.token_re = re.compile(r"\{" + token + r":(\d+)\}")
        self.embed_re = re.compile(r"(!\[[^\]]*\]\(" + kind + r":)(\d+)(\))")
        self.single, self.listed, self.ranged = _prose_patterns(kind)
        self.tokens = self.embeds = 0
        self.rewritten: list[dict] = []
        self.left: list[dict] = []
        self.mentions: list[dict] = []

    def text(self, value: str, where: str) -> str:
        if not value:
            return value
        out, last = [], 0
        for match in _PROTECTED.finditer(value):          # code and links stay as they are
            out.append(self._open(value[last:match.start()], where))
            out.append(match.group(0))
            last = match.end()
        out.append(self._open(value[last:], where))
        return "".join(out)

    def _open(self, chunk: str, where: str) -> str:
        if not chunk:
            return chunk

        def token(m: re.Match) -> str:
            new = self.mapping.get(int(m.group(1)))
            if new is None or new == int(m.group(1)):
                return m.group(0)
            self.tokens += 1
            return m.group(0).replace(m.group(1), str(new))

        def embed(m: re.Match) -> str:
            new = self.mapping.get(int(m.group(2)))
            if new is None or new == int(m.group(2)):
                return m.group(0)
            self.embeds += 1
            return f"{m.group(1)}{new}{m.group(3)}"

        chunk = self.embed_re.sub(embed, self.token_re.sub(token, chunk))
        if self.supp:
            # Reported, never rewritten, whatever `rewrite_prose` says: the
            # spellings of a supplementary reference are too many to be sure of.
            self._report_supplementary(chunk, where)
            return chunk
        return self._prose(chunk, where)

    def _report_supplementary(self, chunk: str, where: str) -> None:
        noun = "Figure" if self.kind == "figure" else "Table"
        short = "Fig" if self.kind == "figure" else "Tab"
        prose_re = re.compile(
            rf"\b(?:Supplementary\s+{noun}|Suppl\.?\s*{noun}|S{noun}\.?|S{short}\.?|"
            rf"{noun}\s*S|{short}\.?\s*S)\s*\d+", re.IGNORECASE)
        off = SUPPLEMENTARY_NUMBER_OFFSET
        for m in prose_re.finditer(chunk):
            number = re.search(r"(\d+)\s*$", m.group(0))
            old = int(number.group(1)) if number else None
            new = self.mapping.get(old + off) if old is not None else None
            if new is not None and new - off != old:
                self.mentions.append({"section": where, "text": m.group(0).strip(),
                                      "suggest": f"S{old} → S{new - off}"})

    def _prose(self, chunk: str, where: str) -> str:
        # A supplementary reference carries its own number ("Supplementary
        # Table 3" is STable 3, not table 3): out of the way before the main
        # patterns look, and back afterwards untouched.
        held: list[str] = []

        def hold(m: re.Match) -> str:
            held.append(m.group(0))
            return f"\x00{len(held) - 1}\x00"

        def also_hold(pattern: re.Pattern, why: str, text: str) -> str:
            def keep(m: re.Match) -> str:
                numbers = [int(n) for n in re.findall(r"\d+", m.group(0))]
                if any(self.mapping.get(n, n) != n for n in numbers):
                    self.left.append({"where": where, "text": m.group(0).strip(), "why": why,
                                      "mapping": {n: self.mapping[n] for n in numbers
                                                  if self.mapping.get(n, n) != n}})
                return hold(m)
            return pattern.sub(keep, text)

        work = _KO_SUPP.sub(hold, _EN_SUPP.sub(hold, chunk))
        work = also_hold(self.listed, "a plural form names several items", work)
        work = also_hold(self.ranged, "a range or a list, not one item", work)

        def single(m: re.Match) -> str:
            old = int(m.group("num"))
            new = self.mapping.get(old)
            if new is None or new == old:
                return m.group(0)
            after = f"{m.group('lead')}{new}"
            if not self.prose:
                self.left.append({"where": where, "text": m.group(0), "why": "rewrite_prose=False",
                                  "mapping": {old: new}})
                return m.group(0)
            lo, hi = max(0, m.start() - 30), min(len(work), m.end() + 30)
            self.rewritten.append({
                "where": where, "before": m.group(0), "after": after,
                "context": re.sub(r"\x00\d+\x00", "…", work[lo:hi]).replace("\n", " ").strip()})
            return after

        work = self.single.sub(single, work)
        return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], work)


def _plan_references(state: State, slug: str, kind: str, mapping: dict[int, int],
                     *, supp: bool, rewrite_prose: bool) -> dict:
    """Every text that will change, and what it will become. Writes nothing."""
    rw = _Rewriter(kind, mapping, supp=supp, prose=rewrite_prose)
    sections: list[tuple[str, str]] = []
    bodies: dict[str, tuple[str, str]] = {}
    for did, d in state.backend.list_collection(
            state.project_path("papers", slug, "sections")):
        body = d.get("body") or ""
        key = d.get("key", did)
        new_body = rw.text(body, key)
        bodies[key] = (body, new_body)
        if new_body != body:
            sections.append((key, new_body))

    # Captions, legends, titles and table cells say "see Table 3" as well.
    items: list[tuple[str, int, dict, str]] = []
    for coll, field, noun, fields in (
            ("tables", "table_number", "Table", ("title", "caption", "legend", "content")),
            ("figures", "figure_number", "Figure", ("title", "caption", "legend"))):
        own = coll == ("figures" if kind == "figure" else "tables")
        for did, d in state.backend.list_collection(state.project_path("papers", slug, coll)):
            number = d.get(field) if isinstance(d.get(field), int) else _safe_int(did)
            if number is None:
                continue
            # Named by where it will BE once the numbers have moved: that is
            # the table the reader of the report can open.
            final = mapping.get(number, number) if own else number
            patch = {}
            for name in fields:
                value = d.get(name)
                if isinstance(value, str) and value:
                    new_value = rw.text(value, f"{noun} {final} ({name})")
                    if new_value != value:
                        patch[name] = new_value
            if patch:
                items.append((coll, final, patch, f"{noun} {final}"))

    # Comments: the one attached to the item follows it; an anchor is rewritten
    # with the passage it sits on, or the highlight would lose its text.
    reviews: list[tuple[str, dict]] = []
    ref_re = re.compile(rf"^{kind}:(\d+)$")
    # Its own rewriter: what an anchor quotes was already counted in the body.
    quiet = _Rewriter(kind, mapping, supp=supp, prose=rewrite_prose)
    comments_moved = anchors = 0
    for rid, r in state.backend.list_collection(state.project_path("papers", slug, "reviews")):
        patch = {}
        m = ref_re.match(str(r.get("manuscript_ref") or ""))
        if m and mapping.get(int(m.group(1)), int(m.group(1))) != int(m.group(1)):
            patch["manuscript_ref"] = f"{kind}:{mapping[int(m.group(1))]}"
            comments_moved += 1
        anchor = r.get("anchor_text")
        if isinstance(anchor, str) and anchor:
            new_anchor = quiet.text(anchor, "anchor")
            if new_anchor != anchor:
                patch["anchor_text"] = new_anchor
                anchors += 1
        if patch:
            reviews.append((rid, patch))

    # A slide that shows the paper's figure by its number.
    slides: list[tuple[str, dict]] = []
    if kind == "figure":
        for deck_id, _ in state.backend.list_collection(
                state.project_path("papers", slug, "decks")):
            base = state.project_path("papers", slug, "decks", deck_id, "slides")
            for slide_id, slide in state.backend.list_collection(base):
                patch = {}
                number = slide.get("figure_number")
                if isinstance(number, int) and mapping.get(number, number) != number:
                    patch["figure_number"] = mapping[number]
                regions = slide.get("regions") or []
                moved = [({**region, "figure_number": mapping[region["figure_number"]]}
                          if isinstance(region.get("figure_number"), int)
                          and mapping.get(region["figure_number"], region["figure_number"])
                          != region["figure_number"] else region) for region in regions]
                if moved != regions:
                    patch["regions"] = moved
                if patch:
                    slides.append((f"{base}/{slide_id}", patch))

    return {"sections": sections, "items": items, "reviews": reviews, "slides": slides,
            "tokens": rw.tokens, "embeds": rw.embeds, "rewritten": rw.rewritten,
            "left": rw.left, "mentions": rw.mentions,
            "comments_moved": comments_moved, "anchors": anchors}


def _write_references(state: State, slug: str, kind: str, mapping: dict[int, int],
                      plan: dict) -> dict:
    for key, body in plan["sections"]:
        _sections.update_section(state, slug, key, body=body)
    for coll, number, patch, _label in plan["items"]:
        path = (_figure_path if coll == "figures" else _table_path)(state, slug, number)
        state.backend.update_doc(path, patch)
    for rid, patch in plan["reviews"]:
        state.backend.update_doc(state.project_path("papers", slug, "reviews", rid), patch)
    for path, patch in plan["slides"]:
        state.backend.update_doc(path, patch)
    return {
        "tokens_updated": plan["tokens"],
        "embeds_updated": plan["embeds"],
        "sections_changed": [key for key, _ in plan["sections"]],
        "prose_mentions": plan["mentions"],
        "prose_rewritten": plan["rewritten"][:MAX_REPORTED],
        "prose_rewritten_total": len(plan["rewritten"]),
        "prose_left": plan["left"][:MAX_REPORTED],
        "items_changed": [label for *_rest, label in plan["items"]],
        "comments_moved": plan["comments_moved"],
        "anchors_updated": plan["anchors"],
        "slides_updated": len(plan["slides"]),
    }

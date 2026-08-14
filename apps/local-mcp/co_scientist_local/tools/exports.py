"""Manuscript export: prepare bundle, run pandoc, upload result to Storage.

`prepare_export` is pure data — collects everything pandoc will need:
- assembled manuscript text (from compile_manuscript)
- references converted to BibTeX
- figures with their blob paths
- warnings: placeholder markers (TBD/TK/XXX/TODO) and unresolved `{doi:…}`
  citations not present in any reference's `doi` field.

`export_to_path` runs the full pipeline:
1. prepare_export
2. Lay out a temp dir: manuscript.md, references.bib, figure files
3. Invoke pandoc to produce the output file
4. Upload the output to Cloud Storage at
   `users/{uid}/papers/{slug}/exports/{filename}` so the dashboard can serve it.
"""
from __future__ import annotations

import json
import io
import pathlib
import re
import shutil
import subprocess
import tempfile
import zipfile

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from . import csl as _csl
from . import display_lint as _display_lint
from . import docx_export as _docx_export
from . import figures as _figures
from .figures import SUPPLEMENTARY_NUMBER_OFFSET
from . import papers as _papers
from . import references as _references
from . import requirements as _requirements
from . import reviews as _reviews
from . import sections as _sections
from . import tables as _tables


_DOI_INLINE_RE = re.compile(r"\{doi:([^}]+)\}")
# Inline citation tokens: {doi:DOI} (resolved via the ref list) and
# {ref:key}/{cite:key} (a registered citation_key directly — for DOI-less works
# like software/books/reports that have no DOI to resolve). A raw pandoc
# [@key] the author wrote is also folded in.
_CITE_KEY_RE = re.compile(r"\{(?:ref|cite):([^}]+)\}")
_RAW_CITE_RE = re.compile(r"\[@([^\]]+)\]")
# One citation TOKEN, and a RUN of adjacent tokens (optionally whitespace-
# separated). The run collapses into ONE pandoc group `[@a; @b; @c]` — never
# `[@a][@b]` (pandoc reads adjacent brackets as a link) and never a `{doi}` group
# left abutting a following `[@key]` (the bug in feedback 57964d23cdef).
_CITE_TOKEN = r"(?:\{doi:[^}]+\}|\{(?:ref|cite):[^}]+\}|\[@[^\]]+\])"
_CITE_RUN_RE = re.compile(_CITE_TOKEN + r"(?:\s*" + _CITE_TOKEN + r")*")
_PLACEHOLDER_RE = re.compile(r"\b(TBD|TK|XXX|TODO|FIXME)\b", re.IGNORECASE)
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[(?:\.{3}|placeholder|tbd|tk|xxx|todo|fixme)\]", re.IGNORECASE)


def _scan_placeholders(text: str) -> list[dict]:
    """Find TODO-like markers per line. Returns [{line, snippet, marker}]."""
    out: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in _PLACEHOLDER_RE.finditer(line):
            out.append({"line": i, "marker": m.group(0).upper(),
                        "snippet": line.strip()[:200]})
        for m in _BRACKET_PLACEHOLDER_RE.finditer(line):
            out.append({"line": i, "marker": m.group(0),
                        "snippet": line.strip()[:200]})
    return out


def _extract_cited_dois(text: str) -> list[str]:
    return _DOI_INLINE_RE.findall(text)


_THEMATIC_BREAK_RE = re.compile(r"(?m)^[ \t]*-{3,}[ \t]*$")


def _escape_thematic_breaks(text: str) -> str:
    """Disambiguate '---' rules for pandoc (dev-todo P1-3). The YAML metadata
    fence is already turned off via `-f markdown-yaml_metadata_block`, but a
    '---' line directly under a paragraph is still read as a setext-H2
    underline (silently promoting that text to a heading). Rewriting standalone
    dash rules to '***' keeps the intended thematic break with no ambiguity.
    """
    return _THEMATIC_BREAK_RE.sub("***", text)


def _by_number(
    main: list[dict], supplementary: list[dict], number_key: str
) -> dict[int, tuple[dict, bool]]:
    """Index figures/tables by their number, tagged main (False) / supp (True)."""
    out: dict[int, tuple[dict, bool]] = {}
    for items, supp in ((main, False), (supplementary, True)):
        for item in items:
            num = item.get(number_key)
            if isinstance(num, int):
                out[num] = (item, supp)
    return out


_INLINE_FIGURE_RE = re.compile(r"!\[([^\]]*)\]\(figure:(\d+)\)")
_INLINE_TABLE_RE = re.compile(r"!\[([^\]]*)\]\(table:(\d+)\)")
# A table embed alone on its own line, starting at column 0 — the only place a
# multi-line pipe table can be substituted without breaking the structure around
# it. Deliberately NOT tolerant of leading whitespace: an indented embed may be
# list-item or blockquote content, and splicing a top-level table there would
# silently reflow the author's list.
_LONE_TABLE_EMBED_RE = re.compile(r"^!\[([^\]]*)\]\(table:(\d+)\)[ \t]*$")


def _rewrite_inline_figure_refs(
    text: str, figures: list[dict], supp_figures: list[dict],
    *, placeable: set[int] | None = None,
) -> tuple[str, set[int]]:
    """Rewrite body embeds `![alt](figure:N)` to point at the staged image file
    (`figure_N.png`) that export_to_path writes into pandoc's working dir.

    The web renderer resolves the `figure:N` scheme to the figure's download
    URL; pandoc can't, so without this rewrite it looks for a file literally
    named `figure:N` and emits a broken/missing image. An unresolved N (no
    blob) drops the image node and keeps the alt text as plain caption text.

    An embed with NO alt text gets the registered caption/legend as its alt, so
    a figure the author placed inline still carries its legend. Without this the
    inline copy would be a bare image and — now that placing inline suppresses
    the appendix copy — the legend would be dropped from the document entirely.

    `figures`/`supp_figures` are the FULL registered sets, so a supplementary
    figure keeps its "SFigure N" label; `placeable` restricts which numbers this
    file may actually embed (the scope-included ones). A registered figure that
    cannot be embedded here degrades to a bold label rather than to its empty
    alt text, which rendered as nothing at all.

    Returns (text, placed) where `placed` is the figure numbers the body itself
    positions; the caller excludes those from the Figures appendix so they are
    not rendered a second time at the end of the document.
    """
    entry_by_num = _by_number(figures, supp_figures, "figure_number")
    placed: set[int] = set()

    def repl(m: re.Match) -> str:
        alt, num = m.group(1), int(m.group(2))
        entry = entry_by_num.get(num)
        if entry is None:
            return alt  # never registered — keep whatever the author wrote
        fig, supp = entry
        bp = fig.get("blob_path")
        if not bp or (placeable is not None and num not in placeable):
            label = _display_label("Figure", num, supplementary=supp)
            return alt or f"**{label}**"
        placed.add(num)
        return f"![{alt or _figure_alt(fig, supplementary=supp)}]({pathlib.Path(bp).name})"

    return _INLINE_FIGURE_RE.sub(repl, text), placed


def _rewrite_inline_table_refs(
    text: str, tables: list[dict], supp_tables: list[dict],
    *, placeable: set[int] | None = None,
) -> tuple[str, set[int]]:
    """Expand a body embed `![alt](table:N)` into the table itself, in place.

    `table:N` is the table counterpart of the `figure:N` scheme the dashboard
    resolves live. On export it had NO handler at all: the embed stayed an image
    node pointing at a file named `table:8`, which resolves to nothing, and both
    engines fall back to the alt text — empty for the usual `![](table:8)`. So
    the line rendered as an empty paragraph and the table appeared only in the
    appendix at the end of the document, with **no trace left at the point the
    author placed it** — not even a cross-reference to reconstruct from
    (feedback 0e394fb76649: a 107-table proposal where every in-body table
    position was lost, and one table vanished from the document entirely).

    An embed alone on its own line becomes the caption + pipe table, so it
    renders where the author put it. An embed that shares a line with prose (or
    is indented, so it may be list/quote content) cannot become a block without
    reflowing what surrounds it, so it degrades to a bold `**Table N**` text
    reference — visible, never silent. So does an embed of a table this file may
    not carry (`placeable`) — a `scope="main"` export referencing a supplementary
    table correctly points at "STable 1" without pasting it into the manuscript.

    Returns (text, placed); the caller excludes `placed` from the Tables
    appendix so an in-body table is not repeated at the end.
    """
    entry_by_num = _by_number(tables, supp_tables, "table_number")
    placed: set[int] = set()

    def fallback(m: re.Match) -> str:
        num = int(m.group(2))
        entry = entry_by_num.get(num)
        supp = entry[1] if entry else False
        return f"**{_display_label('Table', num, supplementary=supp)}**"

    out: list[str] = []
    for line in text.splitlines():
        m = _LONE_TABLE_EMBED_RE.match(line)
        if m:
            num = int(m.group(2))
            entry = entry_by_num.get(num)
            if placeable is not None and num not in placeable:
                entry = None
            block = _table_block(entry[0], supplementary=entry[1]) if entry else None
            if block:
                placed.add(num)
                # Blank lines around the block so the pipe table parses as a
                # block element rather than joining the neighbouring paragraph.
                out.extend(("", block, ""))
                continue
        out.append(_INLINE_TABLE_RE.sub(fallback, line))
    return "\n".join(out), placed


_REF_TOKEN_RE = re.compile(r"\{(fig|tab):(\d+)\}")


def _rewrite_inline_ref_tokens(text: str, *, number_supplementary: bool = True) -> str:
    """Resolve inline reference tokens `{fig:N}` / `{tab:N}` to display text.

    These are the co-scientist inline cross-reference convention in section
    bodies. The dashboard resolves them live; on export they must be turned
    into plain text or the literal `{fig:1}` token leaks into the .docx/PDF
    (same class of gap as `{doi:…}`). N ≥ the +100 supplementary offset renders
    as "Supplementary Figure/Table N-100"; otherwise "Figure/Table N".

    `number_supplementary=False` turns the offset convention off: in a report or
    proposal, table 100 is the hundredth table, not supplementary table 0 (see
    `prepare_export`).
    """
    off = _figures.SUPPLEMENTARY_NUMBER_OFFSET

    def repl(m: re.Match) -> str:
        noun = "Figure" if m.group(1) == "fig" else "Table"
        n = int(m.group(2))
        if number_supplementary and _figures.is_supplementary_number(n):
            return f"Supplementary {noun} {n - off}"
        return f"{noun} {n}"

    return _REF_TOKEN_RE.sub(repl, text)


def _dangling_artifact_refs(manuscript: str, bundle: dict, *, scope: str,
                            include_main: bool, include_supp: bool) -> list[str]:
    """Body references to a figure/table this export does not actually contain.

    The check every other export guard misses, because each one verifies that
    something is PRESENT somewhere: `orphan_references` compares prose against
    everything registered, so a table that is registered but excluded from THIS
    file passes it. Yet the reader gets a reference with nothing behind it.

    That is how feedback 0e394fb76649 lost a table silently: in a 107-table
    report, table 107 crossed the +100 supplementary threshold, `scope="main"`
    dropped it, and the body's `![](table:107)` rendered as nothing. 94 of 95
    references resolved and no warning said which one didn't — it was found by
    counting tables by hand.
    """
    referenced: dict[str, set[int]] = {"Figure": set(), "Table": set()}
    for m in _INLINE_FIGURE_RE.finditer(manuscript):
        referenced["Figure"].add(int(m.group(2)))
    for m in _INLINE_TABLE_RE.finditer(manuscript):
        referenced["Table"].add(int(m.group(2)))
    for m in _REF_TOKEN_RE.finditer(manuscript):
        referenced["Figure" if m.group(1) == "fig" else "Table"].add(int(m.group(2)))

    sources = {
        "Figure": (bundle["figures"], bundle["supplementary_figures"], "figure_number"),
        "Table": (bundle["tables"], bundle["supplementary_tables"], "table_number"),
    }
    out: list[str] = []
    for kind in ("Figure", "Table"):
        main, supp, key = sources[kind]
        main_nums = {d.get(key) for d in main}
        supp_nums = {d.get(key) for d in supp}
        for n in sorted(referenced[kind]):
            if (n in main_nums and include_main) or (n in supp_nums and include_supp):
                continue
            if n in main_nums or n in supp_nums:
                where = "supplementary" if n in supp_nums else "main"
                out.append(
                    f"the body references {kind} {n}, which is registered as {where} "
                    f"content and excluded by scope={scope!r} — the reference renders "
                    f"with nothing behind it. Export the matching scope, or renumber."
                )
            else:
                out.append(
                    f"the body references {kind} {n} but no such {kind.lower()} is "
                    f"registered — nothing is rendered at that point"
                )
    return out


def _rewrite_inline_citations(
    text: str, refs: list[dict]
) -> tuple[str, list[str]]:
    """Rewrite body `{doi:DOI}` markers to pandoc citations `[@citation_key]`.

    Without this, --citeproc never sees a citation: the literal `{doi:…}`
    string passes straight through into the .docx and no bibliography is
    emitted (the web renderer turns the marker into a link, so the gap only
    surfaces on export). Matching is case-insensitive on the DOI — refs from
    CrossRef are stored lowercased, but a manually-added DOI may not be, and
    the body marker may use either case.

    DOIs with no registered reference are left literal and returned so the
    caller can warn; they're the same set prepare_export already reports as
    `unresolved_citations`.

    Also resolves `{ref:key}`/`{cite:key}` (a registered citation_key directly,
    for DOI-less works) and folds an author-written raw `[@key]` into the group.
    A RUN of ANY adjacent citation tokens collapses into ONE pandoc group
    `[@a; @b]`, not `[@a][@b]` — pandoc parses `[@a][@b]` as a markdown link and
    mangles the output; this also fixes a `{doi}` run left abutting a following
    `[@key]` (feedback 57964d23cdef).

    Returns (text, unresolved) where unresolved holds DOIs with no registered
    reference AND `{ref:key}` keys that aren't a registered citation_key — both
    left literal so the caller can warn.
    """
    key_by_doi = {
        (r.get("doi") or "").strip().lower(): r["citation_key"]
        for r in refs
        if r.get("doi") and r.get("citation_key")
    }
    known_keys = {r["citation_key"] for r in refs if r.get("citation_key")}
    unmatched: list[str] = []

    def repl(m: re.Match) -> str:
        keys: list[str] = []
        leftover: list[str] = []
        for tm in re.finditer(_CITE_TOKEN, m.group(0)):
            tok = tm.group(0)
            if tok.startswith("{doi:"):
                d = _DOI_INLINE_RE.match(tok).group(1).strip()
                key = key_by_doi.get(d.lower())
                if key:
                    keys.append(key)
                else:
                    unmatched.append(d)
                    leftover.append("{doi:%s}" % d)
            elif tok.startswith("[@"):
                for k in _RAW_CITE_RE.match(tok).group(1).split(";"):
                    k = k.strip().lstrip("@").strip()
                    if k:
                        keys.append(k)
            else:  # {ref:key} / {cite:key}
                k = _CITE_KEY_RE.match(tok).group(1).strip()
                if k in known_keys:
                    keys.append(k)
                else:
                    unmatched.append(k)
                    leftover.append(tok)     # leave literal so the gap is visible
        seen: set = set()
        ordered = [k for k in keys if not (k in seen or seen.add(k))]
        cite = "[%s]" % "; ".join("@" + k for k in ordered) if ordered else ""
        return cite + "".join(leftover)

    return _CITE_RUN_RE.sub(repl, text), unmatched


def _figure_alt(fig: dict, *, supplementary: bool) -> str:
    """The caption line for a figure, as markdown alt text.

    Bold the "Figure N." label; the caption/legend stay regular weight (the
    markdown is honored by both engines — pandoc parses the alt, the native
    renderer renders the alt's inline tokens). Newlines are collapsed so the
    `![ ... ]( ... )` stays a single image node.

    Shared by the appendix and the in-body `![](figure:N)` rewrite so an inline
    figure and an appendix figure are captioned identically.
    """
    label = _display_label("Figure", fig.get("figure_number"),
                           supplementary=supplementary)
    parts = [f"**{label.rstrip('.')}.**"]
    for field in ("caption", "legend"):
        val = (fig.get(field) or "").strip()
        if val:
            parts.append(val)
    return " ".join(parts).replace("\n", " ").strip()


def _figure_block(fig: dict, *, supplementary: bool) -> str | None:
    bp = fig.get("blob_path")
    if not bp:
        return None
    return f"![{_figure_alt(fig, supplementary=supplementary)}]({pathlib.Path(bp).name})"


def _table_block(tbl: dict, *, supplementary: bool) -> str | None:
    """A bold 'Table N.' caption line followed by the stored pipe-table markdown.

    Shared by the appendix and the in-body `![](table:N)` rewrite, so a table
    renders the same whether the author placed it or it fell to the appendix.
    """
    content = (tbl.get("content") or "").strip()
    if not content:
        return None
    label = _display_label("Table", tbl.get("table_number"),
                           supplementary=supplementary)
    caption = (tbl.get("caption") or tbl.get("title") or "").strip()
    caption = " ".join(caption.split())  # collapse newlines for the caption line
    head = f"**{label}.** {caption}".rstrip() if caption else f"**{label}.**"
    # Blank line between the caption and the table so it parses as a block.
    return f"{head}\n\n{content}"


def _figures_appendix(
    figures: list[dict], supp_figures: list[dict], heading: str = "Figures",
    *, skip: set[int] | None = None,
) -> str:
    """Markdown that embeds each registered figure's image as a Pandoc figure.

    The body only carries 'Figure N' text references, so without this pandoc
    has no image to embed (dev-todo EXP-1). We append a Figures section whose
    image targets are the blob basenames — matching the files export_to_path
    writes into the pandoc working dir.

    `skip` holds numbers the body already positions via `![](figure:N)`; those
    are omitted, because appending them here rendered the same image twice —
    once where the author put it and once at the end.
    """
    skip = skip or set()
    blocks = [b for b in (
        *(_figure_block(f, supplementary=False) for f in figures
          if f.get("figure_number") not in skip),
        *(_figure_block(f, supplementary=True) for f in supp_figures
          if f.get("figure_number") not in skip),
    ) if b]
    if not blocks:
        return ""
    return f"## {heading}\n\n" + "\n\n".join(blocks) + "\n"


def _tables_appendix(
    tables: list[dict], supp_tables: list[dict], heading: str = "Tables",
    *, skip: set[int] | None = None,
) -> str:
    """Markdown that appends each registered table after the body.

    Like figures, the body only carries 'Table N' text references — the table
    markup itself lives in each table doc's `content` (a pandoc/GFM pipe table)
    and was never concatenated into the manuscript, so pandoc/python-docx never
    saw it and every export dropped all tables (dev-todo: tables-appendix). We
    emit a Tables section: a bold 'Table N.' caption line followed by the
    stored pipe-table markdown, mirroring `_figures_appendix`.

    `skip` holds numbers the body positions itself via `![](table:N)`.
    """
    skip = skip or set()
    blocks = [b for b in (
        *(_table_block(t, supplementary=False) for t in tables
          if t.get("table_number") not in skip),
        *(_table_block(t, supplementary=True) for t in supp_tables
          if t.get("table_number") not in skip),
    ) if b]
    if not blocks:
        return ""
    return f"## {heading}\n\n" + "\n\n".join(blocks) + "\n"


_HTML_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&apos;": "'", "&#39;": "'", "&nbsp;": " ",
}


_LATEX_SPAN_RE = re.compile(
    r"\\text(?:it|bf|sc|subscript|superscript)\{[^{}]*\}"
)


def _italicize_taxa(s: str, taxa: list[str]) -> str:
    """Wrap listed taxon names in \\textit{}, only OUTSIDE existing
    \\textit{...} spans (so names CrossRef already italicized aren't doubled),
    with word boundaries (so 'Cuscutaceae' and family/order ranks stay roman).

    We italicize the genus/infrageneric NAME itself, plus the abbreviated
    binomial form ("C. campestris"), which is an unambiguous signal. We do NOT
    auto-italicize the word after a full genus ("Cuscuta chinensis") — too many
    titles put an ordinary English word there ("Cuscuta species",
    "Cuscuta-derived", "Cuscuta infection"), and wrongly italicizing one reads
    as an error. The genus alone becoming consistent already fixes the report.
    """
    names = [t.strip() for t in (taxa or []) if t and t.strip()]
    if not names:
        return s
    name_alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    initials = "".join(sorted({n[0] for n in names if n[:1].isalpha()}))
    pats = []
    if initials:
        # Abbreviated binomial: "C. campestris" — single genus-initial + epithet.
        pats.append(rf"\b[{re.escape(initials)}]\.\s+[a-z][a-z-]{{2,}}\b")
    pats.append(rf"\b(?:{name_alt})\b")  # standalone genus / infrageneric name
    rx = re.compile("|".join(pats))
    repl = lambda m: "\\textit{" + m.group(0) + "}"

    out, last = [], 0
    for span in _LATEX_SPAN_RE.finditer(s):
        out.append(rx.sub(repl, s[last:span.start()]))
        out.append(span.group(0))  # leave already-italic spans untouched
        last = span.end()
    out.append(rx.sub(repl, s[last:]))
    return "".join(out)


def _title_to_bibtex(title: str, taxa: list[str] | None = None) -> str:
    """Convert a CrossRef title (which may carry JATS/HTML markup) into a
    BibTeX-safe title value (dev-todo bib-quality):

    - `<i>`/`<em>` → \\textit{}, `<b>`/`<strong>` → \\textbf{},
      `<scp>` → \\textsc{}, `<sub>`/`<sup>` → \\textsubscript/superscript;
      strip any other tags. Genus names etc. thus render italic instead of
      literal "<i>Cuscuta</i>".
    - decode the few HTML entities CrossRef emits; collapse internal
      whitespace/newlines (some titles arrive with indented tags).
    - wrap the whole title in an extra brace group so CSL case-folding
      (sentence-casing) does NOT down-case proper nouns / acronyms
      (Cuscuta, DNA, ITS, Galápagos, …).
    """
    s = title
    for ent, ch in _HTML_ENTITIES.items():
        s = s.replace(ent, ch)
    flags = re.IGNORECASE | re.DOTALL
    s = re.sub(r"<\s*(?:i|em)\s*>(.*?)<\s*/\s*(?:i|em)\s*>", r"\\textit{\1}", s, flags=flags)
    s = re.sub(r"<\s*(?:b|strong)\s*>(.*?)<\s*/\s*(?:b|strong)\s*>", r"\\textbf{\1}", s, flags=flags)
    s = re.sub(r"<\s*scp\s*>(.*?)<\s*/\s*scp\s*>", r"\\textsc{\1}", s, flags=flags)
    s = re.sub(r"<\s*sub\s*>(.*?)<\s*/\s*sub\s*>", r"\\textsubscript{\1}", s, flags=flags)
    s = re.sub(r"<\s*sup\s*>(.*?)<\s*/\s*sup\s*>", r"\\textsuperscript{\1}", s, flags=flags)
    s = re.sub(r"<[^>]+>", "", s)            # drop any remaining tags
    s = re.sub(r"\s+", " ", s).strip()       # collapse whitespace/newlines
    # Auto-italicize project taxon names that the source didn't mark up.
    s = _italicize_taxa(s, taxa or [])
    # Outer braces protect the whole title from CSL case transformation.
    return "{" + s + "}"


def _ref_to_bibtex(ref: dict, taxa: list[str] | None = None) -> str:
    """Build an @article BibTeX entry from a reference doc.

    If the ref carries a literal `bibtex` field, return that verbatim.
    """
    if ref.get("bibtex"):
        return ref["bibtex"].rstrip() + "\n"
    key = ref.get("citation_key") or "unknown"
    fields: list[str] = []
    if ref.get("title"):
        # Note the double braces: outer = the field, inner (from
        # _title_to_bibtex) = case protection.
        fields.append(f"  title = {{{_title_to_bibtex(ref['title'], taxa)}}}")
    authors = ref.get("authors")
    if isinstance(authors, list):
        author_str = " and ".join(authors)
    else:
        author_str = authors
    if author_str:
        fields.append(f"  author = {{{author_str}}}")
    if ref.get("journal"):
        fields.append(f"  journal = {{{ref['journal']}}}")
    if ref.get("year"):
        fields.append(f"  year = {{{ref['year']}}}")
    if ref.get("volume"):
        fields.append(f"  volume = {{{ref['volume']}}}")
    if ref.get("issue"):
        fields.append(f"  number = {{{ref['issue']}}}")
    if ref.get("pages"):
        # CrossRef "123-130" → BibTeX en-dash page range.
        pages = str(ref["pages"]).replace("--", "-").replace("-", "--")
        fields.append(f"  pages = {{{pages}}}")
    if ref.get("issn"):
        fields.append(f"  issn = {{{ref['issn']}}}")
    if ref.get("publisher"):
        fields.append(f"  publisher = {{{ref['publisher']}}}")
    if ref.get("doi"):
        fields.append(f"  doi = {{{ref['doi']}}}")
    body = ",\n".join(fields)
    return f"@article{{{key},\n{body}\n}}\n"


def _display_label(kind: str, num, *, supplementary: bool) -> str:
    """The label for a figure/table, in the SAME spelling the manuscript body uses.

    `STable 5` / `SFigure 1`, not `Table S5` / `Figure S1`. The appendix used the
    S-suffix form while the prose cross-references (and every skill) use the
    S-prefix form, so a reader following "STable 5" in the text found "Table S5."
    in the appendix — a regression introduced when supplementary items moved onto
    this export path; the paper's earlier submission had the prefix form in both.

    One helper so the two cannot drift again: every label in a rendered document
    comes from here.
    """
    if supplementary and isinstance(num, int):
        return f"S{kind} {num - SUPPLEMENTARY_NUMBER_OFFSET}"
    return f"{kind} {num}"


def _run_output_at(run: dict) -> str | None:
    """When this run plausibly produced output.

    Deliberately NOT just `finished_at`: that field is stamped by BOOKKEEPING as
    well as by a real finish. `auto_finish_stale_runs` closing a months-old row
    writes `finished_at = now` with `exit_code = -2` ("confirmed not running,
    outcome unrecorded"), so reading it would make every analysis look like it
    produced output the moment someone tidied the Running Jobs panel — and every
    artifact older than that cleanup falsely stale. Measured once: closing 28
    long-dead rows moved one analysis's apparent last output five days forward,
    which would have flagged four untouched figures.

    For such a row the honest upper bound is the last PROOF OF LIFE:
    `last_heartbeat` is only ever bumped while a run is seen alive, so it marks
    when output could still have been appearing; `started_at` when there is
    nothing better.
    """
    if run.get("exit_code") == -2:
        stamps = [s for s in (run.get("started_at"), run.get("last_heartbeat")) if s]
        return max(stamps) if stamps else None
    return run.get("finished_at") or run.get("started_at")


def _latest_analysis_output_at(state: State, slug: str, analysis: str) -> str | None:
    """Most recent moment `analysis` produced output (see `_run_output_at` — a
    run still in flight counts from `started_at`, since it is already newer than
    any artifact predating it). None if the analysis has no runs, or does not
    exist — an artifact naming an analysis that was never registered is a
    mislabelled link, not a staleness signal, so it is reported separately."""
    from . import runs as _runs
    # create_analysis() slugifies, so an analysis registered as "qtl_overlap" is
    # stored under "qtl-overlap". Try the link verbatim, then slugified: without
    # this, a plausible-looking link resolves to nothing and the warning silently
    # never fires — the same silent-no-op class of bug this check exists to catch.
    from ..util import slugify
    rows = None
    for candidate in (analysis, slugify(analysis)):
        try:
            rows = _runs.list_analysis_runs(state, slug, candidate)
            break
        except NotFound:
            continue
    if rows is None:
        return None
    stamps = [s for s in (_run_output_at(r) for r in rows) if s]
    return max(stamps) if stamps else None


def _stale_artifact_warnings(
    state: State, slug: str, figures: list[dict], tables: list[dict],
) -> list[str]:
    """Warn for every figure/table whose `source_analysis` has produced output
    since the artifact was last updated. Artifacts with no link are silent —
    the link is optional, so absence means "unknown", never "fresh"."""
    out: list[str] = []
    for kind, label_key, items in (
        ("Figure", "figure_number", figures),
        ("Table", "table_number", tables),
    ):
        for a in items:
            analysis = a.get("source_analysis")
            if not analysis:
                continue
            latest = _latest_analysis_output_at(state, slug, analysis)
            # content_updated_at, NOT updated_at: the row's mtime also moves for
            # a caption/legend fix and for the call that adds the link itself, so
            # comparing against it let a metadata edit certify stale data as
            # fresh. Falls back only for rows written before the field existed
            # and never touched since.
            updated = (a.get("content_updated_at") or a.get("updated_at")
                       or a.get("created_at"))
            if not latest or not updated:
                continue
            # ISO-8601 UTC strings from util.now_iso() — lexicographic order is
            # chronological order, so no parsing is needed.
            if updated < latest:
                out.append(
                    f"{kind} {a.get(label_key)} (content last changed {updated}) "
                    f"is older than its linked analysis '{analysis}' (last output "
                    f"{latest}) — regenerate it before exporting, or confirm it "
                    f"is unaffected"
                )
    return out


def _provenance_coverage_warnings(
    state: State, slug: str, figures: list[dict], tables: list[dict],
) -> list[str]:
    """Report artifacts with NO `source_analysis`, and how many analyses exist.

    The gap this closes (feedback f3f9b4b56577): the staleness check above fires
    only for artifacts that HAVE a link, so the incentive ran backwards —

      - link your artifact honestly  → you may get a warning
      - link nothing at all          → silence

    which made the most dangerous state the quietest one. A paper with six
    computed tables and zero recorded runs passed every structural check. The
    reporter's case had 9 hours of foreground `ssh … python …` training whose
    commands, hyperparameters and checkpoints are now unrecoverable, and none of
    it was visible to any guard.

    Absence of a link means UNKNOWN, and unknown is worth saying out loud. This
    reports the counts and leaves the judgement to the agent — a schematic figure
    legitimately has no analysis behind it, and the server cannot tell which is
    which. Deliberately not an error, and it costs one extra backend call (the
    analyses list; zero analyses implies zero runs).
    """
    items = [("Figure", "figure_number", figures), ("Table", "table_number", tables)]
    total = sum(len(x[2]) for x in items)
    if total == 0:
        return []
    unlinked: list[str] = []
    for kind, key, rows in items:
        for a in rows:
            if not (a.get("source_analysis") or "").strip():
                unlinked.append(f"{kind} {a.get(key)}")
    if not unlinked:
        return []
    n_analyses = len(state.backend.list_collection(
        state.project_path("papers", slug, "analyses")))
    shown = ", ".join(unlinked[:8]) + ("…" if len(unlinked) > 8 else "")
    if n_analyses == 0:
        return [
            f"NO analysis provenance on this paper: {len(unlinked)} of {total} "
            f"registered figures/tables have no `source_analysis`, and no analysis "
            f"is registered at all ({shown}). If any of those numbers were "
            f"computed, the command that produced them is not recorded anywhere — "
            f"back-fill now with create_analysis + record_analysis_run and link via "
            f"update_figure/update_table(source_analysis=…). Journals that require "
            f"a data/code availability statement need exactly this. Schematics and "
            f"hand-built tables need no link — say so and move on."
        ]
    return [
        f"{len(unlinked)} of {total} registered figures/tables have no "
        f"`source_analysis` ({shown}) while {n_analyses} analysis/analyses are "
        f"registered — the unlinked ones are invisible to the staleness check. "
        f"Link them, or confirm they are not computational outputs."
    ]


BUNDLE_FIELDS = (
    "slug", "paper", "sections", "manuscript", "figures", "supplementary_figures",
    "tables", "supplementary_tables", "references", "bibtex", "placeholders",
    "legend_warnings", "unresolved_citations", "doiless_uncited_refs",
    "csl_filename", "csl_slug", "csl_source", "csl_status", "requirements_check",
    "review_triage", "warnings",
)


def numbers_supplementary(paper: dict) -> bool:
    """Whether the "+100 = supplementary" numbering convention applies.

    Only to journal papers. A report or proposal has no supplementary section,
    and its 100th table is simply table 100 — applying the offset there
    reclassified 8 body tables as supplementary and then `scope="main"` dropped
    them from the export, one of them cited in the body (feedback 0e394fb76649:
    a 107-table technical proposal).
    """
    return (paper.get("doc_type") or "paper").lower() == "paper"


def prepare_export(
    state: State,
    slug: str,
    *,
    fields: list[str] | None = None,
    stage_dir: str | None = None,
) -> dict:
    """Collect everything needed to export `slug` to a finished document.

    Returns a dict with:
        slug, paper, sections, manuscript (str), figures, tables,
        references, bibtex (str), warnings, placeholders,
        unresolved_citations (list of DOIs), suggested_csl_filename.

    `fields` narrows the reply to those top-level keys (`slug` is always kept).
    A document with ~100 tables makes the full bundle a few hundred KB, past the
    tool-reply limit; ask for `["sections", "tables"]` instead of taking the
    file fallback. An unknown key raises rather than returning an empty reply.

    `stage_dir` also writes every figure's image blob into that directory and
    adds `local_path` to each figure dict — what you need to post-process the
    bundle yourself, since `blob_path` alone names a remote object.
    """
    if fields:
        unknown = [f for f in fields if f not in BUNDLE_FIELDS]
        if unknown:
            raise ValueError(
                f"unknown prepare_export field(s): {', '.join(unknown)}; "
                f"choose from {', '.join(BUNDLE_FIELDS)}"
            )
    bundle = _papers.get_paper_state(state, slug)
    # A report/proposal has no supplementary split — take every figure/table as
    # main content rather than reading numbers ≥100 as supplementary.
    split_supp = numbers_supplementary(bundle["paper"])
    figs = _figures.list_figures(state, slug, supplementary=False if split_supp else None)
    supp_figs = _figures.list_figures(state, slug, supplementary=True) if split_supp else []
    tbls = _tables.list_tables(state, slug, supplementary=False if split_supp else None)
    supp_tbls = _tables.list_tables(state, slug, supplementary=True) if split_supp else []
    refs = _references.list_references(state, slug)

    manuscript = bundle["manuscript"]
    placeholders = _scan_placeholders(manuscript)
    cited_dois = _extract_cited_dois(manuscript)
    known_dois = {r["doi"] for r in refs if r.get("doi")}
    unresolved = sorted(set(cited_dois) - known_dois)

    # A registered ref only appears in the rendered bibliography if it is cited
    # inline; citeproc drops uncited entries even though they're in the .bib. A
    # DOI-less ref has no {doi:} token, so unless it is cited via {ref:key} /
    # {cite:key} / [@key] it silently vanishes. Warn about those.
    cited_keys = {k.lower() for k in _CITE_KEY_RE.findall(manuscript)}
    cited_keys |= {k.strip().lstrip("@").strip().lower()
                   for grp in _RAW_CITE_RE.findall(manuscript) for k in grp.split(";")}
    cited_keys |= {r["citation_key"].lower() for r in refs
                   if r.get("doi") and r.get("citation_key")
                   and r["doi"] in cited_dois}
    uncited_doiless = sorted(
        r["citation_key"] for r in refs
        if not r.get("doi") and r.get("citation_key")
        and r["citation_key"].lower() not in cited_keys)

    taxa = _references.get_reference_taxa(state)
    bibtex = "".join(_ref_to_bibtex(r, taxa) for r in refs)

    paper = bundle["paper"]
    # Resolve the journal's citation style (offline — registry → in-code map →
    # kebab guess). export_to_path does the actual download.
    csl = _csl.resolve_csl_filename(state, paper.get("journal"))

    # Journal / paper-type requirement check (word limits, item caps, …).
    req_check = _requirements.check_requirements(state, slug)

    # Review-triage gate: accepted comments must be resolved, and rejected
    # comments must carry a rebuttal (response) for the response letter.
    triage = _reviews.review_triage_summary(state, slug)

    warnings: list[str] = []
    if placeholders:
        warnings.append(f"{len(placeholders)} placeholder marker(s) in manuscript")
    if unresolved:
        warnings.append(f"{len(unresolved)} unresolved {{doi:…}} citation(s)")
    if uncited_doiless:
        warnings.append(
            f"{len(uncited_doiless)} DOI-less registered ref(s) not inline-cited "
            f"→ absent from the rendered bibliography ({', '.join(uncited_doiless[:6])}"
            f"{'…' if len(uncited_doiless) > 6 else ''}); cite them with "
            f"{{cite:key}} / {{ref:key}}")
    for s in bundle["sections"]:
        if s.get("status") == "pending" and (s.get("word_count") or 0) == 0:
            warnings.append(f"section '{s['key']}' is empty")
    if req_check.get("violations"):
        warnings.append(
            f"{len(req_check['violations'])} journal-requirement violation(s) "
            f"— see requirements_check"
        )
    if triage["rejected_without_rationale"]:
        warnings.append(
            f"{triage['rejected_without_rationale']} rejected comment(s) missing a "
            f"rebuttal (response) — see review_triage / run /paper-revision"
        )
    if triage["accepted_unresolved"]:
        warnings.append(
            f"{triage['accepted_unresolved']} accepted comment(s) not yet resolved "
            f"— see review_triage"
        )

    # Display-object guardrails (feedback 4cd03d45c221): inline markdown tables/
    # images that were never registered, and prose "Table N"/"Figure N"
    # references with no matching registered object (dropped / mis-numbered).
    warnings.extend(_display_lint.inline_object_warnings(manuscript))
    orphans = _display_lint.orphan_references(
        manuscript,
        [t["table_number"] for t in tbls + supp_tbls],
        [f["figure_number"] for f in figs + supp_figs],
        number_supplementary=split_supp,
    )
    if orphans["tables"]:
        warnings.append(
            "prose references Table " + ", ".join(orphans["tables"])
            + " but no such registered table exists (register with add_table, "
            "or fix the reference)"
        )
    if orphans["figures"]:
        warnings.append(
            "prose references Figure " + ", ".join(orphans["figures"])
            + " but no such registered figure exists (register with add_figure, "
            "or fix the reference)"
        )

    # Provenance staleness — an artifact left behind by a rerun analysis.
    #
    # This is the one failure class no structural check can see: the xlsx/PNG is
    # perfectly well-formed, so it validates, and the manuscript prose has been
    # updated to the new numbers while the artifact still holds the old ones. It
    # shipped once as a supplementary table reporting 28.7% against a manuscript
    # (and figure legend) that said 33.3%. Only a timestamp comparison against
    # provenance catches it — deliberately NOT a content diff, because the
    # DB-embedded preview can be narrower than the source file (the column that
    # changed was absent from the preview, so any preview-based check would have
    # passed too).
    warnings.extend(_stale_artifact_warnings(state, slug, figs + supp_figs,
                                             tbls + supp_tbls))
    # ...and the counterpart: artifacts with no link at all, which the staleness
    # check cannot see by construction.
    warnings.extend(_provenance_coverage_warnings(state, slug, figs + supp_figs,
                                                 tbls + supp_tbls))

    # A registered supplementary item with NO caption. Cheap and certain: two
    # supplementary tables shipped cited-but-uncaptioned in one session, so the
    # reviewer's copy carried an attachment that nothing described.
    #
    # The richer check the field asked for — opening the workbook and diffing the
    # caption's own claims (sheet count, row count, value ranges) against the file
    # — is NOT attempted: it needs spreadsheet access, and a caption whose numbers
    # are merely stale is the `result_only_in_methods`/staleness class above.
    for tbl in supp_tbls:
        if not str(tbl.get("caption") or "").strip():
            n = tbl.get("table_number")
            label = (f"STable {n - _tables.SUPPLEMENTARY_NUMBER_OFFSET}"
                     if isinstance(n, int) else f"table {n}")
            warnings.append(
                f"{label} is registered but has no caption — a cited supplementary "
                f"table with nothing describing it reaches the reviewer as an "
                f"unexplained attachment"
            )
    for fig in supp_figs:
        if not str(fig.get("caption") or "").strip():
            n = fig.get("figure_number")
            label = (f"SFigure {n - _figures.SUPPLEMENTARY_NUMBER_OFFSET}"
                     if isinstance(n, int) else f"figure {n}")
            warnings.append(f"{label} is registered but has no caption")

    # Legend QA — over-long or Results-duplicating figure/table legends. One
    # summary line per flagged item feeds the pre-flight warnings; the full
    # detail is available from lint_legends(slug).
    from . import legend_lint as _legend_lint
    legend_report = _legend_lint.lint_legends(state, slug)
    legend_warnings = [
        f"{f['item']} legend: {', '.join(f['flags'])} ({f['word_count']} words)"
        for f in legend_report["findings"]
    ]
    warnings.extend(legend_warnings)

    # Optionally hand back real files: `blob_path` names a remote object, so an
    # agent post-processing this bundle (assembling its own .docx, say) had no
    # way to reach the image bytes without a per-figure get_figure(dest_dir=…).
    if stage_dir:
        dest = pathlib.Path(stage_dir).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        for fig in (*figs, *supp_figs):
            bp = fig.get("blob_path")
            if not bp:
                continue
            data = state.backend.get_blob(bp)
            if data is None:
                warnings.append(
                    f"figure {fig.get('figure_number')} blob missing at {bp} "
                    f"— not staged to {dest}")
                continue
            local = dest / pathlib.Path(bp).name
            local.write_bytes(data)
            fig["local_path"] = str(local.resolve())

    out = {
        "slug": slug,
        "paper": paper,
        "sections": bundle["sections"],
        "manuscript": manuscript,
        "figures": figs,
        "supplementary_figures": supp_figs,
        "tables": tbls,
        "supplementary_tables": supp_tbls,
        "references": refs,
        "bibtex": bibtex,
        "placeholders": placeholders,
        "legend_warnings": legend_warnings,
        "unresolved_citations": unresolved,
        "doiless_uncited_refs": uncited_doiless,
        "csl_filename": csl["csl_filename"],
        "csl_slug": csl["csl_slug"],
        "csl_source": csl["csl_source"],
        "csl_status": csl["csl_status"],
        "requirements_check": req_check,
        "review_triage": triage,
        "warnings": warnings,
    }
    if fields:
        keep = {"slug", *fields}
        return {k: v for k, v in out.items() if k in keep}
    return out


_VALID_FORMATS = {"docx", "tex", "pdf", "md"}


def _format_pandoc_args(fmt: str, manuscript_filename: str, output_filename: str,
                       has_bib: bool, csl_path: str | None) -> list[str]:
    # Disable yaml_metadata_block so a body-level `---` (thematic break /
    # section divider) isn't mis-parsed as YAML front matter and crash the
    # export (dev-todo P1-3). Everything else in pandoc's markdown stays on.
    args: list[str] = [
        manuscript_filename,
        "-f", "markdown-yaml_metadata_block",
        "-o", output_filename,
    ]
    if fmt == "tex":
        args.extend(["-t", "latex"])
    elif fmt == "pdf":
        # Use default pdf engine (xelatex/pdflatex if available)
        pass
    elif fmt == "md":
        args.extend(["-t", "markdown"])
    # docx is the implicit default when output ext is .docx. We do NOT pass a
    # --reference-doc: pandoc's built-in reference carries the "Table" style
    # (borders/shading) and other style mappings; the base font is instead
    # swapped afterwards (apply_base_font_to_docx) so table styling survives.
    if has_bib:
        args.extend(["--bibliography", "references.bib", "--citeproc"])
    if csl_path:
        args.extend(["--csl", csl_path])
    return args


def _place_csl(
    state: State,
    tmp_path: pathlib.Path,
    bundle: dict,
    explicit_csl_path: str | None,
) -> tuple[str | None, str, str | None, list[str]]:
    """Put a CSL style file into `tmp_path` for pandoc to use.

    Returns (csl_arg, csl_status, csl_filename, warnings):
      - csl_arg      — filename to pass to `pandoc --csl`, or None
      - csl_status   — explicit | downloaded | missing | no_journal
      - csl_filename — the resolved/used filename, or None
      - warnings     — human-readable notes for the export report

    An explicit path wins. Otherwise the journal (already resolved to a
    filename by prepare_export) is downloaded from the CSL styles repo; a
    successful download of a *guessed* slug is written back to the
    per-project registry so it sticks.
    """
    warnings: list[str] = []

    if explicit_csl_path:
        src = pathlib.Path(explicit_csl_path).expanduser()
        if src.is_file():
            shutil.copy2(src, tmp_path / src.name)
            return src.name, "explicit", src.name, warnings
        warnings.append(
            f"csl_path not found: {explicit_csl_path} — used pandoc's "
            "default citation style"
        )
        return None, "missing", None, warnings

    csl_filename = bundle.get("csl_filename")
    if not csl_filename:
        return None, "no_journal", None, warnings

    try:
        data = _csl.download_csl(csl_filename)
    except _csl.CslNotFound as e:
        warnings.append(
            f"CSL '{csl_filename}' not in the styles repo ({e}) — used "
            "pandoc's default citation style. If you know the correct "
            "filename, register it with register_journal_csl."
        )
        return None, "missing", csl_filename, warnings
    except Exception as e:  # network failure — non-fatal, fall back
        warnings.append(
            f"CSL download failed ({e}) — used pandoc's default style"
        )
        return None, "missing", csl_filename, warnings

    (tmp_path / csl_filename).write_bytes(data)
    # Cache a working guess so the next export of this journal skips guessing.
    if bundle.get("csl_source") == "guess":
        try:
            _csl.register_journal_csl(
                state, bundle["paper"].get("journal") or "", csl_filename,
                notes="auto-registered after a successful CSL download",
            )
        except Exception:
            pass
    return csl_filename, "downloaded", csl_filename, warnings


# pandoc emits several near-empty OOXML parts (comments.xml, docProps/
# custom.xml, ...). Word/LibreOffice/Google Docs tolerate them, but Hancom
# Office's OOXML importer SIGSEGVs (dev-todo P0-1). The robust fix is a
# LibreOffice round-trip (`_normalize_docx_via_soffice`); when soffice is
# unavailable we fall back to stripping the known-problem parts + their refs.
_DOCX_PROBLEM_PARTS = (
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
    "docProps/custom.xml",
)


def _normalize_docx_via_soffice(path: pathlib.Path) -> bool:
    """Round-trip the .docx through LibreOffice in place to normalize its
    OOXML into a structure Hancom Office can open. soffice rewrites the whole
    package cleanly, dropping the empty parts that crash Hancom's importer —
    more robust than chasing individual parts. Returns True if the file was
    replaced; False if soffice/libreoffice is missing or conversion failed.
    """
    for binary in ("soffice", "libreoffice"):
        with tempfile.TemporaryDirectory(prefix="docx-norm-") as d:
            try:
                proc = subprocess.run(
                    [binary, "--headless", "--convert-to", "docx",
                     "--outdir", d, str(path)],
                    capture_output=True, text=True, timeout=180,
                )
            except FileNotFoundError:
                continue  # try the next binary name
            except subprocess.TimeoutExpired:
                return False
            produced = pathlib.Path(d) / f"{path.stem}.docx"
            if proc.returncode == 0 and produced.is_file():
                shutil.copy2(produced, path)
                return True
            return False
    return False


def _strip_problem_docx_parts(path: pathlib.Path) -> bool:
    """Fallback for when soffice is unavailable: drop the known-empty parts
    that crash Hancom and scrub their refs.

    Removes each present `_DOCX_PROBLEM_PARTS` entry, its `<Override>` in
    `[Content_Types].xml`, and any `<Relationship>` in any `*.rels` whose
    Target points at it (comment parts are referenced from
    word/_rels/document.xml.rels; docProps/custom.xml from _rels/.rels).
    Returns True if the file was modified; no-ops on a non-zip or when no
    problem part is present.
    """
    try:
        with zipfile.ZipFile(path) as zin:
            names = set(zin.namelist())
            drop = {n for n in _DOCX_PROBLEM_PARTS if n in names}
            if not drop:
                return False
            items = [(info, zin.read(info.filename)) for info in zin.infolist()]
    except zipfile.BadZipFile:
        return False

    part_names = "|".join(re.escape("/" + n) for n in drop)
    targets = "|".join(re.escape(n.split("/")[-1]) for n in drop)
    override_re = re.compile(
        r'<Override\b[^>]*\bPartName="(?:' + part_names + r')"[^>]*/>'
    )
    rel_re = re.compile(
        r'<Relationship\b[^>]*\bTarget="(?:[^"]*/)?(?:' + targets + r')"[^>]*/>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in items:
            if info.filename in drop:
                continue
            if info.filename == "[Content_Types].xml":
                data = override_re.sub("", data.decode("utf-8")).encode("utf-8")
            elif info.filename.endswith(".rels"):
                data = rel_re.sub("", data.decode("utf-8")).encode("utf-8")
            zout.writestr(info, data)
    path.write_bytes(buf.getvalue())
    return True


_VALID_SCOPES = {"main", "supplementary", "all"}


def export_to_path(
    state: State,
    slug: str,
    *,
    output_path: str,
    fmt: str | None = None,
    csl_path: str | None = None,
    upload_to_storage: bool = True,
    scope: str = "main",
    page_size: str = _docx_export.DEFAULT_PAGE_SIZE,
) -> dict:
    """Full export pipeline.

    `fmt` is inferred from output_path extension if None.
    `page_size` is "a4" (default) or "letter", applied to every .docx on both
    engines.
    The citation style is auto-resolved from the paper's journal and
    downloaded from the CSL styles repo; pass `csl_path` to override with a
    local CSL file.

    `scope` controls main-vs-supplementary content (a journal receives a main
    manuscript with only the main figures/tables; supplementary items belong
    in a separate file):
      - "main" (default) — full manuscript text + MAIN figures/tables only
        (figure_number / table_number < 100). Supplementary items are excluded.
      - "supplementary" — a standalone 'Supplementary Material' document with
        ONLY the supplementary figures/tables (≥ 101), no main manuscript text.
      - "all" — everything in one file (the pre-split legacy behavior).
    To deliver both, export twice: once with scope="main" and once with
    scope="supplementary" to a second path.

    Returns metadata: local path, blob path (if uploaded), pandoc rc/stderr,
    csl status, plus the prepare_export warnings so the caller can surface
    them.
    """
    scope = (scope or "main").lower()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}; choose from {_VALID_SCOPES}")
    page_size = _docx_export.validate_page_size(page_size)
    include_main = scope in ("main", "all")
    include_supp = scope in ("supplementary", "all")

    bundle = prepare_export(state, slug)
    export_warnings = list(bundle["warnings"])
    split_supp = numbers_supplementary(bundle["paper"])
    if scope == "supplementary" and not split_supp:
        export_warnings.append(
            f"doc_type={bundle['paper'].get('doc_type')!r} has no supplementary "
            f"split (the +100 numbering convention is journal-paper only), so "
            f"scope='supplementary' produces an empty document — use scope='main'"
        )
    export_warnings.extend(_dangling_artifact_refs(
        bundle["manuscript"], bundle, scope=scope,
        include_main=include_main, include_supp=include_supp))
    out = pathlib.Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    inferred = (out.suffix.lstrip(".") or "").lower()
    fmt = (fmt or inferred or "docx").lower()
    if fmt not in _VALID_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; choose from {_VALID_FORMATS}")

    # Non-"paper" docs (reports / other) render .docx natively via python-docx
    # — pandoc's OOXML crashes Hancom (dev-todo P0-1) and these docs don't need
    # citeproc/CSL. Papers, and any non-docx format, stay on the pandoc path.
    doc_type = (bundle["paper"].get("doc_type") or "paper").lower()
    engine = "docx_native" if (doc_type != "paper" and fmt == "docx") else "pandoc"

    with tempfile.TemporaryDirectory(prefix=f"export-{slug}-") as tmp:
        tmp_path = pathlib.Path(tmp)

        # Which figures/tables go in this file depends on `scope`. The main
        # manuscript carries only main items; the supplementary export carries
        # only supplementary items (in its own document a journal stores
        # separately). "all" keeps both together (legacy).
        main_figs = bundle["figures"] if include_main else []
        supp_figs = bundle["supplementary_figures"] if include_supp else []
        main_tbls = bundle["tables"] if include_main else []
        supp_tbls = bundle["supplementary_tables"] if include_supp else []
        staged_figs = [*main_figs, *supp_figs]

        # Lay out manuscript + bib. Escape '---' rules (dev-todo P1-3), then
        # append Tables/Figures sections so registered items get embedded
        # (dev-todo EXP-1 + tables-appendix). For a supplementary-only export
        # there is no main manuscript text — start from a heading.
        placed_figs: set[int] = set()
        placed_tbls: set[int] = set()
        if include_main:
            manuscript_text = _escape_thematic_breaks(bundle["manuscript"])
            # Pass the FULL registered sets so a supplementary item keeps its
            # "SFigure N" / "STable N" label, and `placeable` (the scope-included
            # numbers) decides what may actually be embedded in THIS file.
            manuscript_text, placed_figs = _rewrite_inline_figure_refs(
                manuscript_text, bundle["figures"], bundle["supplementary_figures"],
                placeable={f["figure_number"] for f in staged_figs},
            )
            # `![](table:N)` had no handler at all and rendered as nothing; now
            # it expands into the table where the author placed it.
            manuscript_text, placed_tbls = _rewrite_inline_table_refs(
                manuscript_text, bundle["tables"], bundle["supplementary_tables"],
                placeable={t["table_number"] for t in (*main_tbls, *supp_tbls)},
            )
            tbl_heading, fig_heading = "Tables", "Figures"
            # Place the bibliography BEFORE the Tables/Figures appendices:
            # pandoc --citeproc fills an explicit `#refs` div in place, else it
            # appends the bibliography at document END — after Tables/Figures,
            # which is the wrong order for journal submission. Expected:
            # body → References → Tables → Figure legends → Figures. Pandoc-only
            # (docx_native has no citeproc); only when the paper has references.
            if engine == "pandoc" and bundle["references"]:
                manuscript_text = (manuscript_text.rstrip()
                                   + "\n\n## References\n\n::: {#refs}\n:::\n")
        else:
            manuscript_text = "# Supplementary Material\n"
            tbl_heading, fig_heading = "Supplementary Tables", "Supplementary Figures"

        # Tables before figures (conventional manuscript order). Both
        # appendices carry markup the body only text-references.
        tbl_appendix = _tables_appendix(main_tbls, supp_tbls, heading=tbl_heading,
                                        skip=placed_tbls)
        if tbl_appendix:
            manuscript_text = manuscript_text.rstrip() + "\n\n" + tbl_appendix
        fig_appendix = _figures_appendix(main_figs, supp_figs, heading=fig_heading,
                                         skip=placed_figs)
        if fig_appendix:
            manuscript_text = manuscript_text.rstrip() + "\n\n" + fig_appendix
        # Convert `{doi:…}` markers to pandoc `[@key]` citations so --citeproc
        # renders them + emits a bibliography. Pandoc-only: docx_native has no
        # citeproc, so its markers stay literal (already warned at prepare).
        if engine == "pandoc":
            manuscript_text, _unmatched_cites = _rewrite_inline_citations(
                manuscript_text, bundle["references"],
            )
        # Resolve {fig:N}/{tab:N} inline refs to text on ALL engines — else the
        # literal tokens leak into the exported file (dev-todo: EXP figure refs).
        manuscript_text = _rewrite_inline_ref_tokens(
            manuscript_text, number_supplementary=split_supp)
        (tmp_path / "manuscript.md").write_text(manuscript_text, encoding="utf-8")
        has_bib = bool(bundle["bibtex"].strip())
        csl_arg: str | None = None
        csl_status = "no_references"
        csl_filename: str | None = None
        # Citation style / bibliography only apply to the pandoc path.
        if has_bib and engine == "pandoc":
            (tmp_path / "references.bib").write_text(bundle["bibtex"], encoding="utf-8")
            csl_arg, csl_status, csl_filename, csl_warnings = _place_csl(
                state, tmp_path, bundle, csl_path,
            )
            export_warnings.extend(csl_warnings)

        # Download figure blobs into tmp dir (only those included in this scope)
        for fig in staged_figs:
            bp = fig.get("blob_path")
            if not bp:
                continue
            data = state.backend.get_blob(bp)
            if data is None:
                continue
            local_name = pathlib.Path(bp).name
            (tmp_path / local_name).write_bytes(data)

        tmp_output = tmp_path / out.name
        docx_hancom_fix = "none"

        if engine == "docx_native":
            # python-docx writes a native package Hancom opens cleanly, so no
            # OOXML normalization is needed. Figure embeds resolve against the
            # staged blobs in tmp_path.
            _docx_export.render_markdown_to_docx(
                manuscript_text, tmp_output, asset_dir=tmp_path,
                page_size=page_size,
            )
            docx_hancom_fix = "native_python_docx"
            if has_bib:
                export_warnings.append(
                    "references are not auto-formatted for report/other docs "
                    "(python-docx export has no citeproc) — add a manual "
                    "references section if needed"
                )
        else:
            # Run pandoc; it writes the output file inside tmp dir, we copy out.
            args = _format_pandoc_args(
                fmt, "manuscript.md", out.name,
                has_bib=has_bib, csl_path=csl_arg,
            )
            rc, stdout, stderr = state.require_pandoc().run(args, cwd=str(tmp_path))
            if rc != 0:
                return {
                    "error": f"pandoc failed (rc={rc}): {stderr.strip()}",
                    "warnings": export_warnings,
                }
            if not tmp_output.is_file():
                return {
                    "error": "pandoc reported success but produced no output file",
                    "warnings": export_warnings,
                }

            # Swap the base font to Times New Roman / 1.15 line spacing in
            # place — AFTER pandoc, so its "Table" style (borders/shading) and
            # all other style mappings are preserved (a --reference-doc would
            # have dropped pandoc's table style). Non-fatal.
            if fmt == "docx":
                try:
                    _docx_export.apply_base_font_to_docx(
                        tmp_output, page_size=page_size)
                except Exception as e:
                    export_warnings.append(f"export font swap skipped: {e!s}")

            # Make the .docx open in Hancom Office (dev-todo P0-1): prefer a
            # LibreOffice round-trip (normalizes the whole OOXML package); fall
            # back to stripping the known-problem empty parts when soffice is
            # unavailable. Done before we copy/upload.
            if fmt == "docx":
                if _normalize_docx_via_soffice(tmp_output):
                    docx_hancom_fix = "soffice"
                elif _strip_problem_docx_parts(tmp_output):
                    docx_hancom_fix = "stripped_parts"

        # Copy to the user-specified path
        shutil.copy2(tmp_output, out)
        output_bytes = tmp_output.read_bytes()

    blob_path: str | None = None
    if upload_to_storage:
        blob_path = state.project_path("papers", slug, "exports", out.name)
        state.backend.put_blob(blob_path, output_bytes)
        # Also record an exports doc so the dashboard can list past exports
        doc_path = state.project_path("papers", slug, "exports", out.name)
        # We're storing the export-doc at the same key as the blob — that's fine
        # because docs and blobs have separate stores. Add metadata fields.
        existing = state.backend.get_doc(doc_path)
        meta = {
            "filename": out.name,
            "format": fmt,
            "scope": scope,
            "blob_path": blob_path,
            "size_bytes": len(output_bytes),
            "csl_filename": csl_filename,
            "csl_status": csl_status,
            "updated_at": now_iso(),
        }
        if existing is None:
            meta["created_at"] = meta["updated_at"]
            state.backend.set_doc(doc_path, meta)
        else:
            state.backend.update_doc(doc_path, meta)

    return {
        "slug": slug,
        "format": fmt,
        "scope": scope,
        "doc_type": doc_type,
        "engine": engine,
        "page_size": page_size if fmt == "docx" else None,
        "local_path": str(out),
        "blob_path": blob_path,
        "size_bytes": len(output_bytes),
        "csl_filename": csl_filename,
        "csl_status": csl_status,
        "docx_hancom_fix": docx_hancom_fix,
        "warnings": export_warnings,
        "placeholders": bundle["placeholders"],
        "unresolved_citations": bundle["unresolved_citations"],
        "dashboard_url": state.dashboard_url("papers", slug),
    }


def attach_export(
    state: State,
    slug: str,
    *,
    local_path: str,
    filename: str | None = None,
    scope: str = "supplementary",
) -> dict:
    """Upload an arbitrary file (CSV / XLSX / TSV / ZIP / …) to a paper's
    Exports area so it shows in the dashboard Exports tab next to the rendered
    .docx/.pdf and ships as part of the submission package.

    Use this for generated submission OUTPUTS that aren't pandoc-rendered —
    e.g. a large numeric supplementary table best delivered as a data file
    rather than a 200-row Word table. (For source/reference INPUTS use
    add_material instead — that's the Materials tab.)

    `scope` tags the file main | supplementary | all (default supplementary).
    """
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    scope = (scope or "supplementary").lower()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}; choose from {_VALID_SCOPES}")
    src = pathlib.Path(local_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(local_path)

    name = (filename or src.name).strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError(f"invalid export filename: {name!r}")
    data = src.read_bytes()
    fmt = (src.suffix.lstrip(".") or "data").lower()
    blob_path = state.project_path("papers", slug, "exports", name)
    state.backend.put_blob(blob_path, data)

    now = now_iso()
    meta = {
        "filename": name,
        "format": fmt,
        "scope": scope,
        "kind": "data",          # distinguishes an attached file from a render
        "blob_path": blob_path,
        "size_bytes": len(data),
        "updated_at": now,
    }
    existing = state.backend.get_doc(blob_path)
    if existing is None:
        meta["created_at"] = now
        state.backend.set_doc(blob_path, meta)
    else:
        state.backend.update_doc(blob_path, meta)
    return {**meta, "dashboard_url": state.dashboard_url("papers", slug)}


def list_exports(state: State, slug: str) -> list[dict]:
    """List previously-exported files for a paper."""
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(state.project_path("papers", slug, "exports"))
    items = [data for _, data in pairs]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items


def delete_export(state: State, slug: str, filename: str) -> bool:
    """Remove an attached/exported file from a paper's Exports area (its doc +
    blob), so a stale supplementary file doesn't ship in the package. Returns
    whether it existed."""
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    name = (filename or "").strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError(f"invalid export filename: {filename!r}")
    path = state.project_path("papers", slug, "exports", name)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_blob(path)
    state.backend.delete_doc(path)
    return True


def rename_export(state: State, slug: str, filename: str, new_filename: str) -> dict:
    """Rename an attached/exported file (moves its blob + doc to the new name),
    so renaming a supplementary data file doesn't leave the old one behind.
    Returns the updated export metadata."""
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    old = (filename or "").strip()
    new = (new_filename or "").strip()
    for n in (old, new):
        if not n or "/" in n or "\\" in n:
            raise ValueError(f"invalid export filename: {n!r}")
    old_path = state.project_path("papers", slug, "exports", old)
    meta = state.backend.get_doc(old_path)
    if meta is None:
        raise NotFound(f"export not found: {old!r} for {slug!r}")
    if new == old:
        return meta
    new_path = state.project_path("papers", slug, "exports", new)
    if state.backend.get_doc(new_path) is not None:
        raise ValueError(f"export {new!r} already exists; delete it first or pick another name")
    data = state.backend.get_blob(old_path)
    if data is not None:
        state.backend.put_blob(new_path, data)
    meta = {**meta, "filename": new, "format": (new.rsplit(".", 1)[-1].lower()
            if "." in new else meta.get("format", "data")),
            "blob_path": new_path, "updated_at": now_iso()}
    state.backend.set_doc(new_path, meta)
    state.backend.delete_blob(old_path)
    state.backend.delete_doc(old_path)
    return {**meta, "dashboard_url": state.dashboard_url("papers", slug)}

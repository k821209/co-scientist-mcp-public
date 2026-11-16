"""Render a markdown manuscript to a native .docx via python-docx.

Used for non-"paper" document types (reports / other). Pandoc's OOXML output
crashes Hancom Office (한컴오피스) — see the soffice round-trip workaround in
exports.py (dev-todo P0-1). python-docx writes a plain, native package that
Hancom opens cleanly, so reports skip pandoc entirely.

Scope: full CommonMark + GFM tables (markdown-it-py "commonmark" preset with
the table rule enabled). We deliberately avoid the "gfm-like" preset because
it enables linkify, which errors without linkify-it-py installed.

Supported blocks:  headings h1-h6, paragraphs, bullet/ordered lists (nested),
                   GFM tables, blockquotes, fenced/indented code, thematic
                   breaks, images.
Supported inline:  bold, italic, inline code, links (real hyperlinks),
                   images, soft/hard breaks.

Images use the same staged-file convention as the pandoc path: a body embed
of `![alt](figure_N.png)` resolves against `asset_dir` (the export temp dir
where figure blobs were written).
"""
from __future__ import annotations

import contextvars
import re

import pathlib

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

# Page setup. python-docx's default template is US Letter with 1.25in side
# margins, and pandoc's default reference doc is Letter too — so every .docx we
# produced was Letter, whatever the document was for. A4 is the standard
# everywhere outside the US/Canada and is a hard requirement for Korean public
# documents (feedback 0e394fb76649: an RFP that specified A4), so it is the
# default here; pass page_size="letter" for the old behaviour. The narrower
# 20mm side margins also widen the text column, which is what wide tables need.
PAGE_SIZES = {
    "a4": (Mm(210), Mm(297)),
    "letter": (Inches(8.5), Inches(11)),
}
DEFAULT_PAGE_SIZE = "a4"
_MARGIN_VERTICAL = Mm(25)
_MARGIN_SIDE = Mm(20)

# Cap image width to the usable text column — 170mm on A4 with the side margins
# above, and wider still on Letter, so 6.0in fits both. Smaller images keep
# their native size.
_MAX_IMAGE_WIDTH = Inches(6.0)
_MONO_FONT = "Consolas"
_LINK_COLOR = RGBColor(0x05, 0x63, 0xC1)

# Report design template. Reports/other docs open in Hancom Office, so we pick a
# CJK-safe default font and style headings/tables for a polished, readable look.
# The East Asian face drives Hangul glyphs; the Latin face drives ASCII.
_BODY_FONT_EASTASIA = "맑은 고딕"          # Malgun Gothic — ships with Korean Windows/Hancom
_BODY_FONT_LATIN = "Times New Roman"        # default export body face (Latin/ASCII)
_BODY_FONT_SIZE = Pt(10.5)
_BODY_LINE_SPACING = 1.15
_HEADING_COLOR = RGBColor(0x1F, 0x38, 0x64)  # deep navy — reads as a section title
# Built-in table style confirmed present in python-docx's default template;
# gives header shading + banded rows out of the box.
_TABLE_STYLE = "Light Grid Accent 1"
# (level, size pt, space-before pt, space-after pt)
_HEADING_SPECS = [(1, 16, 12, 6), (2, 13, 10, 4), (3, 11.5, 8, 3)]


def validate_page_size(page_size: str | None) -> str:
    """Normalize a page-size name, raising on anything unknown.

    Deliberately strict: silently falling back to a default would let a typo
    ("A-4") ship a Letter document to a submission that requires A4, with
    nothing in the reply to show it happened.
    """
    key = (page_size or DEFAULT_PAGE_SIZE).strip().lower()
    if key not in PAGE_SIZES:
        raise ValueError(
            f"unknown page_size {page_size!r}; choose from {sorted(PAGE_SIZES)}")
    return key


def apply_page_setup(doc, page_size: str = DEFAULT_PAGE_SIZE) -> None:
    """Set every section's paper size and margins."""
    width, height = PAGE_SIZES[validate_page_size(page_size)]
    for section in doc.sections:
        section.page_width = width
        section.page_height = height
        section.top_margin = _MARGIN_VERTICAL
        section.bottom_margin = _MARGIN_VERTICAL
        section.left_margin = _MARGIN_SIDE
        section.right_margin = _MARGIN_SIDE


def _set_eastasia_font(style, eastasia: str) -> None:
    """Set a style's East Asian font face via oxml.

    python-docx's `.font.name` only writes the `w:ascii`/`w:hAnsi` attributes;
    Hangul glyphs are selected by `w:eastAsia`, which has no high-level API.
    """
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), eastasia)


def _set_doc_default_font(doc, latin: str, eastasia: str) -> None:
    """Set the document-wide default run font (`w:docDefaults`), so EVERY
    style/paragraph that doesn't override it inherits this face. This is the
    most reliable way to force a base font across a whole docx (incl. one
    pandoc generates from this file as its `--reference-doc`)."""
    styles_el = doc.styles.element
    docDefaults = styles_el.find(qn("w:docDefaults"))
    if docDefaults is None:
        docDefaults = styles_el.makeelement(qn("w:docDefaults"), {})
        styles_el.insert(0, docDefaults)
    rPrDefault = docDefaults.find(qn("w:rPrDefault"))
    if rPrDefault is None:
        rPrDefault = docDefaults.makeelement(qn("w:rPrDefault"), {})
        docDefaults.append(rPrDefault)
    rPr = rPrDefault.find(qn("w:rPr"))
    if rPr is None:
        rPr = rPrDefault.makeelement(qn("w:rPr"), {})
        rPrDefault.append(rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), latin)
    rFonts.set(qn("w:eastAsia"), eastasia)


def apply_base_font_to_docx(path, *, page_size: str = DEFAULT_PAGE_SIZE) -> None:
    """Swap an existing .docx's base font to the export font (Times New Roman)
    at 1.15 line spacing, WITHOUT touching any other style — so a pandoc-
    generated doc keeps its "Table" style (borders/shading), headings, etc.,
    and only the default typeface changes. Sets the document-wide default font
    (so table cells + body inherit it) plus the Normal style's font + spacing.

    Also applies the page setup, so the pandoc and native paths cannot drift to
    different paper sizes.
    """
    doc = Document(str(path))
    apply_page_setup(doc, page_size)
    _set_doc_default_font(doc, _BODY_FONT_LATIN, _BODY_FONT_EASTASIA)
    try:
        normal = doc.styles["Normal"]
        normal.font.name = _BODY_FONT_LATIN
        _set_eastasia_font(normal, _BODY_FONT_EASTASIA)
        normal.paragraph_format.line_spacing = _BODY_LINE_SPACING
    except KeyError:
        pass
    # Pandoc's figure-caption styles default to italic; drop it so captions
    # read as regular text (the bold "Figure N." label comes from the alt
    # markdown, and any genuine *italics* keep their direct run formatting).
    for style_name in ("Image Caption", "Caption"):
        try:
            doc.styles[style_name].font.italic = False
        except KeyError:
            pass
    doc.save(str(path))


def _apply_report_template(doc) -> None:
    """Style the document's Normal + Heading styles for report/other exports.

    Sets a CJK-friendly body font (Latin + East Asian faces), comfortable body
    size with relaxed line spacing, and navy headings with breathing room. All
    block renderers inherit from these styles, so this colors the whole doc.
    """
    normal = doc.styles["Normal"]
    normal.font.name = _BODY_FONT_LATIN
    normal.font.size = _BODY_FONT_SIZE
    _set_eastasia_font(normal, _BODY_FONT_EASTASIA)
    pf = normal.paragraph_format
    pf.line_spacing = _BODY_LINE_SPACING
    pf.space_after = Pt(6)

    for level, size, before, after in _HEADING_SPECS:
        style = doc.styles[f"Heading {level}"]
        style.font.name = _BODY_FONT_LATIN
        style.font.size = Pt(size)
        style.font.color.rgb = _HEADING_COLOR
        _set_eastasia_font(style, _BODY_FONT_EASTASIA)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)


def _md() -> MarkdownIt:
    # "commonmark" + table only — NOT "gfm-like" (that enables linkify, which
    # raises ModuleNotFoundError without linkify-it-py).
    return MarkdownIt("commonmark").enable("table")


def _add_hyperlink(paragraph, url: str, runs_spec: list[tuple[str, bool, bool, bool]]):
    """Append a real Word hyperlink to `paragraph`.

    python-docx has no hyperlink API, so we build the `<w:hyperlink>` element
    by hand: register the URL as an external relationship, then nest styled
    runs inside the hyperlink wrapper. `runs_spec` is a list of
    (text, bold, italic, code) tuples so a link can carry mixed formatting.
    """
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = paragraph._p.makeelement(qn("w:hyperlink"), {qn("r:id"): r_id})
    for text, bold, italic, code in runs_spec:
        r = paragraph._p.makeelement(qn("w:r"), {})
        rpr = r.makeelement(qn("w:rPr"), {})
        # Hyperlink-blue + underline so it reads as a link in any viewer.
        color = rpr.makeelement(qn("w:color"), {qn("w:val"): "0563C1"})
        rpr.append(color)
        u = rpr.makeelement(qn("w:u"), {qn("w:val"): "single"})
        rpr.append(u)
        if bold:
            rpr.append(rpr.makeelement(qn("w:b"), {}))
        if italic:
            rpr.append(rpr.makeelement(qn("w:i"), {}))
        if code:
            rfonts = rpr.makeelement(qn("w:rFonts"), {qn("w:ascii"): _MONO_FONT,
                                                      qn("w:hAnsi"): _MONO_FONT})
            rpr.append(rfonts)
        r.append(rpr)
        t = r.makeelement(qn("w:t"), {qn("xml:space"): "preserve"})
        t.text = text
        r.append(t)
        hyperlink.append(r)
    paragraph._p.append(hyperlink)


def _styled_run(paragraph, text: str, *, bold: bool, italic: bool, code: bool):
    run = paragraph.add_run(text)
    run.bold = bold or None
    run.italic = italic or None
    if code:
        run.font.name = _MONO_FONT
    return run


def _add_image(paragraph, path: pathlib.Path, alt: str | None = None):
    run = paragraph.add_run()
    shape = run.add_picture(str(path))
    if shape.width > _MAX_IMAGE_WIDTH:
        ratio = _MAX_IMAGE_WIDTH / shape.width
        shape.width = _MAX_IMAGE_WIDTH
        shape.height = int(shape.height * ratio)
    if alt:
        # Word's "Alt Text" field, which is what a journal's alt-text
        # requirement means and what a screen reader reads. Distinct from the
        # caption paragraph below the image: the caption is read BESIDE the
        # figure by someone who can see it, the alt text REPLACES it.
        shape._inline.docPr.set("descr", alt)
    return run


# An image attribute block, pandoc's `![caption](f.png){alt="…"}` syntax. The
# markdown-it parser here is commonmark, which has no notion of it: the braces
# come out as literal text in the document AND the caption vanishes, because
# the paragraph is no longer a lone image. So the attribute is lifted out of
# the source before parsing, and applied where it belongs.
_IMAGE_ALT_ATTR = re.compile(
    r'(?P<image>!\[[^\]]*\]\((?P<src>[^)\s]+)\))\{\s*alt="(?P<alt>[^"]*)"\s*\}')


def _lift_image_alts(markdown_text: str) -> tuple[str, dict[str, str]]:
    """Strip `{alt="…"}` blocks, returning the text and src → alt text."""
    alts: dict[str, str] = {}

    def swap(m: re.Match) -> str:
        alts[m.group("src")] = m.group("alt")
        return m.group("image")

    return _IMAGE_ALT_ATTR.sub(swap, markdown_text), alts


_IMAGE_ALTS: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "docx_image_alts", default=None)


def _alt_for(src: str) -> str | None:
    return (_IMAGE_ALTS.get() or {}).get(src)


def _fix_drawing_ids(doc) -> None:
    """Give every embedded drawing a unique, non-zero visual id.

    python-docx hardcodes each picture's `pic:cNvPr id="0"`. Word and
    LibreOffice tolerate the zero id, but Hancom Office (한컴오피스) refuses to
    draw a picture whose visual id is 0 — it shows a broken-image box even
    though the package is valid (EXP-2). Renumber both `wp:docPr` and
    `pic:cNvPr` across the document to unique ids starting at 1.
    """
    n = 0
    for el in doc.element.iter():
        tag = el.tag
        if tag.endswith("}docPr") or tag.endswith("}cNvPr"):
            n += 1
            el.set("id", str(n))


# Raw HTML in the markdown. CommonMark lets it through as html_inline /
# html_block tokens, and this renderer used to handle neither — so a `<br>` in
# a table cell, the one idiom markdown has for a line break inside a cell,
# vanished without a trace: not a break, not the literal text, nothing
# (feedback a22db828faa3: 433 cells, zero breaks, items run together). `<br>`
# is now a break. Every other tag is still not rendered, but it is COUNTED, and
# the export reports what it dropped instead of leaving the discovery to
# whoever opens the file.
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_NAME_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9-]*)")
_DROPPED_HTML: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "docx_dropped_html", default=None)


def _drop_html(fragment: str) -> None:
    counts = _DROPPED_HTML.get()
    if counts is None:
        return
    m = _TAG_NAME_RE.search(fragment)
    name = f"<{m.group(1).lower()}>" if m else fragment.strip()[:20]
    counts[name] = counts.get(name, 0) + 1


def _collect_inline_runs(
    node: SyntaxTreeNode, bold: bool, italic: bool, code: bool
) -> list[tuple[str, bool, bool, bool]]:
    """Flatten an inline subtree into (text, bold, italic, code) run specs.

    Used for link contents, where everything must live inside the single
    `<w:hyperlink>` wrapper rather than as sibling paragraph runs.
    """
    out: list[tuple[str, bool, bool, bool]] = []
    for child in node.children:
        if child.type == "text":
            out.append((child.content, bold, italic, code))
        elif child.type == "code_inline":
            out.append((child.content, bold, italic, True))
        elif child.type == "strong":
            out.extend(_collect_inline_runs(child, True, italic, code))
        elif child.type == "em":
            out.extend(_collect_inline_runs(child, bold, True, code))
        elif child.type in ("softbreak", "hardbreak"):
            out.append((" ", bold, italic, code))
        elif child.type == "html_inline":
            # Inside a hyperlink a break cannot be represented; a space keeps
            # the words apart. Anything else is dropped and counted.
            if _BR_RE.fullmatch(child.content.strip()):
                out.append((" ", bold, italic, code))
            else:
                _drop_html(child.content)
        else:
            out.extend(_collect_inline_runs(child, bold, italic, code))
    return out


def _render_inline(
    paragraph, node: SyntaxTreeNode, asset_dir: pathlib.Path | None,
    *, bold: bool = False, italic: bool = False, code: bool = False,
):
    """Render an inline node's children into runs on `paragraph`."""
    for child in node.children:
        t = child.type
        if t == "text":
            _styled_run(paragraph, child.content, bold=bold, italic=italic, code=code)
        elif t == "code_inline":
            _styled_run(paragraph, child.content, bold=bold, italic=italic, code=True)
        elif t == "strong":
            _render_inline(paragraph, child, asset_dir, bold=True, italic=italic, code=code)
        elif t == "em":
            _render_inline(paragraph, child, asset_dir, bold=bold, italic=True, code=code)
        elif t == "link":
            url = child.attrs.get("href", "")
            runs = _collect_inline_runs(child, bold, italic, code)
            if url and runs:
                _add_hyperlink(paragraph, str(url), runs)
            else:
                _render_inline(paragraph, child, asset_dir, bold=bold, italic=italic, code=code)
        elif t == "image":
            src = str(child.attrs.get("src", ""))
            resolved = _resolve_image(src, asset_dir)
            if resolved is not None:
                _add_image(paragraph, resolved)
            else:
                # Unresolved image → fall back to its alt text as plain run.
                alt = child.content or src
                if alt:
                    _styled_run(paragraph, alt, bold=bold, italic=italic, code=code)
        elif t == "softbreak":
            _styled_run(paragraph, " ", bold=bold, italic=italic, code=code)
        elif t == "hardbreak":
            paragraph.add_run().add_break()
        elif t == "html_inline":
            if _BR_RE.fullmatch(child.content.strip()):
                paragraph.add_run().add_break()   # same as a markdown hard break
            else:
                _drop_html(child.content)


def _resolve_image(src: str, asset_dir: pathlib.Path | None) -> pathlib.Path | None:
    """Resolve an image src to a local file, if it points at a staged asset.

    Only local basenames staged in `asset_dir` are embedded; remote URLs and
    missing files return None so the caller can fall back to alt text.
    """
    if not src or asset_dir is None:
        return None
    if "://" in src:  # remote URL — python-docx can't fetch it
        return None
    candidate = asset_dir / pathlib.Path(src).name
    return candidate if candidate.is_file() else None


def _render_block(doc, node: SyntaxTreeNode, asset_dir: pathlib.Path | None,
                  list_level: int = 0):
    """Render a single block-level node into the document."""
    t = node.type
    if t == "heading":
        level = int(node.tag[1])  # h1..h6 → 1..6
        heading = doc.add_heading(level=min(level, 6))
        inline = node.children[0] if node.children else None
        if inline is not None:
            _render_inline(heading, inline, asset_dir)
    elif t == "paragraph":
        inline = node.children[0] if node.children else None
        # A paragraph that is a single image becomes a centered figure with a
        # caption underneath (the image's alt text). The caption renders its
        # markdown — so a "**Figure N.**" label is bold and the rest regular,
        # while genuine *italics* (e.g. species names) are preserved — instead
        # of force-italicizing the whole line.
        if inline is not None and _is_lone_image(inline):
            img = inline.children[0]
            resolved = _resolve_image(str(img.attrs.get("src", "")), asset_dir)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if resolved is not None:
                _add_image(p, resolved,
                           alt=_alt_for(str(img.attrs.get("src", ""))))
                caption = img.content or img.attrs.get("alt") or ""
                if caption:
                    cap = doc.add_paragraph()
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if img.children:
                        _render_inline(cap, img, asset_dir)
                    else:
                        cap.add_run(caption)
                    for run in cap.runs:
                        run.font.size = Pt(9)
            else:
                run = p.add_run(img.content or str(img.attrs.get("src", "")))
                run.italic = True
            return
        p = doc.add_paragraph()
        if inline is not None:
            _render_inline(p, inline, asset_dir)
    elif t in ("bullet_list", "ordered_list"):
        style = "List Bullet" if t == "bullet_list" else "List Number"
        if list_level > 0:
            style = f"{style} {min(list_level + 1, 3)}"
        num_id = None
        if t == "ordered_list":
            num_id = _own_numbering(doc, style, _list_start(node))
        for item in node.children:
            if item.type != "list_item":
                continue
            _render_list_item(doc, item, asset_dir, style, list_level, num_id)
    elif t == "blockquote":
        for child in node.children:
            if child.type == "paragraph":
                inline = child.children[0] if child.children else None
                p = doc.add_paragraph(style="Quote")
                if inline is not None:
                    _render_inline(p, inline, asset_dir)
            else:
                _render_block(doc, child, asset_dir, list_level)
    elif t in ("code_block", "fence"):
        p = doc.add_paragraph()
        run = p.add_run(node.content.rstrip("\n"))
        run.font.name = _MONO_FONT
        run.font.size = Pt(9)
    elif t == "hr":
        doc.add_paragraph("─" * 30).alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif t == "table":
        _render_table(doc, node, asset_dir)
    elif t == "html_block":
        _drop_html(node.content)


def _is_lone_image(inline: SyntaxTreeNode) -> bool:
    kids = [c for c in inline.children if c.type != "softbreak"]
    return len(kids) == 1 and kids[0].type == "image"


def _list_start(node: SyntaxTreeNode) -> int:
    """The number an ordered list opens with. Markdown records it only when it
    is not 1 ("4. …" continues a list a paragraph interrupted)."""
    try:
        return max(0, int(node.attrs.get("start", 1)))
    except (TypeError, ValueError):
        return 1


def _own_numbering(doc, style: str, start: int = 1) -> int | None:
    """A numbering instance for ONE ordered list, counting from `start`.

    The "List Number" style carries a single numbering instance, so every
    numbered paragraph in the document belonged to one list: a second list
    went on from where the first stopped, and a generated References list
    behind three numbered plans opened at 4 while the body cited [1]–[9]
    (feedback 863dd830e427 — nothing warned, the file looked fine). A second
    instance of the same definition is not enough: Word keeps counting across
    instances that share one, and restarts only on an explicit start override,
    which is also what it writes for "Restart at 1".

    Returns None when the style has no numbering to copy — the caller then
    leaves the paragraph to its style, as before.
    """
    try:
        num_pr = doc.styles[style].element.pPr.numPr
        base = num_pr.numId.val
        numbering = doc.part.numbering_part.element
        abstract = numbering.num_having_numId(base).abstractNumId.val
    except (AttributeError, KeyError):
        return None
    num = numbering.add_num(abstract)
    num.add_lvlOverride(ilvl=0).add_startOverride(start)
    return num.numId


def _number_paragraph(paragraph, num_id: int) -> None:
    num_pr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    num_pr.get_or_add_ilvl().val = 0
    num_pr.get_or_add_numId().val = num_id


def _continuation_style(style: str) -> str:
    """The style of an item's SECOND paragraph: indented like the item, with no
    marker. Given the list style again, it drew a marker of its own — a second
    number on an ordered item, so the list ran one ahead from there on."""
    depth = style.rsplit(" ", 1)[-1]
    return f"List Continue {depth}" if depth in ("2", "3") else "List Continue"


def _render_list_item(doc, item: SyntaxTreeNode, asset_dir, style: str,
                      list_level: int, num_id: int | None = None):
    opened = False
    for child in item.children:
        if child.type == "paragraph":
            inline = child.children[0] if child.children else None
            if opened:
                p = doc.add_paragraph(style=_continuation_style(style))
            else:
                p = doc.add_paragraph(style=style)
                if num_id is not None:
                    _number_paragraph(p, num_id)
                opened = True
            if inline is not None:
                _render_inline(p, inline, asset_dir)
        elif child.type in ("bullet_list", "ordered_list"):
            _render_block(doc, child, asset_dir, list_level + 1)
        else:
            _render_block(doc, child, asset_dir, list_level)


def _set_table_look(table, *, header: bool, banded_rows: bool) -> None:
    """Set the table's `<w:tblLook>` so the style's conditional formatting
    (header shading, row banding) actually renders. python-docx exposes no
    high-level API for this, so we write the element attributes directly.
    """
    tbl_pr = table._tbl.tblPr
    look = tbl_pr.find(qn("w:tblLook"))
    if look is None:
        look = tbl_pr.makeelement(qn("w:tblLook"), {})
        tbl_pr.append(look)
    look.set(qn("w:firstRow"), "1" if header else "0")
    look.set(qn("w:lastRow"), "0")
    look.set(qn("w:firstColumn"), "0")
    look.set(qn("w:lastColumn"), "0")
    look.set(qn("w:noHBand"), "0" if banded_rows else "1")
    look.set(qn("w:noVBand"), "1")


def _set_table_borders(table, *, size: int = 4, color: str = "000000") -> None:
    """Force explicit borders on ALL edges + inside gridlines via direct
    `<w:tblBorders>` formatting. The named table style ("Light Grid Accent 1")
    defines borders, but some viewers (notably Hancom / 한컴오피스) drop the
    OUTER top + bottom rules when they come only from the style — so we draw
    them directly. `size` is in eighths of a point (4 = 0.5pt)."""
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = tbl_pr.makeelement(qn("w:tblBorders"), {})
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = borders.makeelement(qn(f"w:{edge}"), {})
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)


# ── column widths ────────────────────────────────────────────────────────────
#
# A table was laid out with every column the same width, whatever was in it:
# a three-column list of files gave "10", "11", "2" the same 57 mm as the file
# names, and a name wider than that was cut in the middle of a word —
# "lettuce_annotation_1.zi / p" — which the recipient cannot copy (feedback
# c4b78b6d923c). There was room; it was in the wrong column.
#
# So each column gets at least the width of its longest piece that cannot be
# broken, and what is left of the text column is shared by how much each
# column has to say. Widths are estimated from character counts — there is no
# layout engine here — with the three faces the template uses.

_SQUEEZED: contextvars.ContextVar[list | None] = contextvars.ContextVar("squeezed", default=None)
_PT = 12700                                   # EMU per point
_CELL_PADDING_PT = 14.0                       # Word's default cell margins, and the rules
_CJK = re.compile(r"[\u1100-\u11ff\u2e80-\u9fff\uac00-\ud7a3\uf900-\ufaff\uff00-\uffef]")
_CELL_BREAK = re.compile(r"<br\s*/?>", re.I)


def _segments(raw: str) -> list[tuple[str, bool]]:
    """(text, is_code) pieces of a cell's markdown: backticks switch the face,
    emphasis marks print nothing."""
    out: list[tuple[str, bool]] = []
    for index, piece in enumerate((raw or "").split("`")):
        code = index % 2 == 1
        out.append((piece if code else re.sub(r"\*\*|__|(?<!\w)[*_]|[*_](?!\w)", "", piece), code))
    return out


def _char_pt(char: str, code: bool, bold: bool) -> float:
    if _CJK.match(char):
        return _BODY_FONT_SIZE.pt * (1.0 if not code else 0.9)
    if code:
        return 9.0 * 0.55                       # the mono face, at the size inline code is set
    return _BODY_FONT_SIZE.pt * (0.56 if bold else 0.52)


def _cell_needs(raw: str, *, bold: bool, whole_words: bool = False) -> tuple[float, float]:
    """(the widest piece that cannot be broken, the widest line) of one cell, in points.

    A line breaks at a space and between two CJK characters, and nowhere inside
    a run of anything else: a file name, a number with its unit, an identifier.
    `whole_words` keeps a CJK word together as well — for the header row, where
    "내용" set as 내 / 용 over a narrow column is what a reader sees first.
    """
    unbreakable = widest = 0.0
    for line in _CELL_BREAK.split(raw or ""):
        line_pt = run_pt = 0.0
        for text, code in _segments(line):
            for char in text:
                width = _char_pt(char, code, bold)
                line_pt += width
                if char.isspace():
                    run_pt = 0.0
                elif _CJK.match(char) and not whole_words:
                    unbreakable = max(unbreakable, width)
                    run_pt = 0.0
                else:
                    run_pt += width
                    unbreakable = max(unbreakable, run_pt)
        widest = max(widest, line_pt)
    return unbreakable, widest


def column_widths(cells: list[list[str]], available_pt: float) -> tuple[list[float], dict | None]:
    """Widths in points for a table whose cells hold this markdown, and — when
    even the unbreakable pieces do not fit the text column — what was needed.

    Every column first gets its longest unbreakable piece. What is left goes
    to the columns whose lines would otherwise WRAP, up to their widest line —
    a column that already holds its longest content on one line needs no more.
    Anything still left is shared by content, so the table spans the text
    column as it did.
    """
    ncols = max((len(row) for row in cells), default=0)
    if not ncols:
        return [], None
    least = [0.0] * ncols
    widest = [0.0] * ncols
    for ri, row in enumerate(cells):
        for ci in range(ncols):
            # The first column is measured as bold as well as the header: the
            # table style sets it so in LibreOffice whatever tblLook says, and a
            # width that is right for the regular face cuts the bold one.
            unbreakable, line = _cell_needs(row[ci] if ci < len(row) else "",
                                            bold=ri == 0 or ci == 0, whole_words=ri == 0)
            least[ci] = max(least[ci], unbreakable + _CELL_PADDING_PT)
            widest[ci] = max(widest[ci], line + _CELL_PADDING_PT)
    need = sum(least)
    if need > available_pt:
        # It cannot fit: something will still be cut. Shrunk in proportion, and
        # SAID — a table that quietly cuts a file name is the report.
        scale = available_pt / need
        return [w * scale for w in least], {"columns": ncols, "needs_pt": round(need, 1),
                                            "has_pt": round(available_pt, 1)}
    spare = available_pt - need
    wants = [max(widest[ci] - least[ci], 0.0) for ci in range(ncols)]
    wanted = sum(wants)
    if wanted >= spare:
        # Not every line fits. The columns that want least are satisfied first
        # — a label or a number stays on one line — and the long column takes
        # what is left and wraps: sharing in proportion instead set "항목 10"
        # on two lines to give a paragraph a few more points.
        out = list(least)
        left = spare
        order = sorted(range(ncols), key=lambda ci: wants[ci])
        for position, ci in enumerate(order):
            share = left / (ncols - position)
            given = min(wants[ci], share)
            out[ci] += given
            left -= given
        return out, None
    left = spare - wanted
    total = sum(widest) or 1.0
    return [widest[ci] + left * widest[ci] / total for ci in range(ncols)], None


def _apply_column_widths(table, widths_pt: list[float]) -> None:
    """Fixed layout, with the width on the grid AND on every cell: Word reads
    the cells, LibreOffice the grid, and a width set on only one of them is
    ignored by the other."""
    table.autofit = False
    for ci, width in enumerate(widths_pt):
        emu = int(width * _PT)
        table.columns[ci].width = emu
        for row in table.rows:
            row.cells[ci].width = emu


def _keep_rows_whole(table) -> None:
    """A row that splits across a page leaves a line of empty boxes at the top
    of the next one, which reads as missing data. `cantSplit` is ignored only
    for a row taller than a page."""
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(tr_pr.makeelement(qn("w:cantSplit"), {}))


def _render_table(doc, node: SyntaxTreeNode, asset_dir):
    rows: list[list[SyntaxTreeNode]] = []
    for section in node.children:  # thead / tbody
        for tr in section.children:
            if tr.type == "tr":
                rows.append([c for c in tr.children if c.type in ("th", "td")])
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    table.style = _TABLE_STYLE
    # Turn on the style's conditional formatting: header-row + banded rows,
    # no first/last-column emphasis (so data columns read evenly). Without a
    # `<w:tblLook>` the banding/header shading don't render in some viewers.
    _set_table_look(table, header=True, banded_rows=True)
    # Draw all borders explicitly so the outer top + bottom rules always render
    # (the style alone drops them in Hancom / some viewers).
    _set_table_borders(table)
    for ri, cells in enumerate(rows):
        for ci in range(ncols):
            cell = table.cell(ri, ci)
            cell.paragraphs[0].text = ""  # clear default empty run
            if ci < len(cells):
                inline = cells[ci].children[0] if cells[ci].children else None
                if inline is not None:
                    _render_inline(cell.paragraphs[0], inline, asset_dir)
            if ri == 0:  # bold header row
                for run in cell.paragraphs[0].runs:
                    run.bold = True
    section = doc.sections[-1]
    available_pt = (section.page_width - section.left_margin - section.right_margin) / _PT
    raw = [[(cell.children[0].content if cell.children else "") for cell in cells]
           for cells in rows]
    widths, squeezed = column_widths(raw, available_pt)
    _apply_column_widths(table, widths)
    _keep_rows_whole(table)
    if squeezed is not None:
        noted = _SQUEEZED.get()
        if noted is not None:
            noted.append({**squeezed, "first_cell": (raw[0][0] if raw and raw[0] else "")[:40]})


def render_markdown_to_docx(
    markdown_text: str,
    output_path: str | pathlib.Path,
    *,
    asset_dir: str | pathlib.Path | None = None,
    page_size: str = DEFAULT_PAGE_SIZE,
    diagnostics: dict | None = None,
) -> pathlib.Path:
    """Render `markdown_text` to a .docx at `output_path`.

    `asset_dir` is the directory holding staged image files (figure_N.png);
    body image embeds resolve against it. Returns the written path.

    `diagnostics`, if given, receives what the renderer could not render:
    `dropped_html` = {"<span>": 3, …} — every raw HTML tag other than `<br>`;
    `tables_squeezed` = the tables whose columns could not all be given their
    longest unbreakable piece, where something is therefore still cut.
    Nothing here raises for those; the caller decides whether to warn.
    """
    out = pathlib.Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    assets = pathlib.Path(asset_dir).expanduser() if asset_dir else None

    body, image_alts = _lift_image_alts(markdown_text)
    tokens = _md().parse(body)
    root = SyntaxTreeNode(tokens)

    dropped: dict[str, int] = {}
    squeezed: list[dict] = []
    squeezed_token = _SQUEEZED.set(squeezed)
    token = _DROPPED_HTML.set(dropped)
    alt_token = _IMAGE_ALTS.set(image_alts)
    try:
        doc = Document()
        apply_page_setup(doc, page_size)
        _apply_report_template(doc)
        for node in root.children:
            _render_block(doc, node, assets)
    finally:
        _DROPPED_HTML.reset(token)
        _IMAGE_ALTS.reset(alt_token)
        _SQUEEZED.reset(squeezed_token)
    _fix_drawing_ids(doc)  # non-zero visual ids so Hancom renders images (EXP-2)
    doc.save(str(out))
    if diagnostics is not None:
        diagnostics["dropped_html"] = dropped
        # Tables whose unbreakable pieces are wider than the text column.
        diagnostics["tables_squeezed"] = squeezed
    return out

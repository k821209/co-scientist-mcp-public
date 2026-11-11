# `code` slides — the helper catalog

_Part of `/paper-deck`. Read from `SKILL.md` when you are about to write the first `code` snippet of a deck, and whenever you reach for a helper: every callable with its signature, the names bound when the snippet runs, the grid, the palette keys._

### 5a. `code` slides — author the slide in python-pptx (todo 002)

A slide with `render_mode="code"` carries a python-pptx **snippet** in
its `code` field. The exporter `exec`s that snippet with a prepared
namespace, and the snippet adds shapes/textboxes/images to the slide
natively. Result: editable PPTX, visually-rich layout, your design
choices.

**Quick reference — every callable at a glance** (todo 007 Tier 3).
Grep this block to find the right helper / pattern without reading
source. All signatures are *current* — legacy parameter names noted
where they still work.

```text
NAMESPACE (always bound in code snippets)
  slide, title, body, notes, row
  palette = {accent, background, foreground, surface, muted,
             secondary, highlight}    # 7 RGBColor keys, todo 007
             # `text` is accepted as an alias of `foreground` (the concept's
             # Palette block names it `text:`); both resolve to the same color.
  fonts   = {display, body, mono}
  type_scale = {legacy: title/head/body/cover_title/caption/...
                 canonical roles: display_chapter/cover/hero,
                                  headline_section, title_slide,
                                  body_large/standard/small,
                                  label_tag/caption, scale_ratio}
  aspect, sw, sh, Pt, Inches, Emu, MSO_SHAPE, PP_ALIGN, MSO_ANCHOR,
  RGBColor

HELPERS  (h.* — primitives)
  h.accent_stripe(slide, *, palette, sw)                 # top stripe
  h.title_block(slide, text, *, palette, fonts,           # themed title
                type_scale, sw, sh, cover=False,
                accent_rule=True)
  h.bullet_list(slide, items, *, palette, fonts,          # bulleted column
                type_scale, left, top, width, height,
                bullet="•")
  h.card(slide, *, left, top, width, height, title, body, # single card
         palette, fonts, type_scale, accent_top=True)
  h.card_grid(slide, items, *, left, top, width, height,  # N-card grid
              palette, fonts, type_scale, cols=2, gap_pt=12)
            # items: list[{title|tag, body|note}]
  h.pull_quote(slide, text, *, palette, fonts, type_scale, # accent bar + italic
               left, top, width, height)
               # blank line in `text` = explicit half-line gap
  h.callout(slide, *, left, top, width, fill, palette,    # filled callout —
            items=None, headline="", body="",              # auto-sizes its bg
            fonts=None, type_scale=None, pad_pt=14,        # rect to content
            gap_pt=6, min_height=None, text_color=None,    # height. Use this
            border_color=None, border_pt=0, valign="top")  # for dark/light
            # returns {box, height_used, bottom} — stack the next thing at
            # res["bottom"] (NOT `h.callout(...) + Pt(12)`: it is a dict).
            # valign="middle" when min_height equalises a row of cards.
            # `items` is a vstack-style list[{text,         # callout boxes
            # size_pt?, color?, bold?, italic?, ...}]      # instead of drawing
            # OR pass headline= / body= shortcuts.          # rect+text manually
            # text_color auto-picks foreground/surface     # (todo 014 callout-
            # by background luminance.                      # fix)
  h.text(slide, content, *, left, top, width, height,    # one-call textbox
         palette, size_pt=20, color=None, bold=False,
         italic=False, align=None, anchor=None,           # anchor=MSO_ANCHOR
         line_spacing=1.22, autofit=True, min_pt=10,      # .MIDDLE now zeroes
         fonts=None)                                      # insets → centers
  h.text_block(slide, *, lines, left, top, width, height, # FIXED box, V-CENTER
         palette, fonts=None, size_pt=14, valign="middle",# + per-line color
         align=None, mono=False, font_name=None,          # + optional fill.
         line_spacing=1.15, fill=None, pad_pt=8,          # lines: str |
         bold=False)                                      # (text,color) | dict
            # ← USE for code boxes / badges / table-like cells: filled box
            # + symmetric vertical centering + per-line color in ONE call
            # (replaces raw pptx textbox-over-rect). fill: RGBColor|palette key.
  h.vstack(slide, lines, *, left, top, width, palette,    # auto-stack lines
           fonts=None, gap_pt=4)                          # ← USE THIS when
            # lines: list[{text, size_pt?, color?, bold?,    you'd otherwise
            # italic?, font_name?, align?, line_spacing?,    call h.text twice
            # pad_top_pt?}] — auto-measures each line's     with hand-computed
            # height; returns final_y for chaining.         top values (todo
                                                            # 014 vstack-fix)
  h.icon(slide, name, *, left, top, size, palette,        # MSO_SHAPE or glyph
         color=None, fonts=None)
  h.icon_names() -> list[str]                             # vocabulary
  h.deck_chrome(slide, *, palette, fonts, type_scale,     # eyebrow + footer
                sw, sh, eyebrow="", page_number=<auto>,   # + page number
                total=<auto>, footer="")                  # page+total auto-fill
                                                          # → slide_number;
                                                          # =None hides it
                                                          # (todo 009 B)
  h.table(slide, *, headers, rows, left, top, width,      # native pptx TABLE
          height, palette, fonts, type_scale,             # height is a MINIMUM:
                                                          # a wrapping cell makes
                                                          # the table taller and it
                                                          # covers what is below
          first_col_emphasis=False,                       # header: solid bg
          header_fill=None, valign="middle")              # +auto-contrast text
  h.image_path([slide,] path, *, left, top, width,        # embed local PNG
               height, fit="contain")
  h.image_region([slide,] region_id, *, left, top, width, # row.regions[id]
                 height, fit="contain")
  h.image_figure([slide,] figure_number, *, left, top,    # paper figure
                 width, height, fit="contain")
  h.grid(*, sw, sh, cols=12, rows=6, ...) -> Grid         # design grid
       grid.cell(col, span=1, row=1, row_span=1) -> Cell  # (left,top,w,h)
                                                           # OR .left/.top/...
  h.SPACING_UNIT_PT = 8                                   # 8pt rhythm
  h.autofit_pt(text, *, max_width_emu, max_height_emu,    # Korean-aware
               start_pt, line_spacing=1.22, min_pt=10)
  h.estimate_text_width_pt(text, font_pt)

MECHANICAL LAYOUTS  (p.* — structural scaffolds ONLY; see note below)
  # These are content-NEUTRAL structural layouts that are tedious to
  # hand-roll (grids, bars, numbered cards). They do NOT frame an
  # argument. For ANY body slide that carries a thesis / evidence /
  # comparison, do NOT reach for a pattern — compose it bespoke from
  # h.* primitives (see proposal_dense / personnel_equipment exemplars).
  p.title_slide(slide, *, title, subtitle="", eyebrow="", # OWNS SLIDE
                palette, fonts, type_scale, sw, sh,
                align="auto")  # auto: left if title wraps 2+ lines, else center
  p.chapter_divider(slide, *, chapter_label, summary="",  # OWNS SLIDE
                    palette, fonts, type_scale, sw, sh)
  p.title_and_image_grid(slide, *, title, images, cols=2, # under title
                         palette, fonts, type_scale, sw, sh)
  p.figure_full(slide, *, image_path=None,                # under title
                image_callable=None, caption="",
                palette, fonts, type_scale, sw, sh)
                       # Pass ONE of image_path / image_callable.
                       # Full-grid figure + caption in bottom margin.
  p.metric_tile_row(slide, *, items=..., palette, fonts,  # under title
      type_scale, sw, sh, top=None, height=None)
                       # items: list[tuple | {value/tag, label/body, unit?}]
                       # legacy alias: tiles=
  p.flow_pipeline(slide, *, items=..., palette, fonts,    # under title
      type_scale, sw, sh)
                       # items: list[{tag, body}]
                       # legacy alias: steps=
  p.gantt_chart(slide, *, items=..., periods=None,        # under title
                period_count=None, palette, fonts,         # todo 009 D
                type_scale, sw, sh)
                       # items: list[{label, start, span}]
                       # legacy alias: activities=
```

Contract rules:
- **owns slide** patterns: do NOT call `h.accent_stripe` / `h.title_
  block` before — the pattern is the slide.
- **under title** patterns: DO call the preamble first; pattern
  content starts at `_BODY_TOP` ≈ Inches(1.85).
- Every text-emitting helper autofits Korean-aware (`h.autofit_pt`)
  so dense body content can't overflow its box (todo 005 + autofit
  follow-up).
- Every list-of-items parameter is canonically `items=`. Legacy
  names (`tiles` / `steps`) still work as aliases. Passing both
  raises `TypeError`.
- Image helpers (`h.image_*`) accept slide as the first positional
  arg OR rely on the closure-bound `slide`. Both forms work.

Why not just render the markdown `body`? Because markdown's grammar
is too thin to capture slide *design* — punchline placement, figure
position, "is this a list or a card grid", colored callouts, KPI
tiles. Trying to derive visual treatment from `>` quote vs `-` bullet
markers produces mediocre slides. You decide the design; code it.

**The namespace bound at exec time** (use these freely in `code`):

| Name | What it is |
|---|---|
| `slide` | The python-pptx `Slide` object you append shapes to |
| `title`, `body`, `notes`, `row` | The slide's stored fields (read-only inputs) |
| `palette` | `{"accent": RGBColor, "background": RGBColor, "foreground": RGBColor, "surface": RGBColor, …}` — seven keys in all, listed under "Palette has 7 keys" below |
| `fonts` | `{"display": str|None, "body": str|None, "mono": str|None}` |
| `type_scale` | `{"title": 32, "head": 26, "body": 20, "line_spacing": 1.22, "cover_title": 40, "caption": 12, ...}` |
| `aspect` | `"16:9"` / `"16:10"` / `"4:3"` |
| `sw`, `sh` | Slide width / height in EMU (use with `Inches(...)` math) |
| `Pt`, `Inches`, `Emu` | python-pptx units |
| `MSO_SHAPE`, `PP_ALIGN`, `MSO_ANCHOR`, `RGBColor` | python-pptx primitives |
| `h` (alias `helpers`) | Helper namespace (see catalog below) |

**`h.*` helper catalog** — covers the boilerplate so the snippet can
focus on actual layout:

| Helper | Signature (sw/sh/palette/fonts/type_scale are kwargs) | Purpose |
|---|---|---|
| `h.accent_stripe(slide, *, palette, sw)` | — | Top accent stripe, deck signature |
| `h.title_block(slide, text, *, palette, fonts, type_scale, sw, sh, cover=False, accent_rule=True)` | — | Themed title + short accent rule (or centered cover layout if `cover=True`) |
| `h.bullet_list(slide, items, *, palette, fonts, type_scale, left, top, width, height, bullet="•")` | items=list[str] | Vertical bulleted list inside a box |
| `h.card(slide, *, left, top, width, height, title, body, palette, fonts, type_scale, accent_top=True)` | — | One titled card: bg + accent stripe + title + body |
| `h.card_grid(slide, items, *, left, top, width, height, palette, fonts, type_scale, cols=2, gap_pt=12)` | items=list[{title, body}] | N cards in a `cols`-column grid filling a box |
| `h.pull_quote(slide, text, *, palette, fonts, type_scale, left, top, width, height)` | — | Vertical accent bar + italic body — for a punchline |
| `h.image_path([slide,] path, *, left, top, width, height, fit="contain")` | slide optional | Embed an image from a filesystem path. `slide` is optional (falls back to the snippet's bound slide); pass it explicitly for consistency with other helpers. |
| `h.image_region([slide,] region_id, *, left, top, width, height, fit="contain")` | slide optional | Resolve `row.regions[id]` → embed that image. |
| `h.image_figure([slide,] figure_number, *, left, top, width, height, fit="contain")` | slide optional | Resolve a paper figure → embed. |
| `h.text(slide, content, *, left, top, width, height, palette, size_pt=20, color=None, font_name=None, bold=False, italic=False, align=None, anchor=None, line_spacing=1.22, autofit=True, min_pt=10, fonts=None)` | one-call textbox | DX helper: drops the 5-line `add_textbox + text_frame + paragraph + run + font` ceremony to a single call. `color` defaults to `palette["foreground"]`; pass `palette["muted"]` for captions, `palette["accent"]` for emphasis. Autofit-shrinks Korean-aware. `anchor=MSO_ANCHOR.MIDDLE`/`.BOTTOM` zeroes the top/bottom insets so centered text is symmetric. (todo 007 §D) |
| `h.text_block(slide, *, lines, left, top, width, height, palette, fonts=None, size_pt=14, valign="middle", align=None, mono=False, font_name=None, line_spacing=1.15, fill=None, pad_pt=8, bold=False)` | `lines`: list of `str` \| `(text, color)` \| `{text, color?, bold?, size_pt?, align?, font_name?, line_spacing?}` | Multi-line text in a **fixed** box, vertically centered, with optional per-line color and an optional solid `fill` (RGBColor or palette key). When `fill` is set the text lives in that rect's own frame so box + text can't drift. Insets zeroed for symmetric centering. `mono=True` → monospace (default `Consolas`). Use for code boxes / badges / table-like cells instead of overlaying a raw textbox on a rectangle. Unlike `h.vstack`/`h.callout` it does **not** auto-size — keeps the box you pass. (todo text-block) |
| `h.grid(*, sw, sh, cols=12, rows=6, gutter=Pt(8), margin_x=Inches(0.6), margin_top=Inches(1.8), margin_bot=Inches(0.6), row_gap=Pt(8), row_h=None)` | — | Build a 12-col × 6-row design grid. Returns a `Grid` with `.cell(col, span, row, row_span)` → `(left, top, width, height)`. (todo 004 §D) |
| `h.SPACING_UNIT_PT` | constant `8` | 8pt vertical rhythm. Vertical gaps should be `Pt(SPACING_UNIT_PT * N)`. |
| `h.icon(slide, name, *, left, top, size, palette, color=None, fonts=None)` | name = semantic key | Place a named icon at `(left, top)` with `size×size` bounding box. Native MSO_SHAPE auto-shape when available (`arrow-right`, `lightning`, `database`, `warning`, `decision`, `molecule`, `sun`, `moon`, `gear`, `star`, `heart`, `cloud`, `document`, `brace-*`, …) — recolorable + scalable + editable in PowerPoint. Unicode-glyph fallback for `check`, `x`, `info`, `dna`, `microscope`, `flask`, `chart`, `lock`, etc. Color defaults to `palette["accent"]`. (todo 004 §C) |
| `h.icon_names()` | — | Sorted list of every icon name `h.icon()` accepts. Call at runtime when the agent needs to pick one. |
| `h.autofit_pt(text, *, max_width_emu, max_height_emu, start_pt, line_spacing=1.22, min_pt=10)` | Korean-aware | Largest pt in `[min_pt, start_pt]` at which `text` fits inside an EMU-sized box. Used internally by `_emit_text` / `bullet_list` / `_render_simple_body` so every text region auto-shrinks pre-export (soffice doesn't fully honor PowerPoint's TEXT_TO_SHAPE autoshrink — without this, dense Korean text overflowed into adjacent boxes). Call directly if you build a custom textbox. |
| `h.estimate_text_width_pt(text, font_pt)` | — | Rough pt-width estimate, summed per-char (Korean / CJK ≈ 1.0 × font_pt, ASCII alnum ≈ 0.55, space ≈ 0.3). |

All Keynote-safe (RGBA → RGB JPEG ≤ 1920px normalization happens inside
the image helpers).

**Use the grid** — don't scatter ad-hoc `Inches(0.7)` constants. Once
the title's placed, `g = h.grid(sw=sw, sh=sh)` gives you a uniform 12-
column geometry that auto-aligns everything. The default leaves
Inches(1.8) at the top for `h.title_block` and Inches(0.6) margins on
the sides + bottom. Override only when a layout genuinely needs less
margin (a hero cover slide, for instance).

`g.cell(col=, span=, row=, row_span=)` returns a **Cell** namedtuple —
unpack as `(left, top, w, h)` OR address as `cell.left / cell.top /
cell.width / cell.height` (todo 007 axis 3).

**Palette has 7 keys** (todo 007 axis 4) — `accent`, `background`,
`foreground`, `surface`, `muted`, `secondary`, `highlight`. The
concept's `Palette:` block can declare any of them; missing keys get
computed (muted = 45/55 blend of fg+bg; secondary = accent shifted
toward black; highlight = accent shifted toward white). Use
`palette["muted"]` for captions instead of hardcoding hex literals.

```python
g = h.grid(sw=sw, sh=sh)            # 12 cols × 6 rows by default
left, top, w_, h_ = g.cell(col=1, span=7, row=1, row_span=4)
h.bullet_list(slide, items, palette=palette, fonts=fonts,
              type_scale=type_scale,
              left=left, top=top, width=w_, height=h_)
left, top, w_, h_ = g.cell(col=8, span=5, row=1, row_span=4)
h.image_figure(1, left=left, top=top, width=w_, height=h_)
# Full-width footer band on the last row
left, top, w_, h_ = g.row(row=6)
h.pull_quote(slide, "Take-home line",
             palette=palette, fonts=fonts, type_scale=type_scale,
             left=left, top=top, width=w_, height=h_)
```

# Pattern shortcuts, worked examples, overlap and alignment

_Part of `/paper-deck`. Read from `SKILL.md` when a slide might be one of the fixed pattern structures, a `code` slide needs an image placeholder, or text collides or a row will not line up._

## Pattern shortcuts — narrow use only

> Each pattern below now lists an explicit "Use ONLY when…" condition.
> The condition is tight on purpose. When in doubt: bespoke.

**`p.*` whole-slide pattern catalog** (todo 004 §B + 005) — these are
*designed compositions*, not primitives. Each pattern bundles a
designer's compositional decisions (grid placement, type hierarchy,
whitespace ratios, color use, visual storytelling devices). Pick a
pattern that fits the slide's *intent*; don't reinvent the layout
with raw helpers.

**Contract: every pattern is one of two kinds.** Get this wrong and
the pattern collides with your `h.title_block` (or vice versa).
Patterns marked **under title** assume you've already called
`h.accent_stripe(slide, ...)` + `h.title_block(slide, ...)`; they
draw their content starting at `y ≈ 1.85"`. The one **owns slide**
pattern (`chapter_divider`) replaces the entire chrome — don't call
the preamble before it.

| Pattern | Contract | Intent / when to use | Content shape |
|---|---|---|---|
| `p.title_slide(slide, *, title, subtitle="", eyebrow="", align="auto")` | **owns slide** | Deck opener / cover at slide 1. Eyebrow + title + accent rule + subtitle. `align="auto"` left-aligns a title that wraps to 2+ lines (avoids ragged-center; common for long Korean titles) and centers a short one — pass `"center"`/`"left"` to force. Distinct from `chapter_divider` (mid-deck). | `title`, `subtitle` (author/venue/date), `eyebrow` (≤ ~24 chars) |
| `p.chapter_divider(slide, *, chapter_label, summary="")` | **owns slide** | Section opener (Era I/II/III). Big centered label + accent rule + summary. | `chapter_label` (≤ 12 chars), `summary` (≤ 50 chars) |
| `p.title_and_image_grid(slide, *, title, images, cols=2)` | under title | N images in a `cols`-column grid (1 = half-bleed, 2 = side-by-side, 4 = 2×2). Optional per-image captions. | `images: [{path, caption?}]`, `cols` (1/2/4) |
| `p.figure_full(slide, *, image_path=None, image_callable=None, caption="")` | under title | Single figure that owns the FULL grid (~85% slide height); caption rides in the bottom-margin strip outside the grid. Pass `image_path` for filesystem PNGs or `image_callable=lambda **kw: h.image_figure(slide, N, **kw)` for paper figures. (todo 008 §A) | one image + ≤ 120-char caption |
| `p.metric_tile_row(slide, *, items)` | under title | KPI / quantitative summary. Big numbers in a row. | `items: 3–5 of (value, label)` or `(value, label, unit)` |
| `p.flow_pipeline(slide, *, items)` | under title | Process / workflow. Numbered cards with right-arrows between. | `items: 3–5 of {tag, body}` |
| `p.gantt_chart(slide, *, items, periods=None, period_count=None)` | under title | Activity rows × period columns with accent-colored bars at each row's `{start, span}`. Zebra-striped rows + period labels + left-aligned activity labels. Pair with `h.deck_chrome` for proposal rhythm. (todo 009 D) | `items: [{label, start, span}]` (1-indexed) |

All under-title patterns take the same theme kwargs (`palette`,
`fonts`, `type_scale`, `sw`, `sh`) as `h.*` helpers; the two
owns-slide patterns likewise.

**There is NO pattern for argument / evidence / comparison content.**
The old hero/evidence/before-after/contrast/quadrant/milestone/
callout/two-content/title-and-body patterns were removed on purpose
(they made every deck look templated). For any body slide that
carries a thesis, supporting points, a comparison, a timeline arc,
or a figure callout, **compose it bespoke** from `h.*` primitives —
that is the default, not the exception.

**Two-step selection** (todo 013 — bespoke-first):

0. **Trigger-table check FIRST.** Re-read the trigger table at the
   top of §5a against this slide's content. If ANY signal matches
   (3+ structured comparison sections, personnel page, equipment
   list with sections, two independent compositions side-by-side,
   KPI + figure, custom architecture, …), compose bespoke from
   `h.*` primitives + raw `slide.shapes.add_shape` — see **Example
   0** below.

1. **Otherwise** — the ONLY time you call a pattern is when the
   slide IS one of the mechanical structures above:
   - Cover at slide 1 → `p.title_slide`; mid-deck section break →
     `p.chapter_divider`.
   - A single figure that should fill the slide → `p.figure_full`
     (or `h.image_figure` for finer control).
   - Multiple images in a grid → `p.title_and_image_grid`.
   - A row of 3–5 KPI numbers, nothing else → `p.metric_tile_row`.
   - A 3–5 step *sequential* process, nothing else → `p.flow_pipeline`.
   - A project timeline / Gantt → `p.gantt_chart`.

   Everything else — a thesis with supporting points, two ideas
   compared, a claim with tagged evidence, a before/after — is
   **bespoke**. Don't force-fit content into a mechanical layout.

> There is intentionally **no "role → pattern" mapping table** here.
> Mapping `method → flow_pipeline` / `result → metric_tile_row` /
> `discussion → some canned comparison` produces decks where every
> slide is one pattern call and the composition repeats no matter how the
> content varies. `role` is a slide *label*, not a design recipe.
> Design the slide from the content; the role doesn't get a vote.

**Rotation is not a goal.** You do NOT need a "different pattern
per consecutive slide" — most consecutive slides should both be
bespoke, with different *compositions* (not different patterns)
appropriate to their content. If three slides in a row each call
a different pattern, you've turned the deck into a pattern menu
demo. The visual rhythm comes from content-driven composition,
not from rotating through the catalog.

**Example 0 — bespoke composition (where most content slides land)**
(todo 013):

A proposal-grade content slide with 3 structured comparison cards
+ a 5-stage pipeline row + a target-metrics line. ~50 shapes,
hand-composed with `h.text` + `slide.shapes.add_shape`. **No
pattern call.** This is the shape of a typical content slide — the
two pattern-driven examples below are the *narrow* case.

```python
mcp__scivo__add_slide(
  slug, deck_id, slide_number=N, role="method",
  title="Part 1 — 참조 유전체 구축 (3중 플랫폼 전략)",
  body="3 sequencing platforms compared on mode / spec / tag, "
       "then the assembly pipeline they feed into, then the "
       "QV / N50 / BUSCO targets.",
  render_mode="code",
  code="""
h.accent_stripe(slide, palette=palette, sw=sw)
h.title_block(slide, title, palette=palette, fonts=fonts,
              type_scale=type_scale, sw=sw, sh=sh)
h.deck_chrome(slide, eyebrow="HOW · 추진 방법",
              footer="기러기류 종 특이적 마커 발굴 · ㈜디보",
              page_number=5, total=13,
              palette=palette, fonts=fonts, sw=sw, sh=sh)

# ── 3 platform comparison cards (top half) ────────────────────────────
g = h.grid(sw=sw, sh=sh, cols=12, rows=6,
           margin_top=Inches(2.0), margin_bot=Inches(0.6))
plats = [
    {"name": "PacBio HiFi",    "mode": "외주 시퀀싱", "spec": "≥30×, Q30+",
     "tag": "단일 리드 정확도"},
    {"name": "ONT PromethION", "mode": "자체 운영",   "spec": "≥20×, R10.4.1, Q20+",
     "tag": "Ultra-long (>100 kb), 복원서열 통과"},
    {"name": "DNBSEQ-G99",     "mode": "자체 운영",   "spec": "Short-read",
     "tag": "Hybrid polishing + k-mer QC"},
]
for i, plat in enumerate(plats):
    cell = g.cell(col=1 + i*4, span=4, row=1, row_span=2)
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
        cell.left, cell.top, cell.width, cell.height)
    box.fill.solid(); box.fill.fore_color.rgb = palette["surface"]
    box.line.color.rgb = palette["accent"]; box.line.width = Pt(0.75)
    box.shadow.inherit = False
    stripe = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
        cell.left, cell.top, cell.width, Pt(4))
    stripe.line.fill.background()
    stripe.fill.solid(); stripe.fill.fore_color.rgb = palette["accent"]
    stripe.shadow.inherit = False
    h.text(slide, plat["name"],
           left=cell.left + Pt(10), top=cell.top + Pt(10),
           width=cell.width - Pt(20), height=Pt(28),
           palette=palette, size_pt=18, bold=True,
           font_name=fonts.get("display"))
    h.text(slide, plat["mode"],
           left=cell.left + Pt(10), top=cell.top + Pt(38),
           width=cell.width - Pt(20), height=Pt(18),
           palette=palette, size_pt=11, color=palette["muted"],
           font_name=fonts.get("body"))
    h.text(slide, plat["spec"],
           left=cell.left + Pt(10), top=cell.top + Pt(62),
           width=cell.width - Pt(20), height=Pt(20),
           palette=palette, size_pt=14, bold=True,
           font_name=fonts.get("body"))
    h.text(slide, plat["tag"],
           left=cell.left + Pt(10), top=cell.top + Pt(88),
           width=cell.width - Pt(20), height=Pt(40),
           palette=palette, size_pt=11, color=palette["muted"],
           font_name=fonts.get("body"))

# ── 5-stage pipeline row (hand-composed) ──────────────────────────────
stages = ["시료 QC HMW DNA", "라이브러리 시퀀싱", "K-mer (Meryl/GS2)",
          "de novo (Verkko)", "Hybrid Polishing"]
h.text(slide, "어셈블리 파이프라인 (척추동물 reference-grade 표준 접근)",
       left=Inches(0.6), top=Inches(4.5),
       width=Inches(12), height=Pt(20),
       palette=palette, size_pt=13, bold=True,
       font_name=fonts.get("display"))
stage_top = Inches(4.85); stage_h = Inches(0.7)
stage_total_w = sw - Inches(1.2)
stage_w = (stage_total_w - Pt(8) * (len(stages) - 1)) // len(stages)
for i, s in enumerate(stages):
    sx = Inches(0.6) + i * (stage_w + Pt(8))
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
        sx, stage_top, stage_w, stage_h)
    box.fill.solid(); box.fill.fore_color.rgb = palette["background"]
    box.line.color.rgb = palette["secondary"]; box.line.width = Pt(0.75)
    box.shadow.inherit = False
    h.text(slide, f"{i+1}", left=sx + Pt(6), top=stage_top + Pt(4),
           width=Pt(20), height=Pt(20),
           palette=palette, size_pt=10, bold=True,
           color=palette["secondary"], font_name=fonts.get("display"))
    h.text(slide, s, left=sx + Pt(6), top=stage_top + Pt(22),
           width=stage_w - Pt(12), height=stage_h - Pt(24),
           palette=palette, size_pt=11, font_name=fonts.get("body"))

# ── Target metrics line at the bottom ─────────────────────────────────
h.text(slide, "▶ 목표 산출물",
       left=Inches(0.6), top=Inches(5.8),
       width=Inches(2.0), height=Pt(20),
       palette=palette, size_pt=12, bold=True,
       color=palette["accent"], font_name=fonts.get("display"))
h.text(slide,
       "Contig N50 ≥ 5 Mb · BUSCO(aves_odb10) C ≥ 95% · "
       "Mercury QV ≥ 40 · scaffold/T2T-급 chromosome-level reference "
       "+ Mitogenome",
       left=Inches(2.6), top=Inches(5.8),
       width=sw - Inches(3.2), height=Pt(34),
       palette=palette, size_pt=11, color=palette["foreground"],
       font_name=fonts.get("body"))
""",
)
```

Notice what's NOT there: no `p.flow_pipeline`, no `p.metric_tile_row`,
no `p.card_grid`. The slide *contains* a card row and a pipeline
row and a metric line, but each is composed directly from
primitives so they share one coherent layout instead of three
stacked pattern boxes. This is the default shape for any slide
with multiple coordinated regions — and that's most slides.

Source mirror: `reference_corpus/generate.py` under
`"proposal_dense"`; rendered preview at
`reference_corpus/proposal_dense.png` (42 shapes). For a
side-by-side bespoke variant (personnel table on the left,
equipment list on the right, both dense), see
`reference_corpus/generate.py` under `"personnel_equipment"`.

**Example 1 — title + 4-card grid + take-home quote**:

```python
mcp__scivo__add_slide(
  slug, deck_id, slide_number=N, role="discussion",
  title="The four harness primitives",
  body="Memory keeps decisions. Hooks fire on events. Slash commands "
       "are reusable. The context manager is the LLM's attention.",
  notes="Spend ~30 seconds on each primitive then land the take-home.",
  render_mode="code",
  code="""
h.accent_stripe(slide, palette=palette, sw=sw)
h.title_block(slide, title, palette=palette, fonts=fonts,
              type_scale=type_scale, sw=sw, sh=sh)
h.card_grid(slide, [
    {"title": "Memory",
     "body": "decisions and corrections stack across sessions"},
    {"title": "Hooks",
     "body": "auto-run on events (export validation, DOI check, …)"},
    {"title": "Slash commands",
     "body": "reusable workflows like /literature-review"},
    {"title": "Context manager",
     "body": "what the LLM is looking at right now"},
], left=Inches(0.7), top=Inches(1.9),
   width=sw - Inches(1.4), height=Inches(3.6),
   palette=palette, fonts=fonts, type_scale=type_scale, cols=2)
h.pull_quote(slide,
    "Each conversation builds the next version of the AI.",
    palette=palette, fonts=fonts, type_scale=type_scale,
    left=Inches(0.7), top=Inches(5.7),
    width=sw - Inches(1.4), height=Inches(1.0))
""",
)
```

**Example 2 — title + bullets on the left + figure on the right**:

```python
code="""
h.accent_stripe(slide, palette=palette, sw=sw)
h.title_block(slide, title, palette=palette, fonts=fonts,
              type_scale=type_scale, sw=sw, sh=sh)
h.bullet_list(slide, [
    "Two-week bespoke pipeline (before)",
    "30-second MCP query (after)",
    "Automatic provenance trail on every step",
], palette=palette, fonts=fonts, type_scale=type_scale,
   left=Inches(0.7), top=Inches(2.0),
   width=Inches(6.0), height=Inches(4.5))
h.image_figure(1, left=Inches(7.0), top=Inches(2.0),
               width=Inches(5.8), height=Inches(4.5))
"""
```

**Failure handling** — if the snippet raises, the exporter degrades
that slide to plain text (title + body) and records the error in
the export result's `code_errors[]`. The deck still exports. After
seeing an error, fix the snippet and re-export.

**Patterns are a starting point, not a ceiling.** (todo 009.) The
patterns above cover the *common* shapes of a slide; they don't cover
proposal pages, Gantt charts, personnel tables, or any other layout
where the content asks for 30+ shapes hand-composed. Real decks
(e.g., a 13-page funded-grant proposal) have **30–70 shapes per
content slide**. Our toy patterns produce ~10–15. The gap is the
agent's compose budget per slide, not python-pptx's capability.

So:
- **Default to bespoke** — see the "Go bespoke when…" trigger table
  near the top of §5a (right before the pattern catalog).
- **Use a pattern only when the content is an exact fit** — each
  pattern's "Use ONLY when…" line in the catalog is intentionally
  tight. If your brief overflows that condition, you're in bespoke
  territory.
- **Density signals you're on the right track.** When a content slide
  ends up at ~25–60 shapes, that's *good* — every inch carries info.
  The bad case is 60 shapes with no hierarchy; not 60 shapes by
  themselves.
- **Chrome is part of every content slide.** `h.deck_chrome(eyebrow,
  footer, page_number, total)` after `h.title_block`. Pair the
  eyebrow with the slide's role (`role="method"` → `eyebrow="HOW ·
  …"`, `role="result"` → `eyebrow="WHAT · …"`).

**Image placeholder workflow for code slides.** When a `code` slide
needs images (a paper figure, an AI-generated diagram, a code-shape
PNG), **declare them as regions[] up front** instead of hardcoding
paths. The agent's workflow:

1. `add_slide(..., render_mode="code", code="""…h.image_region('r1', left=…, top=…, width=…, height=…)…""")`
2. `set_slide_regions(slug, deck_id, slide_id, regions=[{"render_mode": "ai-image", "prompt": "…", "x": 0.54, "y": 0.30, "w": 0.42, "h": 0.55}, …])`
3. `render_deck(slug, deck_id)` — `render_mode="code"` slides with regions are now rendered the same way as hybrid (each region's image is materialized).
4. `export_deck_to_pptx(slug, deck_id)` — the snippet's `h.image_region(id, …)` call resolves to the rendered blob and embeds it.

This separates **layout decision** (in the code) from **image
generation** (in regions[]). Theme / palette changes don't trigger
re-generation; re-positioning a region doesn't either.

`set_slide_regions` keeps the slide in `code` mode whenever it already
carries a `code` snippet (or its `render_mode` is explicitly `code`) —
so you can author the code first and add regions after without losing
the text/shape overlay. Only a slide with **no** code snaps to `hybrid`
(regions-only, no code execution at export). Watch for this: if you
strip a slide's code to empty and then add regions, it becomes hybrid.

**Text will not overflow its OWN box** — every text emitter in `h.*` and every
`_emit_text` inside `p.*` calls `h.autofit_pt` to shrink the font
before rendering when content would overflow. PowerPoint's
TEXT_TO_SHAPE autoshrink kicks in on top of this; soffice (our
preview pipeline) doesn't fully honor that, so the autofit ensures
the PNG matches the slide. The minimum fall-back is ~12pt for body,
~16pt for headings — if you see autofit hitting min, the right fix
is to **drop content**, not to expand the box. This is about one box and
its text. Two boxes placed over each other is a different fault, and it does
happen: the `layout_warnings` that hard rule 7 makes you clear are how it is
found.

**Text-on-text overlap (todo 014 vstack-fix)** — the *other* overlap
class: when bespoke code places two textboxes at the SAME `(left,
top)` and they superimpose. Symptom looks like one character on top
of another (e.g., a step number "01" overlapping the first hangul of
its label). Cause: you wrote two `h.text(...)` calls with hand-
computed `top` values and reused the same `top` by accident, OR you
didn't increment `top` by the first line's measured height.

Fix: **use `h.vstack(slide, lines, ...)` whenever you would
otherwise call `h.text` twice with hand-computed `top` values for a
stacked layout** (number eyebrow + label below, title + subtitle +
body, callout headline + body, etc.). `h.vstack` measures each
line's natural height and increments `y` between items, returning
the bottom `y` for chaining downstream content. Eliminates the whole
"forgot to advance y" class of overlap bugs.

```python
# WRONG — both textboxes at the same y; "01" overlaps the label.
h.text(slide, f"{i+1:02d}", left=x, top=y, width=w, height=Pt(20), ...)
h.text(slide, label,        left=x, top=y, width=w, height=Pt(20), ...)

# RIGHT — vstack handles the y advancement.
final_y = h.vstack(slide, [
    {"text": f"{i+1:02d}", "size_pt": 14, "color": "muted", "bold": True},
    {"text": label,        "size_pt": 16, "bold": True},
], left=x, top=y, width=w, palette=palette, fonts=fonts)
# downstream items go at `final_y + Pt(...)`.
```

**Timeline / milestone-row alignment (todo 017/018)** — for horizontal
multi-column timelines (year + dot on the rail + content stack
below), **every textbox in a single column** must share an X axis
with the dot. Not just the year — ALL of {year, dot, title,
subtitle, body, any footer line in that column}. v7 p.6 had the
year-vs-dot mismatch; v8 p.5 fixed year+dot but left
title/subtitle/body left-aligned → titles drifted left of the
centered year+dot. Both failures share one root: applying align=
to *some* elements and not the rest.

**Rule**: pick the column's alignment ONCE (`PP_ALIGN.CENTER` for
center-anchored columns, or omit for left-anchored). Then apply
that same alignment to **every textbox** in the column. The dot
shape's coordinate basis follows: center column → dot at
`col_left + col_w//2 - r`; left column → dot at `col_left`.

```python
# WRONG — only the year carries align=CENTER; title/subtitle/body
# default to LEFT and drift to the column's left edge.
align_col = PP_ALIGN.CENTER
h.text(slide, str(year), left=cx, top=y, width=cw, align=align_col, ...)
slide.shapes.add_shape(MSO_SHAPE.OVAL,
    cx + cw // 2 - r, dot_y, 2 * r, 2 * r)
h.text(slide, title,    left=cx, top=y2, width=cw, ...)  # ← LEFT default
h.text(slide, subtitle, left=cx, top=y3, width=cw, ...)  # ← LEFT default
h.text(slide, body,     left=cx, top=y4, width=cw, ...)  # ← LEFT default

# RIGHT — EVERY textbox in the column inherits the column's align.
align_col = PP_ALIGN.CENTER
for col_kwargs in (
    dict(text=str(year),  size_pt=14, color="muted"),
    dict(text=title,      size_pt=18, bold=True),
    dict(text=subtitle,   size_pt=12, italic=True, color="muted"),
    dict(text=body,       size_pt=14),
):
    h.text(slide, **col_kwargs, left=cx, width=cw, top=...,
           height=..., align=align_col, palette=palette, fonts=fonts)
slide.shapes.add_shape(MSO_SHAPE.OVAL,
    cx + cw // 2 - r, dot_y, 2 * r, 2 * r)
```

Even simpler: use `h.vstack(...)` for the column's text stack with
`align=PP_ALIGN.CENTER` propagated to every item. One alignment
decision per column, no chance to forget on one of the rows.

**Filled rect + text inside → use `h.callout`, never hand-roll
(todo 019)** — every "filled rectangle containing text" pattern
the agent hand-composes ends up wrong in one of two directions:
overflow (text past rect bottom, v8 p.14 BEFORE/AFTER) or
underfill (rect ~2× taller than its content, leaving an unbalanced
empty band — v9 p.14 TAKE-HOME footer). Both fail the same way:
agent computes the rect height before knowing the rendered text
height. `h.callout` exists to make this impossible — it measures
content first, then sizes the rect to `content_h + 2*pad_pt`.
**Hard rule**: any filled rectangle that contains text content
(dark hero footer band, light info callout, "BEFORE / AFTER"
comparison pairs, take-home statement boxes, "결산 / 진단 / 핵심"
type stamps) MUST go through `h.callout`. Drawing
`slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, ...)` + a hand-placed
`h.text` inside it is **forbidden for this pattern** — the only
filled rectangles you should draw by hand are decorative
non-content shapes (accent strips, dividers, background panels
that hold images).

```python
# WRONG — manual rect with hand-guessed height, content under/overflows.
hero = slide.shapes.add_shape(
    MSO_SHAPE.RECTANGLE, x, y, w, Inches(2.0),  # ← guessed height
)
hero.fill.solid(); hero.fill.fore_color.rgb = palette["foreground"]
h.text(slide, "TAKE-HOME", left=x + pad, top=y + pad, width=w - 2*pad,
       height=Pt(20), size_pt=12, color=palette["surface"],
       bold=True, palette=palette, fonts=fonts)
h.text(slide, "더 큰 모델이 아니라, 더 나은 연결.",
       left=x + pad, top=y + pad + Pt(28), width=w - 2*pad,
       height=Pt(60), size_pt=32, color=palette["surface"],
       bold=True, palette=palette, fonts=fonts)

# RIGHT — h.callout sizes the rect to its content automatically.
h.callout(slide,
    left=x, top=y, width=w, fill=palette["foreground"],
    headline="TAKE-HOME",
    body="더 큰 모델이 아니라, 더 나은 연결.",
    palette=palette, fonts=fonts, type_scale=type_scale,
)
# (For richer content, pass items=[{text, size_pt, bold, ...}, …]
#  instead of headline=/body=.)
```

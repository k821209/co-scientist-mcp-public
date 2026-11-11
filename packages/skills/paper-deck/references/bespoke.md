# Bespoke is the default

_Part of `/paper-deck`. Read from `SKILL.md` when you design the first content slide: when a brief means a composed slide rather than a pattern, what `h.deck_chrome` is and what not to add to it, and what a dense slide looks like._

## ⚠️  Bespoke is the default — go bespoke when… (todo 011)

> Most content slides are NOT a single-pattern fit. Default to
> bespoke composition with `h.*` primitives + `slide.shapes.add_shape`.
> The pattern catalog comes AFTER this section as narrow shortcuts.

**Trigger table** — any of these signals in the slide brief means
**do NOT call a pattern**; compose directly:

| Signal in content brief | Why no pattern fits |
|---|---|
| 3+ structured comparison sections (e.g. "3 platforms × {mode, spec, tag}") | `card_grid` tops out at title+body; can't hold mode/spec/tag layered per card |
| Personnel page (N people × {role, percentage, expertise}) | Need 3-field row × N — no pattern; compose with rectangles + h.text |
| Equipment list with sections (sequencing / HPC / storage / …) | Multi-section nested-bullet structure; patterns are flat |
| Gantt or roadmap with parallel workstreams | Use `p.gantt_chart` BUT pair with chrome + extra annotation rows hand-added |
| Slide carries TWO independent dense compositions side-by-side (e.g. personnel + equipment) | Patterns assume ONE composition per slide |
| KPI tiles + supporting figure on the same slide | `p.metric_tile_row` doesn't take a figure; compose tiles + figure side-by-side |
| Architecture / system diagram with custom topology | No pattern covers arbitrary node-edge structures |

**Density references — these prove what 30–60 shapes LOOKS like.
They are NOT templates to copy.** (todo 011 v2.)

- `reference_corpus/proposal_dense.png` (42 shapes; source in
  `reference_corpus/generate.py` under `"proposal_dense"`)
- `reference_corpus/personnel_equipment.png` (47 shapes; source
  ditto)

Mirror the **technique** (h.text + slide.shapes.add_shape composed
into cohesive sections, accent stripes, multi-section blocks). Do
NOT mirror the **content** — those exemplars happen to be a Korean
grant proposal; your slide's content comes from YOUR paper. If your
paper has no platform comparison, your slide has no platform
comparison; if it has no personnel page, you don't make one. The
corpus is a *density gym*, not a content shopping mall.

**Chrome (`h.deck_chrome`) is part of every content slide** — never
skip it. But the eyebrow text comes from YOUR talk's sections (not
necessarily WHY / HOW / WHAT / WHO — those are one team's
convention).

**Chrome rules — what NOT to add (todo 020).** `h.deck_chrome` is
the ONLY chrome the slide gets. Do not invent:

- **Marginalia / sidebars**: vertical rotated text on the slide
  edge ("§14 horizon", "§ MAP", "note · vignette · hook"),
  paragraph-mark hashes, book-style edge labels. These are
  decorative noise to the audience; remove them on sight. Only
  add a marginal label if the user has explicitly asked for a
  "marginal notes" aesthetic for the deck.
- **Duplicate page indicators**: `deck_chrome` already prints
  "N / total" bottom-right. Don't draw a SECOND copy (top-left,
  inside a card, etc.) — it confuses the audience and reads as
  a layout bug.
- **Decorative dots / pips placed near textboxes you didn't
  measure**: a small `MSO_SHAPE.OVAL` sitting on a horizontal
  rail must clear every textbox in its column by ≥ Pt(8) vertical
  gap. v10 p.4 had timeline dots landing on the "g" of
  "Diagnosis" and the "i" of "Application" because dot.y and
  italic_label.y were the same. The overlap detector only
  catches textbox↔textbox; shape↔textbox needs manual care:

```python
# WRONG — dot center aligned with italic label's vertical middle.
rail_y = Inches(3.5)
slide.shapes.add_shape(MSO_SHAPE.OVAL,
    cx - r, rail_y - r, 2 * r, 2 * r)
h.text(slide, label_italic, left=cx_box, top=rail_y - Pt(8),
       width=cw, height=Pt(16), italic=True, ...)  # ← overlaps the dot

# RIGHT — dot on rail; italic label distinctly below.
rail_y = Inches(3.3)
slide.shapes.add_shape(MSO_SHAPE.OVAL,
    cx - r, rail_y - r, 2 * r, 2 * r)
h.text(slide, label_italic, left=cx_box, top=rail_y + r + Pt(8),
       width=cw, height=Pt(16), italic=True, ...)
```

- **Anchor a diagram's labels to its RAIL/CENTER, not to a band's
  edge (inner-margin).** In a hand-drawn timeline/bar chart, a label
  placed at a band's top or bottom edge ends up cramped against the
  border. Anchor above/below labels off the rail — `rail_y - offset`
  (above) / `rail_y + offset` (below) — so the band's inner margin is
  automatic and consistent, instead of computing each label's inset
  from the band edge by hand. `preview_slide` now lints this: a label
  whose bbox sits < 8pt from the inner edge of a containing band/card
  is reported in `layout_warnings` as **`inner_margin_tight`** (with
  the tight side + gap). Helper cards / `text_block`s aren't flagged
  (their text has built-in padding); this targets bespoke coordinate
  labels. Fix by re-anchoring to the rail, not by nudging pixels.

  A label that CROSSES its container's edge — text rendering outside
  the card border — is **`inner_margin_overflow`** (with the side and
  how far past, in pt). It replaces `inner_margin_tight` on that label
  rather than adding to it. Unlike `tight`, it fires on snug
  containers too, including a hand-built card its body text nearly
  fills. Fix by cutting content or growing the container — shrinking
  the text box only hides the spill behind a clipping boundary that
  PowerPoint will not honour.

  Overflow is measured from the **wrapped** bottom, not the declared
  box height — the usual way a card overflows is a roomy-looking box
  whose text wraps to two or three times it, not a box placed already
  overrunning.

  Both halves of this were broken until 2026-08-21. First the check
  was inverted (overflow disqualified the card as a container, so the
  worse the spill the quieter the lint); then the fix graded only
  declared heights and stayed silent on wrapping, which is the common
  case. On any build before 0.1.20260821.post1, `layout_warnings: []`
  does not mean the text is inside its card — check the PNG.

- **Repeat-symbol clusters (I/II/III, ★/★★/★★★, N-bar marks)
  must anchor to their cluster's HORIZONTAL CENTER, not to the
  left-most element** (todo 021). Drawing the first bar at
  `col_center` and adding the next bars to its right shifts the
  cluster's optical center rightward as the symbol grows — by
  III/3-bars the cluster's center is `bar_width + gap` past
  column-center, and the accent line + label below (still at
  column-center) read as floating left of the symbol. v11 cover
  shows the bug: I lines up cleanly, II drifts slightly right of
  its accent, III drifts visibly right of "MCP 협업".

```python
# WRONG — first bar at col_center; cluster grows rightward.
for k in range(n_bars):
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
        col_center + k * (bar_w + gap), top, bar_w, bar_h)

# RIGHT — compute cluster_width first; place from a left edge
# derived so the cluster's center == col_center.
cluster_w = n_bars * bar_w + (n_bars - 1) * gap
cluster_left = col_center - cluster_w // 2
for k in range(n_bars):
    slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
        cluster_left + k * (bar_w + gap), top, bar_w, bar_h)
# Now accent_line and label centered at col_center align with the
# cluster's optical center.
```

If the brief has none of the trigger signals AND fits one of the
patterns below cleanly, you can use a single pattern call. But check
the pattern's "Use ONLY when…" line — most are tighter than they
look.

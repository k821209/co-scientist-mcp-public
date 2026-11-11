# Compositional effects

_Part of `/paper-deck`. Read from `SKILL.md` when arranging a slide that is not working — title alignment, left and right, full-bleed against a caption strip, grids, whitespace._

### 5c. Compositional effects — why arrangement matters (todo 006)

Same content lands differently depending on arrangement. The patterns
encode these rules; when you build a custom layout, mirror them.

**Centered vs left-aligned titles (ragged center).** A title that wraps
to two+ lines reads as misaligned when centered — each line is a
different width, so their left edges stagger ("ragged center"), which the
eye registers as "not aligned" even after you tune the line breaks. A
long Korean cover title hits this almost every time. Rule: **center only
short one-line titles; left-align any multi-line title** onto a single
left baseline (eyebrow → title lines → accent rule → subtitle all share
one left margin). `p.title_slide(align="auto")` does this for you (left
when it wraps, center otherwise); for a bespoke cover, follow the same
rule by hand. This also keeps the cover consistent with body slides,
whose `h.title_block` is already left-aligned.

**Left vs right placement.** Western reading is L→R; the right side is
where the audience arrives — the natural "this is the conclusion"
position. Place the **subject** on the right when it's the destination;
on the left when it's the starting fact.
- A before/after composition puts BEFORE on the left (history,
  muted) and AFTER on the right (where you arrive, accented) — the
  asymmetric weight carries the direction of improvement.

**Image emphasis — full-bleed vs caption strip.**
- Full-bleed image, no caption = "the image **IS** the message". Use
  when the image self-explains and you want emotional weight.
- Image + caption strip = "the image is supporting **evidence**".
  Caption stays in body type, never display.

**Multi-image arrangement — grid vs row.**
- 2×2 grid = COMPARISON (items are peers; no order).
- 3- or 4-image single row = PROGRESSION (left→right reads as sequence).
- 1 hero + N small supporting = FOCUS + context.

**Title position — hierarchy.**
- Title at top (default): content-first. The audience reads the title
  briefly and dwells on the body. Most slides.
- Title centered, no body (`title_slide` / `chapter_divider`): the
  title **is** the content. Use for openers and section breaks.

**Whitespace as design.**
- Filled body box = density. Defensible for dense reference data.
- 60% column with 40% whitespace = focus. Use for theses, hero
  statements, KPI tiles. When composing a text-body slide bespoke,
  keep the body in a ~60% left column and leave the right 40% as
  intentional whitespace.

**The 4-color / 4-type-size discipline** (from the deck concept's
`Design language` block, todo 004 §G). Per slide:
- ≤ 3 colors (accent + foreground + one neutral).
- ≤ 4 distinct type sizes (read from `type_scale`, never ad-hoc).

When you author a layout that breaks one of these, ask whether the
break earns its keep — and if not, fall back to the rule.

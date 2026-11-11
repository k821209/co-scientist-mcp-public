# What good looks like, and the AI-slide look

_Part of `/paper-deck`. Read from `SKILL.md` when before the first content slide and again at the critique pass: the rendered exemplars, the tells of a generated deck, a palette library, sizing ratios._

### 5d. Reference corpus — what good renderings look like (todo 004 §F)

The skill ships with a curated corpus of exemplar slides at
`reference_corpus/` (one PNG per canonical pattern + `manifest.json`).
Each entry records the pattern name, the content the example uses, and
a do / don't pair the agent should mirror in its own slides.

**Recommended flow when authoring a `code` slide**:

1. Decide whether the slide is one of the mechanical structures (§5a)
   or — far more often — a bespoke composition.
2. Read `reference_corpus/manifest.json` (beside this skill's `SKILL.md`).
   For a mechanical layout, confirm the canonical example exists; for
   a bespoke slide, study `proposal_dense` / `personnel_equipment`.
3. Open the matching PNG (`reference_corpus/<name>.png`) and LOOK at it —
   see what a good rendering looks like before authoring your own.
4. Follow the manifest entry's **do**; avoid its **dont**.
5. Author the `code` snippet against your own content. Run the
   critique loop (§9) against the result and the reference side-by-
   side; rewrite if your rendering diverges visually from the
   exemplar's discipline.

The corpus covers the 7 mechanical layouts — `title_slide`,
`chapter_divider`, `title_and_image_grid`, `figure_full`,
`metric_tile_row`, `flow_pipeline`, `gantt_chart` — plus two
bespoke density exemplars (`proposal_dense`, `personnel_equipment`)
that show what hand-composed body slides look like. `generate.py` beside
them is the source of each exemplar (regenerating the PNGs is a maintainer's
step, run from the package checkout).

The corpus is checked in (small PNGs), so the agent has it locally
without a network round-trip. Each PNG is < 100 KB.

### 5e. Don'ts + palette library — avoid the AI-slide look (ref: Anthropic pptx skill)

**Tells of an AI-generated deck — don't do these:**
- **Don't underline every title by reflex.** A short rule under every title
  is the #1 AI tell when nobody chose it. It is a THEME decision, made once:
  the presets whose concept says "a thin accent rule under each title" have
  it, and `h.title_block` draws it by default (`accent_rule=True`) for them.
  In a concept you wrote yourself, say in the concept whether titles carry
  one — and pass `accent_rule=False` when it does not — rather than getting
  it because it is the default. Either way, no SECOND underline of your own
  under a heading; the accent motif is used on purpose (the top
  `h.accent_stripe`, ONE highlight number per slide).
- **Don't center body text.** Left-align body/bullets; centering is only for
  short cover/section hero lines (`p.title_slide` already left-aligns multi-
  line titles).
- **Don't repeat the same layout** slide after slide — vary: two-column,
  icon+text rows, 2×2/2×3 grids, a big-stat callout, a half-bleed figure.
- **Don't skimp on size contrast** — a hero number/headline should dwarf its
  caption (use the `display_*` type-scale steps).
- **Every content slide needs a visual anchor** — a figure, a chart, an icon,
  a colored card, or a big number. A wall of bullets reads as a draft.
- **Don't default to blue.** Pick a palette that fits the topic (below), and
  keep it: accent + foreground + ONE neutral, ≤3 colors per slide.

**Quick palette library** (host-safe hex — drop into the concept `Palette:`;
remember `text:` = foreground, and keep `accent` for the ONE thing per slide):

| Theme | accent | bg | foreground | surface | muted |
|---|---|---|---|---|---|
| Navy / ice (data, methods) | `#1F6FEB` | `#F7F8FA` | `#161B22` | `#FFFFFF` | `#6B7280` |
| Forest / moss (ecology, plants) | `#2E7D32` | `#F6F8F4` | `#14210F` | `#FFFFFF` | `#5B6B57` |
| Coral / gold (results, impact) | `#E8590C` | `#FFF9F3` | `#231209` | `#FFFFFF` | `#8A6D5A` |
| Plum / slate (theory) | `#7C3AED` | `#F8F7FB` | `#1E1B2E` | `#FFFFFF` | `#6B6780` |
| Teal / sand (clinical, env) | `#0D9488` | `#F4F8F7` | `#0F2420` | `#FFFFFF` | `#5E7370` |

Fonts: keep to faces present on the render host — `export_deck_to_pptx`
returns `font_warnings` for any missing one (a missing font → LibreOffice
substitutes → the PDF diverges from PowerPoint). Safe picks: macOS
`Apple SD Gothic Neo` (display+body) + `Menlo` (mono); for Korean decks the
Noto Sans CJK KR static build.

**Sizing ratios (so elements read at projection distance):**
- **Card icon ≥ 40–50% of the card width.** A 72pt (1") icon in a 3" card
  is a dot — make it big. (`h.icon(..., size=Inches(card_w*0.45))`.)
- **Card inner margin is TWO layers — budget both, or Korean text touches
  the border:**
  1. *Outer pad* (card border → text box): place the text box at
     `left+pad, top+pad` with `width-2*pad` — pad ≥ **14pt**. (You control
     this in code.)
  2. *Text-frame inset* (text box edge → glyphs): a python-pptx textbox
     defaults to only ~7pt L/R and **~3.6pt top/bottom** — and CJK glyphs
     fill the line box top-to-bottom, so that 3.6pt reads as "touching".
     For a bespoke card set it explicitly:
     `tf.margin_top = tf.margin_bottom = Pt(6)` (and L/R if you zeroed them).
  **Simplest: don't hand-compose.** `h.card` / `h.callout` /
  `h.text_block(fill=…)` apply a proper pad for you. `h.text_block` now
  defaults to **left align** (so the LibreOffice/PDF render doesn't center
  an unset paragraph), draws a **visible muted border** on a filled box
  (pass `border=False`/`border="accent"` to change), and uses a **non-zero
  top/bottom inset** (`pad_y_pt`) so CJK text doesn't touch the edge. Use
  them for any bordered text box. **Omit `height`** on `h.text_block`
  (height=None) to auto-size the box to its lines — no hand-calculating box
  vs text height, no overflow; the emitted height is on `shape.height` for
  stacking the next box. (Per-line `pad_top_pt` adds space before a line.)
  Bespoke `rectangle + h.text` risks both (text touching the inset edge AND
  wrapping past the bottom border) — the latter is flagged by
  `overlap_warnings` (wrap overflow).
- **Type hierarchy 1.5–2.5×**: a card/section header should be 1.5–2.5×
  the body text under it (e.g. body 16 → head 28). Hero numbers larger
  still (`display_*`).
- **4-card row**: each card ≈ (content_width − 3×gap) / 4; keep cards
  roughly square-to-portrait (height ≈ 0.9–1.3× width) — wider-than-tall
  cards look empty.

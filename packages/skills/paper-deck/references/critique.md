# Deck critique — the fix recipes and the rubric

Moved out of `SKILL.md` §9 (packages/skills/CLAUDE.md rule 3: the next edit
that touches paper-deck splits rules from reference). The loop that uses this
file is `/visual-review`; §9 says when to open it. Nothing here is a tool
reference — `export_deck_to_pptx` and `preview_slide` return these lists and
their docstrings carry the shapes. What is here is what to DO about each one,
which the code cannot say.

## The automatic FAILs

A slide in any of these lists fails regardless of how it scores on the rubric
below. Re-render until the list is empty.

### `overlap_warnings` — text on text (todo 016)

Text rendered on top of other text, which LibreOffice will happily export.
For each entry, find the two textboxes in the slide's `code` (the
`a_preview` / `b_preview` strings are the first line of each box's text) and
replace the manual `h.text(...)` /
`add_textbox(...)` calls with `h.vstack(...)` for stacked content
in a single column, or fix the y-coordinates so the boxes don't
overlap. Re-export until `overlap_warnings == []`. This also catches
**wrap overflow** — a big number / long line in a narrow box that wraps
to extra lines and spills onto the box below (the box's declared height
is small but the rendered text is taller). Fix by shrinking the font
(`h.autofit_pt`) or widening the box so the value stays on one line.

### `bounds_warnings` — text off the canvas

A row of prompter/CDS boxes, or a stacked proportion bar, laid out past the
right edge. The usual cause
is a width budget computed against the full slide width `sw` instead of
the *content* width. For any horizontal run of boxes/segments + gaps:
the budget is `content_w = sw - left_margin - right_margin` (typically
`sw - Inches(1.2)`), and `sum(segment widths) + sum(gaps)` must be
`≤ content_w`. Lay segments out starting at `left = left_margin` and
size each as a fraction of `content_w` — never start at a margin and
then add full-width segments. Re-export until `bounds_warnings == []`.

### `font_warnings` — a font the render host does not have

A concept Typography font that is not installed where the deck renders.
LibreOffice silently substitutes a missing face, so the exported PDF/PNG (and
the dashboard preview) diverge from PowerPoint — the
"PPT looks right but the PDF is misaligned" trap. Two gotchas: (a) the font
isn't installed at all → pick one that is; (b) it's a **variable** font
(e.g. some `Noto Sans CJK KR` builds) → LibreOffice may pick the wrong weight,
so prefer a static build or a host-bundled family. Safe cross-platform
picks: macOS `Apple SD Gothic Neo` + `Menlo`; otherwise a static Noto
build. Fix the concept Typography and re-export until `font_warnings == []`.
(Empty when `fc-list` isn't on the host — then it can't be checked.)

### `placeholder_warnings` — "TODO" in front of the audience

Leftover placeholder text ("Lorem ipsum", "TODO", "[placeholder]", "XXXX")
still in the rendered deck. Every hit is real text the audience would see —
replace it with the actual content and re-export until
`placeholder_warnings == []`.

### `layout_warnings` — images

Image problems the text-overlap detector can't see: `tiny_image` (a
picture under ~0.7" — too small to read at projection distance; enlarge it)
and `header_overlap` (a picture that actually overlaps the title text —
move it below the title block). A small top-right corner logo is exempt, so
deck-chrome logos don't false-positive. On both `preview_slide` and the export.

## The rubric

Each category scored 1–5; a slide passes when all are ≥ 4. Score off the
sheet first (`preview_deck_sheet`), then the slides it flagged:

```
res = mcp__scivo__export_deck_to_pptx(slug, deck_id, output_path="<dir>/<deck>.pptx")
for png in res["slide_pngs"]:
    # Read the PNG via the Read tool — Claude is multimodal and will
    # see the actual slide rendering.
    Read(png["local_path"])
    # Score it (in your head / scratchpad) against the rubric.
    # If any category < 4, rewrite the slide's `code` and update_slide.
```

| Category | Question |
|---|---|
| **Visual integrity** (todo 014/016 — automatic FAIL) | Also flagged automatically by `result["overlap_warnings"]` for the text-on-text case. Look for any of these in the PNG and **rewrite the slide bespoke** if you see them: (a) two text elements rendered at the same coordinates (e.g., a step number "01" superimposed on the first hangul of its label — see v4 p.13 Harness 4-primitive cards) → cause is calling `h.text(...)` twice at the same `top` for stacked content → fix by replacing both calls with one `h.vstack(slide, lines=[...], left=, top=, width=)` that auto-advances `y` between items; (b) text extending past its visible container's bottom/right edge (e.g., body wrapping below a card's border — see v4 p.15 card 4 "Synthesis + provenance" wrap, v4 p.12 STACK cards' muted captions) → cause is a fixed-height container with content that doesn't fit at autofit's min_pt → fix by replacing the manual rect + h.text combo with `h.callout(slide, *, fill, items=, left=, top=, width=)` which sizes its bg rect to fit the measured content; (c) a decorative shape (accent bar / rule / line) crossing through text (e.g., v4 p.1 cover where the accent_rule cut through the italic subtitle) → cause is a hand-computed `top=` for the bar that landed on the text region → fix by deleting the manual bar and letting `h.title_block(accent_rule=True)` place its rule for slide titles, or for non-title accents use `h.pull_quote` whose bar tracks its text. Any of these = automatic FAIL regardless of other scores. |
| Visual hierarchy | Is the focal point obvious within 1 second? |
| Whitespace | Does the slide breathe, or is it crowded? |
| Alignment | Are elements on an implicit grid? (no rogue offsets) |
| Typographic discipline | Type hierarchy clear; ≤ 4 sizes; consistent? |
| Color discipline | ≤ 3 colors, used semantically? |
| Visual storytelling | Is there a story device (contrast, progression, arrow), or is it a static composition? |
| **Density** (todo 011) | If this is a *content* slide (not title / chapter divider / qa), does it have ≥ **25** shapes? Toy density (single pattern call ≈ 10 shapes; pattern + chrome ≈ 15) on a slide with proposal-grade content = automatic FAIL. Rewrite **bespoke** referencing `reference_corpus/proposal_dense.png` (~50 shapes) or `personnel_equipment.png` (~60 shapes) — Read those PNGs + their source in `reference_corpus/generate.py` before the rewrite. |
| **Chrome** (todo 011) | Does the slide carry `h.deck_chrome` (eyebrow + footer + page number)? Content slides without chrome look orphaned in the deck. Title slide / chapter divider are exempt. |

For each category that scores < 4: write one specific complaint
("S3's headline is centered, killing the asymmetric tension a thesis
slide needs") + the fix ("left-align the headline at col=1 span=8,
leave col=9-12 empty for breathing room"). Then call
`update_slide(slug, deck_id, slide_id, code=<rewritten snippet>)`.

When a category will not come up after several rewrites, the slide's design
is wrong rather than its code: go bespoke (see SKILL.md "Bespoke is the
default") instead of editing the same snippet again. If you end the pass with
a category still weak, say which one in the user summary — an unsaid weakness
is one the user cannot ask you to fix.

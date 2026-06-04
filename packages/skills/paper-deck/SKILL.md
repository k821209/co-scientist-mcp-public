---
name: paper-deck
description: Build a presentation deck from a paper. Pick a theme or invent one; outline slides to match audience + duration; draft per-slide content + speaker notes; register every slide in Firestore so the dashboard's Presentation tab can pick it up. Use when the user says "make a deck," "presentation," "lab seminar slides," "talk slides," "poster outline."
---

# /paper-deck

**Triggers:** "build slides from this paper," "make a 20-minute lab
talk," "deck for the Nature poster," "slides for the conference,"
"presentation outline."

## What it does

Turns a manuscript into a structured deck:
- One `decks/{deck_id}` doc holding the **concept** (palette,
  typography, motif) — the single source of visual unity.
- N `decks/{deck_id}/slides/{slide_id}` docs, each with role, title,
  body, prompt, MANDATORY speaker notes, optional code, and a
  `render_mode` declaring how it'll be visualized.

Rendering (slide PNGs, PPTX export) is a separate later step (Phase
3). This skill produces the **drafted** deck — content + structure +
unity header — ready for rendering.

## Hard rules

1. **Speaker notes are MANDATORY** on every non-title slide. Empty
   notes mean the presenter wings the take-home → defeats the purpose.
2. **Concept first, slides second.** The deck's `concept` field
   (palette + typography + motif) is the unity header that every
   slide's `prompt` field inherits. Never write a slide whose prompt
   has bare color names — use placeholders like `{accent}` /
   `{display_font}` that materialize at render time against the
   concept.
3. **Don't fabricate figure references.** If the paper has 2 figures,
   you can't have 5 paper-figure slides. Cap result slides at
   `len(list_figures(slug))`.
4. **`add_slide` then `renumber_deck` once.** Don't renumber by hand —
   the doc IDs encode the original number; renumber updates the
   `slide_number` field, the IDs stay.
5. **Native-language flow when the audience is non-English** (todo 001).
   Detect the audience language from `audience`, the user's prompt, or
   the deck concept. When it's Korean / Japanese / Chinese / etc.:
   - Draft *natively* in that language. Do **not** write English first
     and translate — that produces translation-ese a native reader
     spots immediately.
   - Keep English **only** for field-standard abbreviations (GWAS,
     BLUP, MCP, F4, GO, etc.). Translate everyday English nouns to the
     target language (shortcut → 지름길, process → 과정, …).
   - Use the target language's own punctuation conventions. In Korean,
     prefer colons and natural sentence breaks over em-dash chains
     (`X — Y → Z` reads as machine-translated English).
   - Keep sentence endings **consistent** within a slide (Korean: all
     `~합니다` or all `~한다`, not mixed).
   - Self-check: "Could a native speaker mentally reverse-translate
     this to English word-for-word?" If yes, rewrite before delivery.

## Flow

### 1. Pull paper context

```
paper = mcp__co_scientist__get_paper_state(slug)
figs = mcp__co_scientist__list_figures(slug)
tabs = mcp__co_scientist__list_tables(slug)
prep = mcp__co_scientist__prepare_export(slug)   # for warnings
```

If `prep["warnings"]` shows placeholders or unresolved DOIs, ask the
user whether to proceed or fix first.

### 2. Initialize the deck (idempotent)

```
deck = mcp__co_scientist__create_deck(
  slug,
  title="<presentation title>",
  audience="<lab seminar | Nature poster | conference plenary | …>",
  duration_min=<minutes>,
  theme="<theme_slug>" or None,
  aspect_ratio="16:9",   # "16:9" (default) | "16:10" | "4:3"
  deck_id="<short-slug>" or None,   # auto-derived from title if omitted
)
```

`create_deck` is idempotent — calling with the same `deck_id` returns
the existing doc unchanged. Safe to re-run.

### 3. Draft the concept

Two modes:

**A. With theme**: pick from preset slugs:
- `classical-academic` — serif body, navy + gold accents, dense data
- `minimal-modern-academic` — sans body, cool grey + one accent, lots of whitespace
- `mono-chrome-scholarly` — black/white/grey, hairline rules, prose-heavy
- `data-botanical` — earth tones, organic shapes (plant biology talks)
- `tricolor-brief` — red/yellow/black, 3-min lightning talks

Write a SHORT narrative-arc concept and call:

```
mcp__co_scientist__update_deck(
  slug, deck_id,
  concept="""
    Theme: minimal-modern-academic
    Arc: question → data → answer → caveat → what's next
    Motif: one accent color used only for the figure of merit on every slide
  """,
)
```

**B. Without theme**: invent your own concept. Spell out:

```
mcp__co_scientist__update_deck(
  slug, deck_id,
  concept="""
    Palette:
      bg: #fafaf7  surface: #ffffff  text: #1a1a1a  accent: #b58900
      muted: #6c757d  secondary: #2e7d32  highlight: #ee5500
    Typography:
      # English-only audience: Inter is fine. For ANY deck whose audience
      # is Korean / Japanese / Chinese (or whose body text mixes scripts),
      # use the matching Noto Sans CJK family — its Latin glyphs are co-
      # designed to share metrics with the CJK script. Pretendard's Latin
      # is taller / heavier than its Hangul and creates a visible seam in
      # mixed-script body text (todo 008 §B).
      #   Korean   audience: display: Noto Sans KR  body: Noto Sans KR
      #   Japanese audience: display: Noto Sans JP  body: Noto Sans JP
      #   Chinese  audience: display: Noto Sans SC  body: Noto Sans SC
      display: Inter Bold     body: Inter Regular     mono: JetBrains Mono
    Type scale:
      # legacy keys (still honored)
      title: 32  head: 26  body: 20  line_spacing: 1.22
      hybrid_body: 18  hybrid_head: 22  cover_title: 40  caption: 12
      # semantic role keys (canonical — prefer these in new code; todo 004 §E)
      display_chapter: 56  display_cover: 48  display_hero: 44
      headline_section: 28  title_slide: 32
      body_large: 22  body_standard: 20  body_small: 16
      label_tag: 12  label_caption: 12  scale_ratio: 1.25
    Motif:
      a single thin horizontal rule under each title;
      a recurring small icon (#b58900) marking the figure-of-merit line
    Design language:
      Grid: 12 columns, 8pt vertical rhythm, Inches(0.6) side margins.
      Whitespace: >= 25% of each slide reads as empty — leave breathing room.
      Max 4 distinct type sizes per slide; type sizes only from `type_scale`.
      Max 3 colors per slide: accent + foreground + one neutral.
      Visual storytelling: every section opener (Era I/II/III) uses a
        chapter-divider pattern distinct from interior slides.
      Iconography: leave room for accent icons (filed for follow-up,
        todo 004 §C); for now use accent-colored shapes as visual anchors.
    # Arc is the narrative spine YOU choose for THIS talk. Don't copy
    # the line below — derive it from the paper. Example arcs below;
    # remix freely.
    #   "question → data → answer → caveat → next"      (lab seminar)
    #   "why → what → how → who → when → take-home"     (proposal pitch)
    #   "context → finding → mechanism → caveat → so-what"  (single paper)
    Arc:
      [the arc that fits THIS paper / talk; pick one or write your own]
  """,
)
```

The `Type scale:` block is **optional** — unspecified keys fall back to
defaults (title 32 / head 26 / body 20 / line_spacing 1.22 / cover 40).
Override any of them per deck:
- **Smaller body** (16–18pt) when slides are dense and projected close.
- **Larger title** (36–40pt) when the audience is at the back of a room.
- **Tighter line_spacing** (1.1–1.15) for code-heavy slides.

Avoid going below 14pt — the export's auto-shrink (TEXT_TO_SHAPE) will
already step down when individual slides overrun.

**Mixed-script typography** (todo 008 §B). When the deck's body text
mixes Latin and CJK in the same paragraph (typical for Korean academic
talks that use English jargon like "BLUP", "GWAS", "MCP"), the
**Latin glyphs need to share metrics with the CJK script** or the two
read as collaged from different fonts. Google's **Noto Sans** pan-CJK
families do this by design — Noto Sans KR / JP / SC ship Latin
glyphs co-designed with the matching Hangul / Kana / Hanzi. Pretendard
and Inter look great in isolation but their Latin glyphs are taller
and heavier than the Hangul they sit next to, so "MCP가 다리" reads
with a visible seam between "MCP" and "가". The default for any non-
English audience should be the matching Noto Sans family.

The `Design language:` block is the deck's **design constitution** —
free-text rules every slide answers to (todo 004 §G). Not parsed by
the renderer; it's a contract you write to yourself as the slide
author. When you draft each slide's `code`, check it against this
block. Defaults to use if you don't write one:
- 12-column grid, 8pt vertical rhythm
- ≥ 25% whitespace per slide
- ≤ 4 type sizes, ≤ 3 colors per slide
- Section openers use a distinct (chapter-divider) layout from
  interior slides

### 4. Outline slides

> ⚠️ **Derive the outline from YOUR paper, not from a template.**
> There is NO "standard slide sequence" — different talks have
> wildly different shapes. A funded-grant proposal looks nothing
> like a lab seminar, which looks nothing like a chapter divider
> for a textbook. Read the paper's `prepare_export` output + the
> figures + tables, decide what story THIS paper tells, and build
> the outline that fits THAT story. The reference corpus and the
> role enum are *menu items*, not a default deck shape.

**Roles available** (pick whatever fits YOUR story; don't force the
full menu):

`title` · `outline` · `background` · `hook` · `thesis` · `section`
· `question` · `method` · `result` · `figure` · `image` · `content`
· `discussion` · `conclusion` · `qa` · `custom`

Some example deck shapes (NONE of these is *the* canonical shape —
pick or remix based on the talk type):

- **Lab seminar (20 min) on a single paper.** Title → background
  (1) → method (1) → result (1 per main figure, clamp to actual
  figure count) → discussion (1) → take-home (1).
- **Conference talk (15 min) on a methodology.** Title → motivation
  (1–2) → method (2–3) → key result with figure (1) → conclusion (1).
- **Grant proposal pitch (10 min).** Title → why / problem (1) →
  what we propose (1–2) → how / methodology (2–3) → who / capability
  (1) → when / timeline (1, often a Gantt) → take-home (1).
- **Departmental review (30 min).** Title → outline → 3 chapter
  dividers each followed by 2–3 content slides → discussion → qa.
- **One-figure result deep-dive (5 min).** Title → context (1) →
  full-bleed figure (1) → take-home (1).

The role names + counts in those examples are *illustrative*. Mix,
drop, repeat, invent. `role="custom"` is there because nothing else
might fit your slide's purpose; use it freely.

**Duration math**: each content slide ≈ 1–2 minutes (more for dense
proposal pages; less for chapter dividers). A 20-min talk lands at
~12–15 slides; a 5-min lightning at 3–5. Don't pad to meet a count.

**Don't commit to render_mode here (todo 010).** Outline is the
*content-brief* step — each slide gets `role + title + body intent +
speaker notes`. The design decision (will this be a code snippet?
a full-bleed figure? a 2-column compare? a Gantt?) is made in **§5
per slide**, when you've actually thought about the slide's content
and decided what layout serves it. `render_mode` defaults to None at
this stage; the exporter / renderer infers it from whichever fields
end up populated in §5 (regions → hybrid, code with python-pptx
signals → code, figure_number → paper-figure, prompt → ai-image,
otherwise → text). Pass an explicit `render_mode` only when you want
to lock the strategy at outline time (rare).

### 4.5. AI image opportunities — decide at outline (todo 015)

While you're still in outline mode, sweep the slide list and decide
which slides would visibly improve with a generative AI image. This
is a separate pass from §5 design — get the decisions made BEFORE
you start authoring code, so the agent isn't re-deciding mid-author.

**Step 1 — set the deck-wide image style ONCE.** Call
`update_deck(slug, deck_id, image_style="<style hint>")` near the
start of the deck. The exporter prepends this string to every
ai-image region's prompt, so all generated images share one visual
treatment without you repeating the style hint on every slide. A
useful template:

```
<medium>, <lighting>, <subject framing>, <mood>, no text, no captions
```

Examples that work well together for a single deck:

- *"minimalist watercolor on cream paper, soft natural morning light,
  Korean researcher aesthetic, muted earth tones, no text"*
- *"isometric line illustration on warm cream background, single
  accent color matching deck accent (#7A2A1A), generous whitespace,
  no labels, no logos"*
- *"editorial photograph, shallow depth of field, available light,
  shot on 35mm film, neutral grading, no text overlays"*

If you skip this step, regions still render but with no shared
treatment — each scene comes out with whatever default style the
generator picks, which looks incoherent across the deck.

**Step 2 — sweep each slide for image opportunity.** For each
slide, ask one question: *would an AI image visibly improve this
slide's narrative impact?* Rough heuristics by role:

| Role / shape | Image candidate? | Why |
|---|---|---|
| `title` (cover) | **REQUIRED when image_gen is configured** — full-bleed | The cover is what the audience sees for the longest. Text-only covers read as placeholder slides; a single full-bleed evocative image with the title overlaid is the difference between "draft" and "finished". Do not skip this. |
| `chapter_divider` / hook / vignette | **REQUIRED when image_gen is configured** — full-bleed or large top-band | Same reasoning — these are pause beats in the narrative where the audience expects a visual breath. Text-only chapter dividers feel like missing slides. |
| narrative / story-time content slide | **Often** | Anywhere you'd want to "show, not tell". |
| concept / abstract idea (e.g., "Protocol의 도착", "무엇이 가로막는가") | **Sometimes** | A metaphorical image can anchor an abstract concept — but only if you can name the metaphor cleanly in 1 sentence. Otherwise skip. |
| `method` step-by-step / `result` numbers / table | **Rarely** | The data IS the message; an image dilutes it. |
| `qa` / closing thanks | **Sometimes** | A small closing image can land the tone. |

> **REQUIRED-when-configured (todo 017):** If the deck has
> `image_style` set (i.e., user expected images), then cover + every
> chapter divider MUST have an ai-image — there is no "would an
> image improve this" judgment call for those roles. The judgment
> is reserved for the other rows in the table. If `image_gen` isn't
> wired (Pro feature) AND user expected images, surface a single
> note in §8 ("AI image generation isn't configured; cover and
> chapter dividers fell back to text-only") rather than silently
> producing a deck the user will reject.

For every "yes", DRAFT the scene prompt in 1–2 sentences (no style
hint — that comes from `image_style` automatically). Examples:

- cover slide for "2036년 김 박사의 화요일" → `"a Korean plant
  breeding researcher at their desk in early morning, opening a
  laptop, a single hot drink steaming on the desk, soft window
  light from the right"`
- concept slide "Protocol 의 도착" → `"a clean handshake between
  two abstract robotic forms across a shared cable, symbolic, mid-
  air"`
- chapter divider "무엇이 가로막는가" → `"five concentric layers
  of fabric overlapping with a small gap between each, top-down,
  symbolic of friction"`

**Step 3 — wire the placeholder.** For each slide that needs an
image, decide whether the image is the WHOLE slide or a REGION:

- **Whole-slide image** (covers, full-bleed dividers): `add_slide(
  …, render_mode="ai-image", prompt="<scene>", …)`. No regions
  needed.
- **Image alongside text** (most narrative content slides): leave
  `render_mode` unset, then call `set_slide_regions(slug, deck_id,
  slide_id, regions=[{"render_mode": "ai-image", "prompt":
  "<scene>", "x": 0.05, "y": 0.15, "w": 0.45, "h": 0.7}])` with a
  region box that matches your text layout (text on the OTHER half
  of the slide).

After §5 authoring + §6 render, the renderer materializes every
region — Pro-gated; cost is charged at render time. If the user
isn't on a Pro plan, the renderer will error on ai-image regions
and the rest of the deck still exports — surface this in §8.

**When NOT to add an image.** If you'd struggle to write a clean
1-sentence scene prompt, skip the image — a generic prompt produces
generic stock-image output that drags the deck down. Better to
leave the slide text-only with strong typography than fill it with
a weak image.

### 5. Design + author each slide

> **Content slides are BESPOKE by default — target ≥ 25 shapes per
> slide, composed from `h.*` primitives.** Patterns (`p.*`) are
> narrow shortcuts for *exact-fit* cases only (a 3-step workflow with
> nothing else on the slide; a single chapter divider). When the
> content has any of the §5a "Go bespoke when…" signals — proposal-
> grade density, multi-section structure, two compositions side-by-
> side, etc. — **do NOT call a single pattern**. Compose directly
> from `h.text` + `slide.shapes.add_shape` + `h.deck_chrome` like
> `reference_corpus/proposal_dense.png` and `personnel_equipment.png`.
> Pattern-fits-everything is the toy-density failure mode (todo 011).

Now you go slide-by-slide. For each slide:

1. **Read the brief** (role + title + body intent + notes from §4).
2. **Decide the design** based on the content. Default to bespoke
   composition; only fall back to a single pattern when the content
   is a clean exact-fit case (see §5a's "Use only when…" criteria).
   `reference_corpus/proposal_dense.png` and `personnel_equipment.png`
   are the canonical density references — Read them before authoring
   any non-trivial content slide.
   (`chapter_divider` / `metric_tile_row` / `flow_pipeline` /
   `figure_full` / `gantt_chart` / …). If no pattern fits, **go
   bespoke** — compose with `h.text` / `h.card` / `h.icon` /
   `h.table` / `slide.shapes.add_shape` (§5a's "patterns are a
   starting point, not a ceiling" rule).
3. **Author the slide** by setting the field(s) that fit your design.
   The render_mode is **inferred** from which fields you populate —
   don't pass `render_mode` unless you want to lock it explicitly.

| What you authored                              | Mode inferred at export |
| ---------------------------------------------- | ----------------------- |
| `code` with `h.*` / `p.*` / `slide.shapes` etc. | `code`                  |
| `figure_number`                                | `paper-figure`          |
| `prompt` (no image yet)                        | `ai-image`              |
| `regions[]` (via `set_slide_regions`)          | `hybrid`                |
| `code` looking like an external PNG script     | `code-shape`            |
| Just `title + body`                            | `text`                  |

So the simplest add+design loop is:

```python
# Step 4 produced the brief; Step 5 designs + authors:
mcp__co_scientist__update_slide(
  slug, deck_id, slide_id=...,
  code="""
    h.accent_stripe(slide, palette=palette, sw=sw)
    h.title_block(slide, title, palette=palette, fonts=fonts,
                  type_scale=type_scale, sw=sw, sh=sh)
    h.deck_chrome(slide, palette=palette, fonts=fonts,
                  type_scale=type_scale, sw=sw, sh=sh,
                  eyebrow='HOW · 추진 방법', page_number=5, total=13,
                  footer='기러기류 마커 발굴 · ㈜디보')
    p.flow_pipeline(slide, items=[...],
                    palette=palette, fonts=fonts,
                    type_scale=type_scale, sw=sw, sh=sh)
  """,
)
# render_mode auto-inferred to "code" — no commitment made at outline time.
```

`add_slide` itself stays simple:

```
mcp__co_scientist__add_slide(
  slug, deck_id,
  slide_number=N,
  role="<role>",
  title="<slide title>",
  body="<content-brief lines — what the slide should say>",
  notes="<MANDATORY speaker notes — what you'll say>",
  # render_mode / code / prompt / figure_number all OPTIONAL —
  # populate via update_slide once you've decided the design (§5).
)
```

**Prompt template rule**: when you do set `prompt` (for ai-image), it
MUST start with the unity header using placeholders. Example:

> `"{accent} accent. {display_font} typography. Minimal modern academic
> theme. Body: …"`

Never hardcode `"navy blue"` or `"Inter"` — write `{accent}` /
`{display_font}` so theme switching is a no-op rebuild.

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
            border_color=None, border_pt=0)                # for dark/light
            # `items` is a vstack-style list[{text,         # callout boxes
            # size_pt?, color?, bold?, italic?, ...}]      # instead of drawing
            # OR pass headline= / body= shortcuts.          # rect+text manually
            # text_color auto-picks foreground/surface     # (todo 014 callout-
            # by background luminance.                      # fix)
  h.text(slide, content, *, left, top, width, height,    # one-call textbox
         palette, size_pt=20, color=None, bold=False,
         italic=False, align=None, anchor=None,
         line_spacing=1.22, autofit=True, min_pt=10,
         fonts=None)                                      # todo 007 §D
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
                sw, sh, eyebrow="", page_number=None,     # + page number
                total=None, footer="")                    # (todo 009 B)
  h.table(slide, *, headers, rows, left, top, width,      # native pptx TABLE
          height, palette, fonts, type_scale,             # (todo 009 C)
          first_col_emphasis=False)
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
                palette, fonts, type_scale, sw, sh)
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
| `palette` | `{"accent": RGBColor, "background": RGBColor, "foreground": RGBColor, "surface": RGBColor}` |
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
| `h.text(slide, content, *, left, top, width, height, palette, size_pt=20, color=None, font_name=None, bold=False, italic=False, align=None, anchor=None, line_spacing=1.22, autofit=True, min_pt=10, fonts=None)` | one-call textbox | DX helper: drops the 5-line `add_textbox + text_frame + paragraph + run + font` ceremony to a single call. `color` defaults to `palette["foreground"]`; pass `palette["muted"]` for captions, `palette["accent"]` for emphasis. Autofit-shrinks Korean-aware. (todo 007 §D) |
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
| `p.title_slide(slide, *, title, subtitle="", eyebrow="")` | **owns slide** | Deck opener / cover at slide 1. Centered eyebrow + title + accent rule + subtitle. Distinct from `chapter_divider` (mid-deck). | `title`, `subtitle` (author/venue/date), `eyebrow` (≤ ~24 chars) |
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
mcp__co_scientist__add_slide(
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
mcp__co_scientist__add_slide(
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

**Patterns are a starting point, not a ceiling.** (todo 009.) The 14
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
re-generation; re-positioning a region doesn't either. Set
`render_mode="code"` BEFORE calling `set_slide_regions` to keep the
mode (otherwise it snaps to `hybrid` for backwards compatibility).

**Box overlap won't happen** — every text emitter in `h.*` and every
`_emit_text` inside `p.*` calls `h.autofit_pt` to shrink the font
before rendering when content would overflow. PowerPoint's
TEXT_TO_SHAPE autoshrink kicks in on top of this; soffice (our
preview pipeline) doesn't fully honor that, so the autofit ensures
the PNG matches the slide. The minimum fall-back is ~12pt for body,
~16pt for headings — if you see autofit hitting min, the right fix
is to **drop content**, not to expand the box.

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

### 5c. Compositional effects — why arrangement matters (todo 006)

Same content lands differently depending on arrangement. The patterns
encode these rules; when you build a custom layout, mirror them.

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

### 5b. Hybrid slides — bullets + figure, or several images (regions)

Two distinct uses of `set_slide_regions` / hybrid:

**(a) Title + bullets + one figure** — the most common mixed slide.
Put the bullets in `body` (markdown) on `add_slide`, then set ONE
image region for the figure on the right:

```
mcp__co_scientist__set_slide_regions(
  slug, deck_id, slide_id,
  regions=[
    { "render_mode": "ai-image",
      "prompt": "{accent} schematic of 2-week pipeline vs 30-sec MCP query",
      "x": 0.54, "y": 0.22, "w": 0.42, "h": 0.65,
      "fit": "contain" },
  ],
)
```

The slide's `body` renders as native bullets in the LEFT half; the
image region renders in its box on the right. The bullets stay
editable text in the .pptx; only the figure is an image.

**Keep the body tight on hybrid slides.** The body box is half-width,
so each bullet wraps onto more lines than on a full-width `text`
slide. As a rule, aim for ≤ 4 bullets, each ≤ 2 wrapped lines (i.e.
~80 Korean characters / 120 English characters). Dense bullets will
overflow the box even at the reduced 20pt body type.

**(b) Several images on one slide** — a generated schematic next to a
data plot next to a manuscript figure:

```
mcp__co_scientist__set_slide_regions(
  slug, deck_id, slide_id,
  regions=[
    { "render_mode": "paper-figure", "figure_number": 2,
      "x": 0.05, "y": 0.22, "w": 0.42, "h": 0.62, "fit": "contain",
      "caption": "Fig 2 — measured response" },
    { "render_mode": "ai-image", "prompt": "{accent} pathway schematic …",
      "x": 0.52, "y": 0.22, "w": 0.43, "h": 0.62, "fit": "contain",
      "caption": "Proposed mechanism" },
  ],
)
```

- This forces the slide to `render_mode="hybrid"`. Regions get ids
  `r1..rN` in order.
- `x/y/w/h` are **fractions of the slide** (0–1) — keep `y ≥ ~0.2` so
  regions clear the title. Useful layouts:
  - **2-up**: `r1` x=0.05 w=0.42, `r2` x=0.52 w=0.43 (both y=0.22 h=0.62)
  - **big-left + 2 stacked right**: `r1` x=0.05 y=0.22 w=0.55 h=0.62;
    `r2` x=0.64 y=0.22 w=0.31 h=0.29; `r3` x=0.64 y=0.55 w=0.31 h=0.29
  - **2×2**: four 0.42×0.34 boxes at x∈{0.05,0.52}, y∈{0.22,0.60}
- Each region has its own `render_mode` (`ai-image` / `code-shape` /
  `paper-figure`) and source. A region can't itself be `hybrid`/`text`.
- **`fit`** decides how the image fills its box:
  - `contain` (default) — letterbox, never crop. Use for figures,
    charts, tables, schematics — anything where cropping loses data.
  - `cover` — fill the box, crop the overflow. Use for an eyecatch /
    decorative / photo region where edge loss is fine.
- `render_region` records the rendered image's real pixel size
  (`image_width` / `image_height`) on the region — handy if you want
  to nudge a box to match the image's true aspect on a second pass.
- At export each region becomes a **separate, individually editable
  PPTX picture** — the user can nudge them in PowerPoint.

### 5d. Reference corpus — what good renderings look like (todo 004 §F)

The skill ships with a curated corpus of exemplar slides at
`reference_corpus/` (one PNG per canonical pattern + `manifest.json`).
Each entry records the pattern name, the content the example uses, and
a do / don't pair the agent should mirror in its own slides.

**Recommended flow when authoring a `code` slide**:

1. Decide whether the slide is one of the mechanical structures (§5a)
   or — far more often — a bespoke composition.
2. Read `packages/skills/paper-deck/reference_corpus/manifest.json`.
   For a mechanical layout, confirm the canonical example exists; for
   a bespoke slide, study `proposal_dense` / `personnel_equipment`.
3. Read the matching PNG (`Read("packages/skills/paper-deck/reference_corpus/<name>.png")`)
   — Claude is multimodal, so the agent SEES what a good rendering
   looks like before authoring its own.
4. Follow the manifest entry's **do**; avoid its **dont**.
5. Author the `code` snippet against your own content. Run the
   critique loop (§9) against the result and the reference side-by-
   side; rewrite if your rendering diverges visually from the
   exemplar's discipline.

The corpus covers the 7 mechanical layouts — `title_slide`,
`chapter_divider`, `title_and_image_grid`, `figure_full`,
`metric_tile_row`, `flow_pipeline`, `gantt_chart` — plus two
bespoke density exemplars (`proposal_dense`, `personnel_equipment`)
that show what hand-composed body slides look like. Regenerate with:

```bash
PYTHONPATH=apps/local-mcp python \
  packages/skills/paper-deck/reference_corpus/generate.py
```

The corpus is checked in (small PNGs), so the agent has it locally
without a network round-trip. Each PNG is < 100 KB.

### 6. Renumber once at the end

After adding all slides:

```
mcp__co_scientist__renumber_deck(slug, deck_id)
```

Packs `slide_number`s tightly starting at 1, even if you added them
out of order.

### 7. Mark drafted

```
mcp__co_scientist__update_deck(slug, deck_id, status="drafted")
```

Status flow: `draft` (initial) → `drafted` (slides + notes + prompts
done, ready for rendering) → `rendered` (Phase 3, slide PNGs + PPTX
exist).

### 8. Tell the user

Summary: "Deck `{deck_id}` drafted with N slides at status='drafted'.
Run /paper-deck again to iterate, or wait for Phase 3 rendering to
turn this into slide images + .pptx."

### 9. Critique pass — vision review of the exported deck (todo 004 §A)

After `export_deck_to_pptx` the result includes a `slide_pngs[]` list:
one PNG per slide rendered from the sibling PDF (so what the agent
sees is exactly what an opener of the .pptx / .pdf will see). Use them
to **score and rewrite weak slides** before declaring the deck done.

**First: check `result["overlap_warnings"]`** (todo 016 —
render-time text-on-text detector). It's a list of
`{slide_number, slide_id, pairs: [{a_preview, b_preview,
overlap_ratio}]}` entries — any slide that appears here has
textbox bounding boxes intersecting by ≥20% of the smaller box's
area, which means text is visibly rendered on top of other text
in the export. These are **automatic FAIL regardless of the visual
rubric**. For each entry, find the two textboxes in the slide's
`code` (the `a_preview` / `b_preview` strings are the first line
of each box's text), and replace the manual `h.text(...)` /
`add_textbox(...)` calls with `h.vstack(...)` for stacked content
in a single column, or fix the y-coordinates so the boxes don't
overlap. Re-export until `overlap_warnings == []`.

**Also check `result["bounds_warnings"]`** (render-time off-slide
detector). Same shape as above but each entry is `{slide_number,
slide_id, shapes: [{preview, sides, over_in}]}` — `sides` names which
edges the text box runs past (`left`/`top`/`right`/`bottom`) and
`over_in` is how far, in inches. Any slide here has text spilling off
the canvas (e.g. a row of prompter/CDS boxes or a stacked proportion
bar laid out past the right edge). **Automatic FAIL.** The usual cause
is a width budget computed against the full slide width `sw` instead of
the *content* width. For any horizontal run of boxes/segments + gaps:
the budget is `content_w = sw - left_margin - right_margin` (typically
`sw - Inches(1.2)`), and `sum(segment widths) + sum(gaps)` must be
`≤ content_w`. Lay segments out starting at `left = left_margin` and
size each as a fraction of `content_w` — never start at a margin and
then add full-width segments. Re-export until `bounds_warnings == []`.

```
res = mcp__co_scientist__export_deck_to_pptx(slug, deck_id)
for png in res["slide_pngs"]:
    # Read the PNG via the Read tool — Claude is multimodal and will
    # see the actual slide rendering.
    Read(png["local_path"])
    # Score it (in your head / scratchpad) against the rubric.
    # If any category < 4, rewrite the slide's `code` and update_slide.
```

**Rubric** (each scored 1–5; a slide passes when all ≥ 4):

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

**Loop**: re-export, re-score, max 3 rounds. After round 3, accept
the deck as-is and surface the remaining weak categories in the user
summary so they know what to ask for next.

**When `slide_pngs_skipped` is True**: the export couldn't produce
PNGs (no LibreOffice / no PyMuPDF on this machine). Skip the critique
loop and tell the user — they can install soffice + pymupdf to enable
it.

## Acceptance test

`/paper-deck <slug> "lab seminar" 20` should produce:
- One deck doc with concept + theme + audience + duration_min
- 9 default-role slides (title, outline, background ×2, method,
  result × `min(figs, 4)`, discussion, conclusion, qa) — adjusted to
  not exceed the paper's figure count
- Every slide has `notes` non-empty
- Every slide's `prompt` starts with the unity header placeholders
- `status == "drafted"` on the deck

## Common follow-ups

- "Change the theme to data-botanical" → `update_deck(theme=...,
  concept=...)`. Slides don't need to change — their prompts use
  placeholders that re-materialize against the new theme.
- "Cut to 10 minutes" → drop discussion + outline; verify with the
  user before deleting any slide that has good `notes`.
- "Reorder so methods come after background" → `update_slide` each
  affected one with new `slide_number`, then `renumber_deck`.

## Rendering + export (Phase 3 — shipped)

After every slide has its body / prompt / notes filled:

```
mcp__co_scientist__render_deck(slug, deck_id)
```

This walks every slide and:
- `text`         → nothing to render; it becomes native PPTX text at
                   export. Returned in `skipped[]` with that reason.
- `paper-figure` → copies the existing figure blob into a slide image
- `ai-image`     → substitutes `{accent}` etc. from `deck.concept`,
                   calls `generate_image`
- `hybrid`       → renders every region it can (`paper-figure` /
                   `ai-image` regions); `code-shape` regions land in
                   `skipped[]` for you to do via `render_region`.
- `code-shape`   → returned in `skipped[]` because the MCP can't safely
                   exec arbitrary Python. Run the slide's `code` block
                   yourself locally (matplotlib/seaborn/etc. into a
                   PNG), then pass that path back:

```
mcp__co_scientist__render_slide(
  slug, deck_id, slide_id,
  local_path="/abs/path/to/slide-3.png",
)
```

For a **hybrid** slide's `code-shape` region, render that one region:

```
mcp__co_scientist__render_region(
  slug, deck_id, slide_id, region_id,   # e.g. region_id="r2"
  local_path="/abs/path/to/region.png",
)
```

`paper-figure` / `ai-image` regions need no `local_path` — the MCP
renders them (an ai-image region's aspect ratio is matched to its
box). A hybrid slide is "done" when every region has an image.

Once every non-`text` slide has an `image_blob_path`, the deck's
`status` flips to `"rendered"`. To export from Claude Code:

```
mcp__co_scientist__export_deck_to_pptx(
  slug, deck_id,
  output_path="~/decks/my-talk.pptx",
)
```

Export behavior:
- **Image slides** embed the rendered PNG, aspect-fitted and centered.
- **`hybrid` slides** get a themed title frame plus each region placed
  as its own separately-editable PPTX picture at its `x/y/w/h` box,
  with an optional caption.
- **`text` slides** (and any slide still missing a render) become
  NATIVE editable text — title + bullets — themed from the concept's
  `accent` / `bg` / `text` colors. Not a picture: the user can edit
  the words in PowerPoint.
- Page size follows the deck's `aspect_ratio`.
- The exported **`.pptx` opens in Keynote as well as PowerPoint /
  LibreOffice.** `export_deck_to_pptx` strips the stale
  `<p:sldSz type="screen4x3">` attribute python-pptx leaves after a
  16:9 resize, and registers `<p:notesMasterIdLst>` (python-pptx adds
  a notesMaster relationship for speaker notes but never registers it —
  a dangling relationship Keynote refuses). Do NOT tell the user the
  PPTX is Keynote-incompatible or steer them to the PDF for that
  reason; just hand them the `.pptx`.
- A sibling **`.pdf`** is produced when LibreOffice (`soffice`) is
  installed — a convenience for read-only sharing, NOT a Keynote
  workaround.

Returns `{ local_path, blob_path, pdf_local_path, pdf_blob_path,
pdf_skipped, aspect_ratio, slide_count, image_slides, text_slides,
hybrid_slides, missing_renders }`. `missing_renders[]` is the non-text slides that
came out as text fallbacks because they weren't rendered yet — render
those and re-export. If `pdf_skipped` is true, tell the user to
install LibreOffice if they want the PDF.

python-pptx ships with the base install. LibreOffice is the only
optional extra (PDF sibling only).

## Addressing slide comments

Reviewers leave comments on individual slides from the dashboard's
Presentations tab — the deck analogue of manuscript review comments.

- `list_deck_comments(slug, deck_id)` — open slide comments, each tagged
  with `slide_number` / `slide_id` / `slide_title` (and an optional
  `region_id` pointing at one region of a hybrid slide). This is the
  deck's revision to-do list; check it at session start.
- For each comment: read it, revise that slide (`update_slide` /
  `set_slide_regions`), re-render if needed, then
  `resolve_deck_comment(slug, deck_id, slide_id, comment_id)` —
  `status="resolved"` if addressed, `"rejected"` if you and the user
  decide not to act on it.
- Re-export the deck once the slides are revised.

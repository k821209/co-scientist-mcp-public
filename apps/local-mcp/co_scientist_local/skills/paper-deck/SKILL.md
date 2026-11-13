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

Rendering (slide PNGs, PPTX export) comes after the deck is drafted —
content, structure, unity header — and is the last part of this skill
(`references/render-export.md`).

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
4. **`add_slide` inserts; use `reorder_deck` to move.** `add_slide` does a
   TRUE insert: inserting at number N shifts every existing slide at N or
   later down by one, so the new slide lands exactly at N. To insert
   "between 4 and 5", add at **5**. To append, use `len(list_slides)+1`.
   To *move/reorder* existing slides, call `reorder_deck(slug, deck_id,
   order=[id1, id2, …])` with the full slide-id list in the desired order
   (the deck analogue of `reorder_section`) — don't juggle add/delete.
   `renumber_deck` stays for packing gaps after deletes. On a big deck,
   call `list_slides(slug, deck_id, fields=["title", "role"])` to get a
   compact index (with ids) without the bulky `code`/`notes`.
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
6. **Iteration discipline — preview during work, export ONCE at the end.**
   While editing slides, use `preview_slide(slug, deck_id, slide_id)` — it
   renders just that slide to a PNG in seconds and updates the dashboard
   preview (same `preview_png_blob_path`), so the user sees changes live.
   `export_deck_to_pptx` re-renders the WHOLE deck (LibreOffice + a PNG per
   slide → tens of seconds to minutes); call it only when (a) the deck is
   done and you need the shareable .pptx/.pdf, or (b) the user asks to
   "export". Do NOT re-export after each edit. `render_slide` is only for
   when a region's image **prompt** changed — not for coordinate/size
   tweaks (the existing image stays; `preview_slide` composes it). See §9.
   **Verify, then confirm:** after a design change, a batch applying the
   same pattern across slides, or a large text edit, run `preview_slide`,
   `Read` the returned PNG yourself (check it visually + the code_errors /
   overlap / bounds / layout / placeholder warning lists), then ASK the
   user to confirm that slide before moving to the next one/batch — don't
   `update_slide` and silently move on. A one-character typo fix is exempt.
7. **The layout lint is a hard done-gate — zero warnings before a deck is
   "done".** Every `preview_slide` / `export_deck_to_pptx` return carries
   `overlap_warnings`, `bounds_warnings`, `layout_warnings`
   (shape-overlap · footer-overlap · uneven-card-heights · tiny-image ·
   inner-margin), `placeholder_warnings`, and `image_placement_warnings`
   (an uploaded/rendered region image the slide `code` never placed — it's
   auto-placed at the region's geometry as a fallback; position it explicitly
   with `h.image_region(id, …)` to clear the warning). These are not advisory —
   a deck with any of them is NOT finished. Fix the slide and re-preview
   until all lists are empty; only then present it as done. (`font_warnings`
   are host-font availability and may be tolerated — say so if you leave any.)
   This lint is heavily invested in specifically so no overlapping band,
   footer collision, or ragged card row ever ships unseen.

## Flow

### 1. Pull paper context

```
paper = mcp__scivo__get_paper_state(slug)
figs = mcp__scivo__list_figures(slug)
tabs = mcp__scivo__list_tables(slug)
prep = mcp__scivo__prepare_export(slug)   # for warnings
```

If `prep["warnings"]` shows placeholders or unresolved DOIs, ask the
user whether to proceed or fix first.

### 2. Initialize the deck (idempotent)

```
deck = mcp__scivo__create_deck(
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

### 3. Pick a style — SHOW THE GALLERY, LET THE USER CHOOSE

Before drafting the concept, **show the user the theme gallery and ask
which style they want** (don't silently default to one — that's how every
deck ended up looking the same). Each registered theme has a rendered
swatch under `reference_corpus/gallery/<slug>.png`; read
`reference_corpus/gallery/manifest.json` for the list, then present the
swatches (Read the PNGs) with a one-line vibe for each and ask the user
to pick a slug — or to say "surprise me / invent one," in which case you
choose. Only skip the ask if the user already named a style.

The six presets (all **fully specified in code** — see `THEME_REGISTRY`
in `deck_render.py`; a swatch PNG exists for each):
- `classical-academic` — serif body, navy + gold accents, dense data
- `minimal-modern-academic` — sans body, cool grey + one accent, whitespace
- `mono-chrome-scholarly` — black/white/grey, hairline rules, prose-heavy
- `data-botanical` — earth tones, organic/rounded shapes (plant biology)
- `tricolor-brief` — red/yellow/black, 3-min lightning talks
- `data-infra-console` — cool blue + teal, mono numerals, dark-header tables

### 3b. Draft the concept

Two modes:

**A. With theme (recommended).** Because the presets are now fully
specified in `THEME_REGISTRY`, a concept of **just** `Theme: <slug>`
already renders the complete look — palette, fonts, type scale, AND the
structural *motif* (top-stripe / title-rule / card treatment, applied
automatically to every slide). You only add a `Palette:` / `Typography:`
/ `Type scale:` block to OVERRIDE specific values; anything you omit
falls back to the preset. So the minimal, correct concept is often:

```
Theme: data-botanical
Arc: <the narrative spine for THIS talk>
```

`data-infra-console` is spelled out below for reference (it matches the
registry entry); you do NOT need to paste it — the slug alone is enough.
Reproduce it verbatim only if you want to hand-tune from it:

```
Palette:
  bg: #F7F8FA  surface: #FFFFFF  text: #161B22
  accent: #1F6FEB      # precise blue — protocol names + the figure-of-merit only
  secondary: #0E7C66   # deep teal — biology / cultivar / trait labels
  muted: #6B7280       # slate grey — captions, grid, footer
  highlight: #E8590C   # signal orange — ONE decisive number / bottleneck per slide
Typography:
  # Noto Sans CJK KR for display + body (shared Hangul/Latin metrics → no
  # mixed-script seam). Noto Sans Mono CJK KR for tool names / code / numerals /
  # markers / DB stats only.
  display: Noto Sans CJK KR   body: Noto Sans CJK KR   mono: Noto Sans Mono CJK KR
Type scale:
  title: 28  head: 22  body: 17  line_spacing: 1.30
  cover_title: 48  caption: 11  hybrid_head: 22  hybrid_body: 15
  display_cover: 48  headline_section: 28  title_slide: 28
  body_standard: 17  body_small: 14  label_tag: 11  label_caption: 11
Motif:
  Top accent_stripe + a thin accent rule under each title.
  Bottom chrome via h.deck_chrome: eyebrow (top-left section label, secondary
  mono) · footer (centered, muted) · page number (bottom-right). page_number
  defaults to the slide's own number — omit it. Exempt cover / closing /
  pull-quote slides from chrome.
Design language:
  Tables: header row = dark (foreground) bg + white bold text, body cells
    vertically centered, first column emphasized. Use
    h.table(..., header_fill="foreground", valign="middle",
    first_col_emphasis=True) — the default accent header is too low-contrast
    for this tone.
  Code / console blocks: a foreground-filled box, mono text, per-line color
    (keywords in accent), vertically centered. Use
    h.text_block(..., fill="foreground", mono=True, valign="middle",
    lines=[(code, accent_or_surface), ...]).
  Body copy in Korean (~합니다체); keep only field English abbreviations
    (MCP, LLM, marker, …) in English.
Writing rules:
  A slide title, a contents item, a question line, a card headline stands
    with no sentence before it. Three rules from `/paper-writing`, in the
    order they fail: no deictic without its name (§2d-quinque: 그게 →
    후보 목록의 상위 몇 개), no coined term where the measurement belongs,
    and — Korean — keep the subject and the object in every predicate line
    (§2d-quater-bis: "목록 맨 위가 실제로 맞는가" → "모델이 매긴 후보 목록의
    상위 몇 개가 실제로 그 기관에서 켜지는가"). Deleting 그 and stopping is
    the second defect dressed as a fix for the first.
image_style:
  "isometric technical line illustration on cool off-white, single deep-blue
  accent (#1F6FEB) with one teal data-color (#0E7C66), thin precise strokes,
  generous whitespace, no text/labels/logos/human faces"
  — set via update_deck(image_style=...). Full-bleed on cover + closing only.
```

Write a SHORT narrative-arc concept and call:

```
mcp__scivo__update_deck(
  slug, deck_id,
  concept="""
    Theme: minimal-modern-academic
    Arc: question → data → answer → caveat → what's next
    Motif: one accent color used only for the figure of merit on every slide
  """,
)
```

**B. Without theme** — the user declines the gallery and you invent the
concept: the palette, the type scale, and — for a deck whose body text is
Korean, Japanese or Chinese — fonts whose Latin glyphs share metrics with the
CJK script. All of it is `references/concept-without-theme.md`; read it before
writing a concept by hand.

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

### 4.9. One slide first — SHOW IT BEFORE YOU BUILD THE REST

The gallery in §3 settles the theme. It does not settle what THIS deck looks
like at this paper's density, and a deck authored in one pass comes back with
every slide the same shape — a correction then costs all of them instead of
one.

So author **one** content slide before any other: the one that carries the
most (a result with its figure, or the composed method diagram) — not the
title, which every theme makes look finished. Render it with `preview_slide`,
put the PNG in front of the user (`/show-image`), say in a line what the other
slides will share with it, and wait for a yes or a correction.

- A correction about the LOOK (density, type size, how figures sit, the
  accent) goes into the deck's `concept` with `update_deck`, not only into
  this slide — rule 2 above is why: the concept is what the remaining slides,
  and the next session, are built from.
- Then author the rest (§5). The approved slide is the bar; Read its PNG again
  before the critique pass in §9.

Skip this only when the user asked for the deck in one go without stopping,
when nobody is there to answer (a non-interactive run), when the deck is three
slides or fewer, or when you are revising a deck that already exists. Say in
the summary (§8) that it was skipped and why.

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
| `code` with `h.*` / `p.*` / `slide.shapes` etc. | `code` (beats regions)  |
| `figure_number`                                | `paper-figure`          |
| `prompt` (no image yet)                        | `ai-image`              |
| `regions[]` (via `set_slide_regions`)          | `hybrid`                |
| `code` looking like an external PNG script     | `code-shape`            |
| Just `title + body`                            | `text`                  |

   **Code beats regions, in either order.** A slide that carries *both* a
   python-pptx `code` snippet and `regions[]` resolves to `code` — the
   snippet places each region via `h.image_region`, whereas the `hybrid`
   path ignores `code` and would silently drop your text/shape overlay.
   This holds even if you explicitly set `render_mode="hybrid"` and add
   code later: the export auto-corrects `hybrid + code → code`. So you can
   `set_slide_regions` first then add code, or vice versa — same result.

So the simplest add+design loop is:

```python
# Step 4 produced the brief; Step 5 designs + authors:
mcp__scivo__update_slide(
  slug, deck_id, slide_id=...,
  code="""
    h.accent_stripe(slide, palette=palette, sw=sw)
    h.title_block(slide, title, palette=palette, fonts=fonts,
                  type_scale=type_scale, sw=sw, sh=sh)
    h.deck_chrome(slide, palette=palette, fonts=fonts,
                  type_scale=type_scale, sw=sw, sh=sh,
                  eyebrow='HOW · 추진 방법',
                  footer='기러기류 마커 발굴 · ㈜디보')
    # Both page_number AND total auto-fill when omitted: page_number from
    # this slide's slide_number, total from the deck's slide count. So
    # inserting a slide (add_slide shifts the rest automatically) never
    # needs a rewrite of every slide's literal "x / N". Pass page_number=N / total=N to
    # override, or =None to hide either. (DON'T hardcode total=13.)
    p.flow_pipeline(slide, items=[...],
                    palette=palette, fonts=fonts,
                    type_scale=type_scale, sw=sw, sh=sh)
  """,
)
# render_mode auto-inferred to "code" — no commitment made at outline time.
```

`add_slide` itself stays simple:

```
mcp__scivo__add_slide(
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

### 5a. `code` slides — author the slide in python-pptx

A slide with `render_mode="code"` carries a python-pptx snippet that the
exporter runs. **Before the first snippet, read `references/code-slides.md`**:
every callable (`h.*` helpers, `p.*` patterns) with its signature, the names
bound when the snippet runs, the grid, and the palette keys. Do not write a
helper call from memory — the catalog is the list of what exists, and a call
that is not in it raises at export.

## Bespoke is the default

Most content slides are composed, not picked from a pattern.
`references/bespoke.md` has the trigger table (which signals in a slide brief
mean bespoke), the chrome rules — `h.deck_chrome` is part of every content
slide, and there is a list of what NOT to add to it — and the density
references. Read it before designing the first content slide.

## Pattern shortcuts — narrow use only

A `p.*` pattern covers one of a few fixed structures and nothing else: there
is NO pattern for argument, evidence or comparison content.
`references/patterns.md` has the two kinds of pattern and how to choose, the
worked examples (a bespoke composition, a card grid, bullets beside a figure),
the image-placeholder workflow for a `code` slide, and the overlap and
alignment rules — stacked text, timelines, filled rectangles. Read it when a
slide might be a pattern, when a `code` slide needs an image, or when text
collides.

### 5c. Compositional effects — why arrangement matters

`references/composition.md`: centred against left-aligned titles, what goes
left and what goes right, full-bleed against a caption strip, grid against
row, whitespace, and the four-colour / four-size discipline. Read it when a
slide is arranged and still does not work.

### 5b. Hybrid slides — bullets + figure, or several images (regions)

`references/regions.md`: a title with bullets and one figure, several images
on one slide, and images the USER uploaded from the dashboard.

**A user-uploaded slide image is on the slide — not in `list_materials`, not
in `list_assets`.** It is a region with `image_source == "upload"`; find it
with `list_slides(slug, deck_id, fields=["regions"])`, read its `note` (the
user's hint about what it is and where it goes), and place it. Never tell the
user an uploaded slide image is inaccessible.

### 5d–5e. What good looks like, and the AI-slide look

`references/look.md`: the reference corpus of rendered exemplars (and how to
look at one before authoring), the tells of a generated deck, a palette
library, and sizing ratios for projection distance. Read it before the first
content slide and again at the critique pass (§9).

### 6. Renumber once at the end

After adding all slides:

```
mcp__scivo__renumber_deck(slug, deck_id)
```

Packs `slide_number`s tightly starting at 1, even if you added them
out of order.

### 7. Mark drafted

```
mcp__scivo__update_deck(slug, deck_id, status="drafted")
```

Status flow: `draft` (initial) → `drafted` (slides + notes + prompts
done, ready for rendering) → `rendered` (Phase 3, slide PNGs + PPTX
exist).

### 8. Tell the user

Summary: "Deck `{deck_id}` drafted with N slides at status='drafted'.
Next: the critique pass, then render and export."

### 9. Critique pass — vision review (todo 004 §A)

Run `/visual-review`: the whole set first, then the frame, fix, re-render,
and **stop when a full pass finds nothing** — not after three rounds. What
follows is only what is specific to a deck.

**The whole deck before any single slide.** `preview_deck_sheet(slug,
deck_id)` tiles every slide into one PNG — Read it first. It is the only view
that shows the faults a slide cannot have on its own: one accent used on
every slide so it marks nothing, chrome that fades out after slide 8, two
slides drawing the same thing differently, a density cliff in the back half.
It renders nothing itself, so a tile captioned STALE (and `current: false`)
means refresh that slide with `preview_slide` before scoring anything.

**Then the automatic FAILs.** `preview_slide` and `export_deck_to_pptx` both
return `overlap_warnings`, `bounds_warnings`, `font_warnings`,
`placeholder_warnings` and `layout_warnings`. A slide in any of them fails
regardless of how it scores — text on text, text off the canvas, a
substituted font, "TODO" in front of the audience, an unreadable thumbnail.
Re-render until they are empty. **The fix recipe for each, and the scoring
rubric (visual integrity, density ≥ 25 shapes on a content slide, chrome,
hierarchy, whitespace, alignment, type, colour, storytelling), are in
`references/critique.md`** — open it when a warning fires, or when you are
about to score the deck.

Read every PNG with the `Read` tool; you are multimodal and the render is the
only evidence that counts. For each category under 4, write one specific
complaint plus its fix, then `update_slide(slug, deck_id, slide_id,
code=<rewritten snippet>)`.

**No PNGs?** `pdf_skipped` / `slide_pngs_skipped` means this machine lacks
LibreOffice or PyMuPDF; the result names the missing piece and its install
command. Tell the user, and do not report the deck as looked at — the warning
lists are not a substitute for having seen it.

## Acceptance test

`/paper-deck <slug> "lab seminar" 20` should produce:
- One deck doc with concept + theme + audience + duration_min
- Slides whose roles follow from THIS paper's story — there is no
  standard sequence (§4) — in a number the duration supports and with no
  more result slides than the paper has figures to show
- One content slide shown to the user and answered before the others were
  authored (§4.9), or the summary saying why that was skipped
- Every slide has `notes` non-empty
- Every slide's `prompt` starts with the unity header placeholders
- `status == "drafted"` on the deck

## Common follow-ups

- "Change the theme to data-botanical" → `update_deck(theme=...,
  concept=...)`. Slides don't need to change — their prompts use
  placeholders that re-materialize against the new theme.
- "Cut to 10 minutes" → drop discussion + outline; verify with the
  user before deleting any slide that has good `notes`.
- "Reorder so methods come after background" → `reorder_deck(slug,
  deck_id, order=[…ids…])` with the slide ids in the target order.

## Rendering + export

`references/render-export.md`: what each render mode produces, what lands in
`skipped[]` and why, previewing, and exporting to PPTX (with its PDF). The
hard rules above say WHEN — preview while editing, export once at the end —
and that file says how.

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

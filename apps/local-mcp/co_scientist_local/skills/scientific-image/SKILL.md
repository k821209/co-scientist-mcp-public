---
name: scientific-image
description: Generate a publication-quality scientific diagram or schematic (pathway, network, workflow, comparison, architecture, heatmap, tree) via the MCP's image generator and register it as a figure on a paper. Use when the user says "draw the pathway," "make a schematic," "generate a figure showing X," "diagram the workflow," "show me a model of …".
---

# /scientific-image

**Triggers:** "draw a pathway diagram of …", "schematic of …", "show
the model architecture," "make a figure of the workflow," "diagram
the relationship between …".

## What it does

A staged pipeline around `mcp__scivo__generate_image`:

1. **Classify** the diagram type (pathway / network / workflow /
   comparison / architecture / heatmap / tree / freeform schematic).
2. **Blueprint** the entities, relationships, and spatial layout
   BEFORE generating — pinning structure prevents the LLM-painter
   from inventing relationships that don't exist.
3. **Generate** with a structured prompt that bakes in the blueprint.
4. **Critique** the result against style rules and re-prompt until a
   full pass finds nothing (`/visual-review`).
5. **Register** as a figure on the paper (or save as asset for
   exploratory shots).

`generate_image` is a paid-plan tool: on a free plan it refuses, and there
is no fallback inside this MCP. Check `get_plan()` before promising a
figure; `project_guide(topic="image-generation")` says what a free-plan user
does instead.

## Hard rules

- **NEVER skip the blueprint step**, even for simple diagrams. The
  blueprint is your source of truth — the painter LLM lies; the
  blueprint doesn't.
- **NEVER chain >3 edits**. After three iterations on the same image
  the text fidelity degrades visibly. Start fresh with a tightened
  prompt instead.
- **NEVER inline-render data values** (numbers, p-values, gene names)
  if the audience needs precision — the painter mis-spells. Use
  numbered labels in the figure and a real key in the caption.
- **ALWAYS register through `add_figure` if it's going in the
  manuscript**. Otherwise it sits as an asset (use `figure_number`
  unset; the tool stores it under `papers/{slug}/assets/`).

## Code-based figures (matplotlib / graphviz): spec + lint BEFORE render

When you draw a schematic in **code** (hand-placed boxes/arrows) instead of via
the painter, do NOT loop by rendering the PNG and eyeballing it — that misses
overlaps, off-canvas elements, and arrows crossing unrelated boxes. Instead:

1. **Represent the layout as a spec** of nodes and edges on a canvas, each box
   with its `label` and `font_size` — `lint_figure_layout`'s description has
   the schema, what it checks and what it returns.
2. **Lint before rendering, and iterate on the spec until `ok`, THEN render.**
   Pass the figure size so label overflow is measured. Fix a flagged label by
   shrinking the font, enlarging the box, or setting `wrap=True`; confirm a
   borderline hit with matplotlib's real extent
   (`t.get_window_extent(fig.canvas.get_renderer())`) at render.

This turns the unreliable render-and-eyeball loop into a deterministic one.

## References (load these — don't reinvent)

This skill ships with reusable scaffolds. **Read the ones that match
your task before writing prompts** — the painter LLM produces much
sharper diagrams when fed exact hex codes, shape conventions, and
arrow rules from these guides than when given freeform descriptions.

```
references/
  index.md                       # type ↔ keyword map (auto-detect)
  styles/
    pathway_diagram.md           # metabolic / signaling / biosynthesis
    network_diagram.md           # PPI / GRN / co-expression
    workflow_pipeline.md         # protocols / bioinfo pipelines
    comparison_chart.md          # bar charts / treatment vs control
    architecture_diagram.md      # system / platform / software stack
    heatmap_matrix.md            # heatmaps / correlation matrices
    phylogenetic_tree.md         # cladograms / dendrograms
templates/
  color_palettes.md              # 6 palettes, exact hex codes
  style_guidelines.md            # typography, shapes, arrows, layout
  critique_checklist.md          # 6-category weighted rubric
```

Each `styles/*.md` file contains: characteristics, layout patterns
(ASCII), element conventions table, arrow conventions table, prompt
keywords, and a ready-to-adapt example prompt fragment. Copy hex codes
and shape rules verbatim into your generation prompt — never describe
colors by name alone.

## Flow

### 1. Classify diagram type

**Read `references/index.md`** — it has the canonical keyword map and
auto-detection rules. Pick the type with the most keyword matches; if
the content spans two types, treat the dominant one as primary and
note the secondary.

Quick keyword sniff (full rules in `index.md`):

| Type           | Keywords / cue                                       |
| -------------- | ---------------------------------------------------- |
| `pathway`      | "pathway," "signaling," gene/metabolite cascade      |
| `network`      | "interaction," "graph," "PPI"                        |
| `workflow`     | "pipeline," "flowchart," "steps," "method overview"  |
| `comparison`   | "vs," "before/after," "wild-type vs mutant"          |
| `architecture` | "model," "system," "block diagram"                   |
| `heatmap`      | conceptual matrix only; for REAL data → `/analysis-run` |
| `tree`         | "phylogeny," "lineage," "hierarchy"                  |

If the user wants real data plots (heatmap of actual expression
values, scatter, statistical bar) — defer to `/analysis-run` with
matplotlib/seaborn. This skill is for SCHEMATICS and conceptual
figures only.

### 2. Blueprint

**Before drafting the blueprint, read three files:**

1. `references/styles/{type}.md` for the classified type — gives you
   layout patterns, the element/arrow conventions tables, and a
   reference prompt fragment to anchor against.
2. `templates/color_palettes.md` — pick the palette that matches the
   type (the per-type recommendation is in the "Palette Selection
   Guide" table). Note the exact hex codes you will use.
3. `templates/style_guidelines.md` — Typography table, node/shape
   conventions, arrow rules, layout spacing. This is the cross-type
   baseline.

Now spell out the blueprint, citing the conventions you just loaded:

```
Title: <figure title>
Type: pathway
Aspect: 16:9
Background: clean white, scientific journal style

Entities (each gets a label, a position, a glyph):
  A. EGF (ligand, top-left, blue receptor-shaped)
  B. EGFR (membrane receptor, top-center, blue)
  C. RAS (small GTPase, mid-center, green diamond)
  D. ERK (kinase, mid-right, orange rounded rect)
  E. Nucleus (bottom-right, gray ellipse)

Relationships (each gets an arrow style):
  A → B: binding (solid black, T-shape)
  B → C: activation (solid black, →)
  C → D: phosphorylation, multi-step (dashed black, → with "P")
  D → E: translocation (curved arrow into nucleus)

Spatial:
  - Membrane runs horizontally across the top third
  - Cytoplasm fills middle
  - Nucleus is bottom-right with thick boundary
  - Labels outside elements, not inside, to keep text crisp
```

Show this to the user, ask for confirmations / tweaks. THEN generate.

### 3. Build the prompt + generate

Follow the **7-layer prompt template** in
`templates/style_guidelines.md` ("Prompt Construction Template"
section) — STYLE → LAYOUT → ENTITIES → RELATIONSHIPS → GROUPS →
LABELS → NEGATIVE. The example prompt fragment at the bottom of the
matching `references/styles/{type}.md` is a good starting point;
substitute in your blueprint's entities and adapt the layout
direction.

Rules for the prompt:
- Always use exact hex codes (`#0066CC`), never color names ("blue").
- Always include the NEGATIVE layer: "No 3D effects, no drop shadows,
  no gradients, no decorative elements, no photo-realistic textures".
- Specify the canvas: "Scientific journal figure, flat design, clean
  white background, sans-serif".

From the blueprint, write a single prompt for the painter:

```
"A clean schematic pathway diagram, scientific journal style, white
background. Show EGF (blue ligand glyph, top-left) binding to EGFR
(blue receptor crossing a horizontal membrane line). EGFR activates
RAS (green diamond, mid-center) which activates ERK (orange rounded
rectangle, mid-right). ERK phosphorylates and translocates into the
nucleus (gray ellipse, bottom-right). Solid black arrows for direct
activation, dashed arrow with 'P' label for phosphorylation. Labels
outside each element. 16:9 aspect, minimal color palette."
```

Then:

```
result = mcp__scivo__generate_image(
  prompt=<full prompt>,
  slug=slug,                            # keyword: `prompt` is the first parameter
  figure_number=<N>,                    # if registering immediately
  asset_filename=<name.png>,            # if exploring (no fig number)
  aspect_ratio="16:9",
  caption="<draft caption matching blueprint>",
)
```

### 4. Critique + iterate

Run the loop in `/visual-review` — look, write the complaint AND the fix,
re-render, look again. **Stop when a full pass finds nothing**, not after a
set number of rounds: a count stops on tiredness, and the painter's
leftovers are exactly what a tired pass waves through.

Score the output against `templates/critique_checklist.md`. Its six weighted
categories cover the failure modes the painter LLM introduces — arrows and
colour carry the most weight because they are the ones that make the figure
say something false.

Quick sniff (the checklist has the full check items):
- All entities present? Spelled correctly?
- Relationships go the right direction? Inhibition uses flat-bar, not triangle?
- Spatial layout matches blueprint? No crowded-vs-empty halves?
- Labels outside, not inside? Adequate contrast?
- White background, no shadows, no gradients?

**PASS**: overall weighted >= 3.5 AND no category < 2.5. Otherwise
write targeted edit instructions (max 5, prioritized by weight — fix
Arrow and Color issues first) using the edit-instruction format in
the checklist, and re-prompt.

**When a pass keeps finding the same fault, the generator is wrong, not the
image.** After about three re-prompts on one defect, change tactic: simplify
the blueprint (fewer entities) and start fresh. Chained edits degrade text
fidelity, so a fourth edit on the same image is worse than a first edit on a
simpler one — this is a tactic change, not a budget running out.

### 5. Save the final version

If exploring with `asset_filename`: the user can promote one to a
figure later via `add_figure(local_path=...)`.

If `figure_number` was set: the figure doc + storage blob are
already in place. Update the caption with the polished version:

```
mcp__scivo__update_figure(
  slug, figure_number,
  caption="<polished caption>",
  legend="<full legend for the manuscript>"
)
```

The dashboard's Paper page shows it under Figures with a
download/preview button.

## Aspect ratios + sizes

Defaults that work:
- `1:1` for single-cell schematics, isolated components
- `16:9` for multi-stage pathways, workflows, comparisons (most common)
- `3:2` (landscape) for tree / hierarchy figures; `2:3` for a tall one

Only the ratios `generate_image` lists are accepted — `4:3` is not one of
them — and the output is one of the model's native sizes whatever is asked.

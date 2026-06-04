---
name: supplementary-material
description: Identify and register supplementary figures, tables, and text for a paper. Use when the user says "add supplementary," "make this an SFigure," "move X to supplement," "extended data," "supporting information."
---

# /supplementary-material

**Triggers:** "make a supplementary figure," "move the QC plots to
supplement," "extended data table," "supporting information," "SFig 3."

## Numbering convention

Supplementary content reuses the SAME figures / tables collections with
a **+100 offset**:

- SFigure 1 → `figure_number = 101`
- SFigure 2 → `figure_number = 102`
- STable 1  → `table_number = 101`

`list_figures(slug, supplementary=True)` and
`list_tables(slug, supplementary=True)` filter to the ≥101 range.
The dashboard renders them under separate "Supplementary Figures /
Tables" headings.

## Flow

### 1. Audit existing state

```
main_figs = mcp__co_scientist__list_figures(slug)
supp_figs = mcp__co_scientist__list_figures(slug, supplementary=True)
main_tbls = mcp__co_scientist__list_tables(slug)
supp_tbls = mcp__co_scientist__list_tables(slug, supplementary=True)
paper = mcp__co_scientist__get_paper_state(slug)
```

### 2. Identify supplementary candidates

Good candidates to move OUT of the main text into supplement:
- Extended / full-resolution versions of main figures
- QC plots (read-depth, mapping rate, PCA of batch effects)
- Full datasets where the main text shows a top-N subset
- Detailed protocols, parameter tables, derivations
- Negative / control results that support but don't carry the story

Surface the candidates and let the user confirm which to promote.

### 3. Register supplementary figures / tables

```
mcp__co_scientist__add_figure(
  slug,
  figure_number=101,           # first SFigure
  title="Extended QC metrics",
  caption="<draft caption>",
  legend="<full legend>",
  local_path="<path to PNG>",
)
mcp__co_scientist__add_table(
  slug,
  table_number=101,            # first STable
  title="Full parameter set",
  content="<markdown table>",
  caption="<caption>",
)
```

Pick the next free number: max existing supplementary number + 1,
starting at 101.

### 4. Supplementary text sections

For supplementary METHODS / NOTES that are prose (not a figure or
table), add them as regular sections with a `supplementary_` key
prefix, or append to a dedicated section the user designates:

```
mcp__co_scientist__update_section(
  slug, key="supplementary_methods",
  body="<supplementary text>",
  status="draft",
)
```

(If the canonical section set doesn't have a supplementary section,
discuss with the user where it should live — most journals want
supplementary text as a separate document, which `/paper-export`
handles via the supplementary figures/tables already.)

### 5. Cross-reference from the main text

Wherever the main text should point to a supplement, insert an inline
marker so the export pipeline picks it up:

- `{fig:101}` → renders as "Supplementary Figure 1"
- `{tab:101}` → renders as "Supplementary Table 1"

Edit the relevant section body via `update_section` to add the
reference at the right spot.

### 6. Verify export-readiness

```
prep = mcp__co_scientist__prepare_export(slug)
```

`prepare_export` already bundles `supplementary_figures` and
`supplementary_tables` (the ≥101 range). Check `prep["warnings"]` for
placeholders. Don't auto-run `/paper-export` — wait for the user to
ask.

## Rules

- **No placeholders.** Every supplementary item is a real figure /
  table / section doc — not a `TODO` comment in the manuscript.
- **+100 offset, always.** A supplementary figure is never
  `figure_number < 101`.
- **Don't auto-export.** Registering supplementary content and
  exporting are separate steps.

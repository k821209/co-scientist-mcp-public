---
name: promote-result
description: Map an analysis group's output files (PNG/CSV) onto manuscript figures and tables. Use when the user says "make figure 2 from that analysis," "promote the results," "turn the analysis output into a figure," "register the table from the CSV."
---

# /promote-result

**Triggers:** "promote the DE analysis results," "figure 3 from the
pangenome run," "register that CSV as a table," "map analysis outputs
to panels."

## What it does

Takes the output files an `/analysis-run` produced (sitting in
`analysis/<group>/out/`) and registers the user-chosen subset as
manuscript figures / tables via MCP tools — with proper Storage upload
and path normalization the dashboard expects.

Two modes:
- **Map** (default) — show the user which output maps to which figure
  panel / table slot, draft short captions, but DON'T create the final
  figure yet. Lets the user adjust the mapping.
- **Promote** — create the actual figures/tables from a confirmed map.

## Flow

### 1. Resolve the analysis group

```
analyses = mcp__co_scientist__list_analyses(slug)
runs = mcp__co_scientist__list_analysis_runs(slug, analysis=<group>)
```

If the user didn't name a group, list them and ask.

### 2. List the candidate outputs

Walk `analysis/<group>/out/` on disk. Show the user each PNG / PDF /
CSV / TSV with size + a one-line guess at what it is.

### 3. Map mode — propose, don't write

For each output the user wants in the paper, propose:

```
analysis/de-genes/out/volcano.png   → Figure 2, panel A
                                       "Volcano plot of differential
                                        expression"
analysis/de-genes/out/top50.csv     → Table 1
                                       "Top 50 differentially expressed
                                        genes"
```

Multi-panel figures: register each output as a PANEL —
`add_figure_panel(slug, figure_number, local_path=…)` per image, then
`compose_figure_panels(slug, figure_number)`. Do NOT montage them by hand: a
hand-built composite bypasses the `panels` array, so the dashboard cannot
re-letter or replace one panel, and `panels_updated_at` never says the
composite is stale.

### 4. Promote mode — write to the DB

For figures:

```
mcp__co_scientist__add_figure(
  slug,
  figure_number=N,            # ≥101 for supplementary
  title="<concise title>",
  caption="<draft 1-sentence caption>",
  legend="<FULL legend — written now, during promotion>",
  local_path="analysis/<group>/out/<file-or-composed-panel>.png",
  source_analysis="<group>",
  source_runs=["<run_key of each arm shown>"],
  varies="<the one param the panels differ in>",
)
```

For tables — convert CSV/TSV to a markdown table:

```
mcp__co_scientist__add_table(
  slug,
  table_number=N,
  title="<title>",
  content="<markdown table converted from the CSV>",
  caption="<caption — what the table shows: columns, units, n>",
  source_analysis="<group>",
  source_runs=["<run_key behind each row>"],
  varies="<the one param the rows differ in>",
)
# Tables have `caption` only; `legend` is a figure field and add_table
# rejects it.
```

Then, for any table or figure that COMPARES arms:

```
mcp__co_scientist__compare_run_params(slug, table_number=N)
```

Read `report` before the caption is final. Every key that differs across
the rows' runs and is not in `varies` is listed; decide for each whether it
is design (say so in the caption) or a confound (the row is not comparable
— do not promote it). A row whose run has no `params` shows as uncomparable;
back-fill with `update_analysis_run` first. `source_analysis` is not optional
for a numeric table: `check_requirements` fails one without it, and a table
nobody computed says `source_analysis="manual"`.

### 5. Link the analysis to its outputs

```
mcp__co_scientist__update_analysis(
  slug, name=<group>,
  description="<what was done> → produced Figure N, Table M",
)
```

## Critical rules

- **NEVER copy files into a `figures/` directory manually** or write
  figure docs by hand. `add_figure(local_path=…)` handles the Storage
  upload + path normalization the dashboard depends on.
- **Full legends are written during PROMOTE, not MAP.** Map mode only
  drafts short captions.
- **Don't promote every output.** Only the user-picked subset. The
  rest stay in `analysis/<group>/out/` as the audit trail.
- **300+ DPI** for any PNG that becomes a figure.

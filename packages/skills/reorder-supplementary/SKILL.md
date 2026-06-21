---
name: reorder-supplementary
description: Renumber/reorder supplementary figures or tables (SFig/STable). Use when the user says "make SFig 3 come first," "swap STable 1 and 2," "reorder the supplementary figures," or a reviewer asks to reorder supporting items.
---

# /reorder-supplementary [slug]

Supplementary items are keyed by number (SFig 1 = `figure_number` 101, …), and
a figure's image blob path embeds that number — so reordering means renumbering
the docs and moving the blobs. `mcp__co_scientist__reorder_supplementary` does
that server-side (no image re-upload) and rewrites deterministic body refs.

## Flow

1. List the current items: `list_figures(slug, supplementary=True)` (or
   `list_tables(slug, supplementary=True)`). Show the user the current order
   with their numbers (≥101) and titles.
2. Confirm the desired order with the user, as a sequence of the CURRENT
   numbers. E.g. to put SFig 3 first: current `[101, 102, 103]` → desired
   `order=[103, 101, 102]`.
3. Apply: `reorder_supplementary(slug, kind="figure"|"table", order=[…])`.
   The items are reassigned to 101, 102, … in that order; figure blobs are
   copied to their new paths; `{fig:N}`/`{tab:N}` tokens and `![](figure:N)`
   embeds in the manuscript are auto-rewritten.
4. **Fix prose references.** The result's `prose_mentions` lists freeform
   mentions the tool did NOT rewrite (e.g. "Supplementary Figure 2",
   "Fig. S2") with a `suggest` like `S2 → S3`. These aren't auto-edited because
   prose phrasing/spacing varies. Open the named sections, update each mention
   to its new index using `update_section`, and re-read to confirm. Do this
   carefully — the index shift can collide (S1→S2, S2→S1), so map every mention
   from its ORIGINAL number, not sequentially.
5. Report the final order and how many refs you updated.

## Notes

- `order` must be a permutation of the current supplementary numbers of that
  kind; a partial or unknown list is rejected.
- Main (non-supplementary) figures/tables are out of scope here — this tool
  only touches the ≥101 range.
- An identity reorder is a no-op (nothing is written).

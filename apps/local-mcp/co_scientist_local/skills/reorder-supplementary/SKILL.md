---
name: reorder-supplementary
description: Renumber/reorder supplementary figures or tables (SFig/STable). Use when the user says "make SFig 3 come first," "swap STable 1 and 2," "reorder the supplementary figures," or a reviewer asks to reorder supporting items.
---

# /reorder-supplementary [slug]

Supplementary items are keyed by number (SFig 1 = `figure_number` 101, …), and
a figure's image blob path embeds that number — so reordering means renumbering
the docs and moving the blobs. `mcp__scivo__reorder_supplementary` does
that server-side (no image re-upload) and rewrites deterministic body refs.

## Flow

1. List the current items: `list_figures(slug, supplementary=True)` (or
   `list_tables(slug, supplementary=True)`). Show the user the current order
   with their numbers (≥101) and titles.
2. Confirm the desired order with the user, as a sequence of the CURRENT
   numbers. E.g. to put SFig 3 first: current `[101, 102, 103]` → desired
   `order=[103, 101, 102]`.
3. Apply: `reorder_supplementary(slug, kind="figure"|"table", order=[…])` —
   its description says what it rewrites and what it returns.
4. **Fix prose references.** Each entry in `prose_mentions` carries a
   `suggest` like `S2 → S3`. Open the named sections, update each mention
   to its new index using `update_section`, and re-read to confirm. Do this
   carefully — the index shift can collide (S1→S2, S2→S1), so map every mention
   from its ORIGINAL number, not sequentially.
5. Report the final order and how many refs you updated.

## Notes

- `order` must be a permutation of the current supplementary numbers of that
  kind; a partial or unknown list is rejected.
- An identity reorder is a no-op (nothing is written).

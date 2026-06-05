---
name: paper-review
description: Act as a virtual expert reviewer on a paper. Surfaces methodological, statistical, and domain issues, then writes EACH finding to the database as a Firestore review row (source='ai') so the dashboard and the user can see them inline. Use when the user says "review my paper," "give me reviewer comments," "find weaknesses," "critique the methods/results."
---

# /paper-review

**Triggers:** "review my paper," "critique X," "play reviewer 2,"
"check the stats," "what would a reviewer find wrong," "AI review,"
"get me reviewer feedback."

## Non-negotiable rules (do NOT violate)

1. **Every finding becomes a database row**, written via
   `mcp__co_scientist__add_review(...)` with `source="ai"`. No
   markdown-only output. The dashboard's Comments card lists these
   alongside user comments; the bidirectional `/paper-revision` loop
   reads them from there.
2. **Anchor each finding to the smallest passage that triggers it**.
   Use the same `anchor_text` field that user selection comments use —
   the exact quoted phrase from the manuscript. This lets the
   dashboard render an inline yellow highlight on the problem text and
   lets the next round of `/paper-revision` jump straight to it.
3. **Verify after writing**. Call
   `mcp__co_scientist__list_reviews(slug, source="ai", status="open")`
   at the end; assert total ≥ number of findings you intended to write.
   If short, retry the missing ones.
4. **Don't duplicate**. Before writing, call
   `list_reviews(slug, source="ai")` to see what already exists. Skip
   findings that overlap heavily with an open AI review.

## Three modes

### A. Full review (default)

Three virtual reviewers, run in sequence. Each writes its own findings:

1. **Methods Reviewer** — experimental design, sample size, controls,
   reproducibility, statistical method choice. Flag: missing
   replicates, biased sampling, missing controls, inappropriate
   parametric/non-parametric calls.
2. **Statistics Reviewer** — calculations, claims that don't follow
   from the data, p-value misuse, multiple-testing, effect-size
   omissions. Cross-check numbers between abstract / results / tables.
3. **Domain Reviewer** — field context, prior art, terminology,
   missing key citations. Use `mcp__co_scientist__search_works` to
   spot-check that referenced prior work exists and is correctly
   characterized.

Plus a consistency pass:
- Every `{table:N}` resolves to an actual table (`list_tables(slug)`).
- Every `{fig:N}` resolves to an actual figure (`list_figures(slug)`).
- Numbers in abstract == numbers in results section for the same
  claim.
- Captions describe what tables/figures actually contain.

### B. Specialist addendum

User says: "give me a statistician's take" or "review from a TE biology
perspective." Run ONE virtual reviewer with that focus, skipping
findings already covered by existing AI reviews.

### C. Custom opinion

User pastes a critique they want formatted. Convert it into one or
more structured review docs — break compound critiques into separate
rows ("the methodology is weak AND the writing is unclear" → two
reviews).

## Flow (full mode)

### 1. Load context

```
paper = mcp__co_scientist__get_paper_state(slug)
existing = mcp__co_scientist__list_reviews(slug, source="ai")
figures = mcp__co_scientist__list_figures(slug)
tables = mcp__co_scientist__list_tables(slug)
refs = mcp__co_scientist__list_references(slug)
```

Read the assembled manuscript text from `paper.manuscript`.

### 2. Run each reviewer in sequence

For each persona, produce findings as a list of:

```python
{
  "section": "methods" | "results" | "intro" | ...,
  "severity": "major" | "minor" | "suggestion",
  "anchor_text": "<exact verbatim phrase from the manuscript>",
  "comment": "<the reviewer's critique, in 1-3 sentences>",
}
```

The `anchor_text` MUST be a substring that appears in the manuscript
body — copy/paste from `paper.manuscript` or from a section's body
returned by `get_section`. Don't paraphrase.

### 3. Persist each finding

```
mcp__co_scientist__add_review(
  slug,
  comment="...",
  source="ai",
  reviewer_name="Methods Reviewer" | "Statistics Reviewer" | "Domain Reviewer",
  section="...",
  severity="major" | "minor" | "suggestion",
  anchor_text="...",
  manuscript_ref=f"section:{section}",
)
```

Even if 30 findings, write 30 separate rows — the dashboard's UI is
built around per-passage anchoring.

### 4. Consistency pass

For each `{table:N}` in the manuscript:
- If `N` not in `tables`, write a "major" finding anchored to that
  citation: "Table N referenced but not present in the paper."

Same for `{fig:N}`.

For numerical claims in the abstract, scan the results section for
the same number. If not found, write a "major" finding anchored to
the abstract claim: "Abstract states X but results section doesn't
support this number."

### 5. Verify

```
final = mcp__co_scientist__list_reviews(slug, source="ai", status="open")
assert len(final) >= <expected>
```

Print: "Wrote N findings (X major, Y minor, Z suggestions)."

### 6. Tell the user

Summary: "Three reviewer personas produced N findings. View them on
the dashboard's Paper page — each one is a yellow highlight on the
problem passage. Or run `/paper-revision` to walk through them one by
one."

## Anti-patterns

- **Markdown-only output** ("here's a review for you ↓ ... ↓") — that
  doesn't land in Firestore, the dashboard won't see it, and the
  bidirectional loop dies. Always `add_review`.
- **One row containing 20 issues** — break them up. Each row gets its
  own highlight, severity, and resolution state.
- **Vague anchors** like a whole paragraph — pick the smallest phrase
  that triggers the critique. If the user/agent fixes it, the
  highlight goes with the change naturally.
- **Inventing citations in the critique** — if the reviewer mentions
  prior work, verify via `search_works` first; otherwise say "the
  authors may want to consider work on X" instead of citing a paper
  that doesn't exist.

## Severity guidance

- `major` — manuscript can't be accepted as-is. Wrong stats, missing
  control, unsupported claim, missing data.
- `minor` — accept-after-revision. Writing clarity, missing detail,
  small inconsistency.
- `suggestion` — editorial taste; optional improvement.

## After /paper-review, before re-submission

Have the agent or user run `/paper-revision` — it iterates the open
reviews, addresses each, and marks them resolved with a response
field. The dashboard's Comments card shows the resolution history.

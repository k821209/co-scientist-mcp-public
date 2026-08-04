---
name: response-letter
description: Turn a journal's reviewer comments into a point-by-point response letter. Use when the user got a decision letter (major/minor revision), pastes reviewer comments, or says "write the response to reviewers / rebuttal letter / response letter."
---

# /response-letter [slug]

Build a point-by-point response letter from the journal's **real** reviewer
comments — never from internal `/paper-review` (`source='ai'`) self-review,
which is pre-submission and has no place in a response letter.

Real reviewer points live as reviews with `source='reviewer'`, carrying
`reviewer_name` ("Reviewer 1") and a `round`. The author triages each
(accept → revise the manuscript; reject → write a rebuttal) using the normal
decision/`response` flow, and this skill compiles the letter from them.

## Step 0 — make sure the reviewer comments are registered

Check first: `mcp__co_scientist__list_reviews(slug, source='reviewer')`.

If there are none (or the user is pasting a fresh decision letter), **import**:
1. Ask the user to paste the decision letter (or read the file they point to).
2. Split it into individual points, grouped by reviewer. Keep each reviewer's
   numbering. One `add_review` per point:
   `add_review(slug, comment="<the reviewer's point, verbatim or lightly
   cleaned>", source="reviewer", reviewer_name="Reviewer 1", round=<N>,
   severity="major"|"minor"|"suggestion", section=<key if obvious>,
   anchor_text=<a quoted phrase from the manuscript the point targets, if any>)`.
3. Confirm the count back to the user ("Registered 3 points from Reviewer 1,
   2 from Reviewer 2 — round 1").

Do NOT invent points the letter didn't contain, and don't merge distinct
points — one row each, so each gets its own response.

## Step 1 — make sure every point is addressed

Run `mcp__co_scientist__review_triage_summary(slug)`. Every reviewer point
must be either:
- **accepted** → the manuscript was revised; its `response` says *how* (and
  where: section / lines). Resolve it (`status='resolved'`).
- **rejected** → its `response` carries a polite rebuttal (why not adopted;
  cite where the manuscript already covers it).

If `rejected_without_rationale > 0` or any accepted point is unresolved, do
that pass first — run `/paper-revision` (it walks accepted edits and rejected
rebuttals). A point with no `response` becomes a `⚠ rebuttal missing`
placeholder in the letter, so don't leave gaps silently.

## Step 2 — compile the letter

Read the addressed reviewer comments
(`list_paper_comments(slug, source='reviewer', status=None)`), group by
`round` then `reviewer_name`, and produce markdown:

```
# Response to Reviewers — <paper title>
We thank the reviewers for their careful reading. Our point-by-point
responses follow; reviewer comments are in italics and manuscript changes
are quoted.

## Reviewer 1
**1.** *<reviewer point>*
> <response>: how we revised (Section X, lines …) — or, if rejected, a
> courteous rebuttal explaining why, citing where the manuscript addresses it.
```

Rules:
- One entry per reviewer point, in the reviewer's original order.
- **Accepted** → describe the change and cite the location; quote the new text
  when short.
- **Rejected** → "We have chosen not to adopt this suggestion because …",
  citing Section/lines that already address it.
- **Missing `response`** → emit `> ⚠ rebuttal missing — add a response for
  review <id>` so it can't be overlooked. Tell the user which ones.
- Keep the author's voice professional and concise; do not overclaim changes
  that weren't made.

## Write for a reader who wasn't in the session

A reviewer has read the manuscript once and shares NONE of your working memory,
and is deciding whether to believe a new analysis they haven't seen. You have
perfect recall of it, which makes context-dropping invisible from the inside —
and asking yourself to be concise makes it worse, because the clauses carrying
reader context are the ones that look redundant to you. **When concision and
reader-context conflict, keep the context.** Dropped context also degrades into
error: "genomic inflation falls from λ = 7.03 to 1.23" with no arm named implied
a diagnostic that does not exist for the other method.

**First-use audit before you deliver.** For every technical term, symbol,
threshold and named cross-reference, grep its FIRST occurrence and confirm it
carries (a) what it means, (b) the scale/baseline that makes the value
interpretable, (c) whose it is when several are in play — "Reviewer 1's Major 3",
not "Major 3"; λ attributed to the arm it exists for.

- **A number without a scale is not information**: "0.904, on a 0–1 scale where
  1 means the same partition"; "28.7% against a chromosome-matched null of
  21.5% ± 2.8%". Give the causal step: "a permutation test cannot return a
  p-value below one over the number of arrangements it can draw, so the floor
  was 8.3e-4 — three orders of magnitude above the 8.9e-7 needed".
- **When compressing, cut claims, not context.** Safe: a sentence the manuscript
  already carries in full. Unsafe: the clause saying why a number matters.

## Step 3 — deliver

Show the draft. Offer to save it — either as a new section
(`add_section(slug, key='response_letter', title='Response to Reviewers',
body=…)`) so it exports with the paper, or as a standalone file the user can
attach to the resubmission. Default to showing it inline and asking which.

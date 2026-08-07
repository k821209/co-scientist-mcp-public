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

## Writing the letter: three rules from repeated corrections

**A declined request needs its REASON, in the same breath.** A bare
"MDSearch was not benchmarked." headlines what we did not do; deleting it hides
non-compliance and re-creates the very `frame_error` the frame check catches. The
resolution is neither — it is the reason:

> "We benchmarked the LD-based haplotyping route **because it is the direct
> alternative to what vcf2hash does**: it produces gene-level haplotypes from the
> same input. MDSearch and PLINK LD pruning select markers rather than build
> haplotypes, so we cite them in the Discussion as complementary tools instead of
> running a head-to-head experiment against either."

Stated bare it is an omission; stated with the reason it is a scoping decision.
That satisfies both constraints at once — lead with what was done, and never bury
what was not.

**Attribute the reviewer's numbering.** Never a bare "Major 3": this letter's own
sections are numbered the same way, so the reviewer cannot tell you are pointing
back at them. Write "the reviewer's Major 3" / "Reviewer 1's Major 3".
`lint_manuscript` flags this as `unattributed_reviewer_reference` under the
correspondence profile.

**Before you delete OR restate a qualification, read the manuscript passage.**
Re-deriving a caveat from memory inverts it. Real case, same clauses reordered:

| | |
|---|---|
| manuscript | "…so this describes the candidate set rather than testing it independently; **what it adds is that the 15 act together**, which per-gene significance does not by itself imply." |
| letter | "…so this describes the set rather than testing it independently, **but** per-gene significance does not by itself imply that the 15 act together." |

The manuscript reports a gain; the letter apologises for a shortfall. A letter that
apologises for a result the paper claims is a real inconsistency for a reviewer to
find. Expect contradiction as often as duplication.

And: **new results live in the manuscript.** The letter says what changed and
where; it does not re-derive the finding.

## Step 2b — check the letter from the reviewer's side (`/reviewer-frame-check`)

The audit above is you checking your own writing, and it has a ceiling: you cannot
notice context you never knew was missing. Four consecutive rounds of author
corrections on one letter all traced to that, and two of them were invisible to
any self-check and to `lint_manuscript` — a removed panel described as having
shown the CURRENT cohort when the reviewer saw the earlier one, and diagnostics
quoted at a different parameter value than the candidate set came from. Every word
ordinary; wrong only to a reader tracking what each number is for.

Run `/reviewer-frame-check` before the letter is final: it reads the letter with
ONLY that reviewer's own report plus the manuscript they actually received, and
reports what it had to supply from outside. One run per reviewer, a separate run
with the editor's frame for the cover letter. Findings arrive as `source='ai'`
comments in the normal triage flow — advisory, never blocking.

It must run as a **subagent with a fresh context**. This session knows the
analysis, so it cannot perform the check on itself; asking yourself to pretend
otherwise is the failure mode, not the check.

## Step 3 — deliver

Show the draft. Offer to save it — either as a new section
(`add_section(slug, key='response_letter', title='Response to Reviewers',
body=…)`) so it exports with the paper, or as a standalone file the user can
attach to the resubmission. Default to showing it inline and asking which.

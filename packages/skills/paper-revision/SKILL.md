---
name: paper-revision
description: Walk through open user comments from the dashboard and address them. Use when the SessionStart banner reports open comments, or when the user explicitly asks you to handle their feedback.
---

# /paper-revision

This is the back half of the bidirectional review loop. The dashboard lets
the user leave comments on paragraphs, figures, or specific claims. Those
comments land in Firestore as `reviews` rows with `source='user'`. This
skill walks through them one by one.

## Triage (decision) comes first

Each comment carries a `decision` the author sets in the dashboard:
`accepted` (act on it), `pending` (not triaged yet), or `rejected` (declined).
This is separate from `status` (open → resolved).

- If the author has triaged, your work list is the **accepted** ones:
  `list_reviews(slug, status='open', decision='accepted')`. Address those.
- **Never act on a `rejected` comment** — the author declined it. Leave it.
- For `pending` comments, don't silently rewrite. Surface them and ask the
  author to Accept / Reject (in the dashboard, or tell you), then proceed.
  If they say "just handle all of them," treat pending as accepted.

## Rejected comments need a rebuttal (don't skip them)

A `rejected` comment is NOT done — academic response letters must state *why*
a reviewer point was not adopted, so every rejected comment needs a rebuttal
in its `response`. Treat this as the symmetric half of the accepted workflow.

Run `mcp__co_scientist__review_triage_summary(slug)` to see the gap in one
call — `rejected_without_rationale` lists rejected comments whose `response`
is empty. For each:

1. Draft a polite rebuttal: why the change isn't being made, and — if the
   manuscript already addresses the point — cite where (section / lines).
2. Show the draft to the author for confirmation (don't invent a stance on
   their behalf for substantive points).
3. Record it WITHOUT reopening: `update_review(slug, review_id,
   response='…')` — leave `status='rejected'`.

`prepare_export` also surfaces `rejected_without_rationale` as a warning, so an
unaddressed rejection blocks a clean export. Do this pass before you tell the
author the revision is done, and again right before any export / submission.

## Flow

1. `mcp__co_scientist__list_reviews(slug, status='open', source='user')`
   to fetch every open user comment, newest first. Read each comment's
   `decision` and split into accepted / pending / rejected per the rule above.
2. For each comment, show the user:
   - The section / figure / claim it refers to (from `manuscript_ref` and
     `anchor_text`)
   - The comment text
   - The severity
3. Discuss what to do with each:
   - **Accept** — make the requested change in the manuscript.
   - **Reject** — explain why and respond.
   - **Need more info** — pause that one and come back later.
4. For accepted comments, edit the relevant section via
   `mcp__co_scientist__update_section(slug, key, body=...)`.
5. Mark the comment resolved AND re-anchor it to the revised text:
   `mcp__co_scientist__resolve_paper_comment(slug, review_id,
   status='accepted', response='...', new_anchor_text='<a verbatim phrase
   from the REVISED passage>', new_section='<key if it moved>')`
   - **Always pass `new_anchor_text` when your edit changed the anchored
     sentence.** Otherwise the old anchor no longer matches and the dashboard
     can't show *where* the comment was addressed — it falls back to the top of
     the section. Re-anchoring moves the highlight to the new wording, so the
     reader sees exactly what changed.
   - Use the rendered wording (no `**`/`{doi:…}` markers), a distinctive
     ~5–15 word span that exists verbatim in the new body.
   - **Edited several spots for one comment?** Pass `new_anchor_texts=[…]`
     instead — one verbatim phrase per edited location. The dashboard then
     highlights each and lets the reviewer cycle through them ("N spots").
   - `response` is what the human sees alongside the "✓ Addressed" badge.

## Anchor Drift

If the comment's `manuscript_ref` points to a paragraph that no longer
exists (you or someone else rewrote it), the `anchor_text` and
`manuscript_snapshot` fields tell you what the user was reacting to.

If you can't find the corresponding location in the current manuscript:
- Surface this clearly to the user
- Ask whether to discard the comment as stale, or to find an analogous
  passage to update

If the dashboard flags *several* comments it "couldn't locate" but the
sentences are clearly still there, the stored `section` is likely wrong
rather than the text being gone — run `/reconcile-reviews [slug]` (wraps
`mcp__co_scientist__reconcile_review_anchors`) to re-align them in bulk.

## After editing sections

Editing sections regenerates the manuscript blob, which can leave some
comments pointing at the wrong section. Before you report done, run
`mcp__co_scientist__reconcile_review_anchors(slug, dry_run=True)`; if it
reports any `relocated`, apply it (`dry_run=False`) so the user's remaining
highlights resolve correctly. See `/reconcile-reviews`.

## Comment sources

`list_reviews` surfaces several sources. This skill defaults to
`source='user'` (the author's live dashboard comments). Also:
- `source='reviewer'` — REAL journal reviewer points from a decision letter.
  When the user says "address the reviewer feedback for resubmission," work
  this set; accepted points get revised + a `response` describing the change,
  rejected points get a rebuttal in `response`. Then run `/response-letter`.
- `source='ai'` — internal `/paper-review` self-review (never goes in a
  response letter).
- `source='external'` — anonymous share-link visitors (collaborators).

## After Addressing All Open Comments

Call `mcp__co_scientist__count_open_user_comments(slug)` to confirm the
count is zero. Report the resolution summary back to the user.

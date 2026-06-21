---
name: reconcile-reviews
description: Re-align inline comment highlights after manuscript edits. Use when comment highlights show "위치를 찾지 못했습니다" / "couldn't locate", after importing a manuscript, after bulk section rewrites, or at the end of /paper-revision — anything that regenerates the manuscript blob.
---

# /reconcile-reviews [slug]

Inline comments (`reviews`) carry an `anchor_text` and a stored `section`.
The dashboard highlights each comment by re-matching its `anchor_text`
against the *current* manuscript, so ordinary edits don't break highlights.
But a comment whose stored `section` is wrong — `/paper-review` sometimes
stamps the wrong one, and older comments stored a section *title* where a
*key* is expected — fails to highlight even though the sentence is still
there verbatim. This skill fixes the stored `section` in bulk.

It wraps `mcp__co_scientist__reconcile_review_anchors`.

## Flow

1. Resolve the paper `slug` (ask, or use the one in context). If the user
   didn't name one, run `mcp__co_scientist__list_papers()` and confirm.
2. **Preview** — call
   `mcp__co_scientist__reconcile_review_anchors(slug, dry_run=True)`.
   It returns:
   - `relocated` — `[{review_id, from, to, anchor_preview}]`: comments whose
     `section` will be corrected to where the text actually lives.
   - `ok` — already correct, nothing to do.
   - `truly_missing` — `[{review_id, section, anchor_preview}]`: the anchor
     text is in **no** section, so it really was edited/deleted away.
3. Show the user a short summary: how many will be relocated, how many are
   truly missing (quote each `anchor_preview`). If `relocated` is empty and
   `truly_missing` is empty, report "all comment anchors already resolve
   correctly" and stop.
4. **Apply** — on the user's OK, call
   `mcp__co_scientist__reconcile_review_anchors(slug, dry_run=False)`.
5. **Handle the truly-missing ones** — these are NOT auto-changed. For each,
   show the `anchor_preview` and the comment text
   (`mcp__co_scientist__list_paper_comments(slug, status='open')`) and ask
   the user whether to:
   - re-anchor it to an analogous passage that still exists —
     `update_review(slug, review_id, section=…, anchor_text=…)`;
   - resolve it as addressed —
     `resolve_paper_comment(slug, review_id, status='resolved', response=…)`;
   - or, for a wrong/obsolete AI note, delete it —
     `delete_paper_comment(slug, review_id)`.
6. Report the final tally.

## When to run

Run this right after anything that regenerates the manuscript blob and may
have moved text between sections:

- after `/paper-import` (imported comments often carry title-shaped sections);
- after a batch of `update_section` / `add_section` / `delete_section`;
- at the end of `/paper-revision`, before telling the user you're done;
- whenever the dashboard's comment rail flags anchors it "couldn't locate".

Always preview (`dry_run=True`) first and show the plan; only apply after the
user confirms. Never delete a `source='user'` or `source='external'` comment
to "clean up" — relocate or resolve those; deletion is only for retracting a
wrong `source='ai'` note.

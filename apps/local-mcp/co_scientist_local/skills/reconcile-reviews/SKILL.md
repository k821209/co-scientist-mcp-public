---
name: reconcile-reviews
description: Re-align inline comment highlights after manuscript edits. Use when comment highlights show "위치를 찾지 못했습니다" / "couldn't locate", after importing a manuscript, after bulk section rewrites, or at the end of /paper-revision — anything that regenerates the manuscript blob.
---

# /reconcile-reviews [slug]

The guide's "How this project works" explains why a comment with a wrong
stored `section` fails to highlight, and prescribes this preview-then-apply
pass after bulk edits. This skill is that pass, wrapping
`mcp__scivo__reconcile_review_anchors` (its description has the return shape).
`/paper-review` sometimes stamps the wrong section, and older comments stored
a section *title* where a *key* is expected.

## Flow

1. Resolve the paper `slug` (ask, or use the one in context). If the user
   didn't name one, run `mcp__scivo__list_papers()` and confirm.
2. **Preview** — `mcp__scivo__reconcile_review_anchors(slug, dry_run=True)`.
3. Show the user a short summary: how many will be relocated, how many are
   truly missing (quote each `anchor_preview`). If `relocated` is empty and
   `truly_missing` is empty, report "all comment anchors already resolve
   correctly" and stop.
4. **Apply** — on the user's OK, call
   `mcp__scivo__reconcile_review_anchors(slug, dry_run=False)`.
5. **Handle the truly-missing ones** — these are NOT auto-changed. For each,
   show the `anchor_preview` and the comment text
   (`mcp__scivo__list_paper_comments(slug, status='open')`) and ask
   the user whether to:
   - re-anchor it to an analogous passage that still exists —
     `update_review(slug, review_id, section=…, anchor_text=…)`;
   - resolve it as addressed —
     `resolve_paper_comment(slug, review_id, status='resolved', response=…)`;
   - or, for a wrong/obsolete AI note, delete it —
     `delete_paper_comment(slug, review_id)`.
6. Report the final tally.

## When to run

After the bulk edits the guide names (`/paper-import` — imported comments
often carry title-shaped sections — section batches, the end of
`/paper-revision`), and whenever the dashboard's comment rail flags anchors it
"couldn't locate".

Always preview (`dry_run=True`) first and show the plan; only apply after the
user confirms. Never delete a `source='user'` or `source='external'` comment
to "clean up" — relocate or resolve those; deletion is only for retracting a
wrong `source='ai'` note.

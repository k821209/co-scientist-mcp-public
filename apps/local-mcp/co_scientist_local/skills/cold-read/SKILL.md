---
name: cold-read
description: Read a manuscript section — the abstract first — as a domain expert who has never seen the paper and will not get the rest of it, and report every term, number or claim the text required from outside itself. The check an author cannot run on their own text. Use before a section is marked done, when the user says "would a reader follow this," "read it cold," "이 abstract 처음 보는 사람이 이해되나," or when a term is questioned that you thought was obvious.
---

# /cold-read

**Triggers:** "read it cold," "would a reviewer follow this abstract," "check
it from outside," "처음 보는 사람 입장에서 읽어줘," and, without being asked,
**before the abstract is marked `complete`**.

## Why this is a separate step and not a rule

`/paper-writing` §2b already says "every term defined on first use" and
"definition precedes use." Those rules were loaded, and one abstract violated
them fifteen times — no metric named, no baseline outside the model, "condition"
used three times and defined nowhere. Not carelessness: "is this term defined?"
is the one question an author cannot answer, because the author always knows
what the term means. The missing gloss is invisible from inside exactly the way
it is obvious from outside. `lint_manuscript` cannot see it either (it found
`insider_context: 0` on that abstract): every word was ordinary.

So the fix is a **reader**, not more text in the rule. This skill is the
manuscript-side entry to the same shipped reader `/reviewer-frame-check` uses —
under `profile: manuscript`, where self-containment is the standard and a
pointer elsewhere IS the defect. Read that skill for the reporting rule
("a correct guess is still a finding"), the three kinds, the output shape and
the mapping onto `add_review`. This file says only what differs for a
manuscript section.

## What to hand the reader — and nothing else

| Include | Notes |
|---|---|
| the section text, in a temp file | `get_section(slug, key)` → write `body` to `/tmp/cold-read-<slug>-<key>.md`. **The abstract alone** when checking the abstract: that is exactly what a reader of the abstract holds. |
| the seat | who reads it: "a plant genomicist who has not seen the paper," "an editor screening abstracts" — take the field from the paper's title/journal |
| `profile: manuscript` | always; the agent's default when handed a manuscript is right, but say it |

Not the other sections, not the figures, not the references, not anything from
this session. For a full-manuscript read (before `/paper-export`), hand over
`get_manuscript(slug)` written to one file — still no analysis outputs, no
session notes. The isolation is what makes the check work; see
`/reviewer-frame-check` "Making the isolation real" for what a leaked bundle
does.

```
Task(subagent_type="reviewer-frame-check",
     prompt="""You are a plant genomicist reading this abstract in a journal's
     table of contents. You have not seen the paper and will not see it.
     profile: manuscript

     The abstract:  /tmp/cold-read-plantcad2-abstract.md
     """)
```

## What comes back, and where it goes

The same five blocks as `/reviewer-frame-check` (`--- FINDINGS ---` … `---
BUNDLE_NOTE ---`). For a manuscript, expect mostly `missing_premise`: an
undefined term, a number with no scale or metric, a comparison with no
baseline, a count that does not match what was named. `absent_referent` in an
abstract ("as described above") is a real defect too. `frame_error` cannot
occur — the reader has no prior copy.

Write them as `add_review(source="ai", reviewer_name="Cold Read (<section>)",
section=<key>, severity=…, anchor_text=<verbatim span>,
manuscript_ref="section:<key>")` — the mapping and the one-row-per-defect
rule are in `/reviewer-frame-check` "Emitting the findings"; the only
difference is the `reviewer_name`. Then `list_reviews(slug, source="ai",
status="open")` to confirm the rows landed. They enter the same triage flow as
`/paper-review` output. **Advisory, never blocking.**

Say to the user what the reader held (the one file) so they can judge the run.

## When

- **The abstract, before it is marked done** — a reader there has zero context
  and the text is short, so the check is cheap and the yield is highest.
  Measured once: fifteen findings on an abstract that had passed
  `lint_manuscript` clean.
- The introduction's first paragraph, for the same reason.
- The whole manuscript once, before `/paper-export`, if the paper has never had
  an outside reader.
- Again after the section is rewritten: fixing one term routinely introduces
  the next.

Under Pi and Codex this needs a fresh-context subagent (see the host docs); a
session that already knows the paper cannot perform this check on itself, only
degrade it — say that rather than reporting clean.

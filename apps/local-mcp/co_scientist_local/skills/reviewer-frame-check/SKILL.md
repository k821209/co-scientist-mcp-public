---
name: reviewer-frame-check
description: Read a response letter or cover letter with ONLY what the real reviewer or editor holds — their own report and the manuscript they actually saw — and report every place the text required context they were never given. Use before a response/cover letter is final, when the user says "would a reviewer follow this," "is the letter self-contained," "check the letter from outside," "리뷰어 입장에서 읽어줘."
---

# /reviewer-frame-check

**Triggers:** "would Reviewer 2 follow this," "read the letter cold," "check the
response letter from the reviewer's side," "is the cover letter self-contained,"
"리뷰어 입장에서 읽어줘," or any point where a response/cover letter is about to be
final.

## What this produces

A list of spans in the **letter** that cannot be read with what the recipient
actually has. Not a judgement of the science, not a style pass. Each finding
names the span, what the agent had to supply from outside, and which of three
kinds it is.

Then it writes them as paper comments (`source='ai'`) so they land in the triage
flow the author already uses — accept / reject per finding, exactly like
`/paper-review` output. **Advisory, never blocking.**

## Why the existing tools miss this

| Tool | Reads | Blind to |
|---|---|---|
| `/paper-review` | the MANUSCRIPT, judging science | whether the LETTER is legible from outside |
| `lint_manuscript` | regex phrase-lists + Jaccard sentence pairs (`tools/manuscript_lint.py`) | anything whose words are all ordinary |

Four real failures, all on one response letter, all surviving four consecutive
human corrections:

1. *"we considered"* — an internal deliberation the reviewer never saw. A
   wordlist could catch this; `_STYLE_TELLS` does not contain it.
2. *"an earlier draft"* — a document outside the reviewer's bundle. Same: a
   wordlist could catch it, and none does.
3. A sentence describing a **removed figure panel** as having shown "the 285
   accessions". The panel the reviewers actually saw was the 69-accession one.
   Every word ordinary, lexically clean, and **factually wrong** — wrong
   *because* it was written from inside the session, where 285 is the current
   number.
4. Diagnostics quoted at **K = 3** while the candidate set came from **K = 25**,
   with the two cohorts' numbers compared at mismatched K. No phrase is
   suspicious. Only a reader tracking what each number is *for* catches it.

Cases 3 and 4 are why this skill exists. No lexical rule reaches them, and no
agent that already knows the session will notice them.

## The rule that makes or breaks it

An agent asked "is this clear?" reconstructs the missing context from
surrounding text and answers yes. **That move is forbidden here.** Put this
verbatim in the reviewing agent's prompt:

> Do not report whether you eventually understood a passage. Report what you had
> to infer, guess, or look up that was not given to you. If you had to construct
> a fact to make a sentence work, that sentence is the finding, even if your
> construction turned out right.

The last clause is the whole skill. Case 3 above reads perfectly if you let
yourself assume the panel matched the cohort — the successful reconstruction is
what hid the error. So: a correct guess is still a finding.

## The three kinds

| Kind | Definition | Severity | Example from the failures above |
|---|---|---|---|
| `missing_premise` | a term, symbol or number used before it is defined or scaled | `minor` | "λ = 1.23" with no arm named; "K = 3" with no statement of which K the candidates came from |
| `absent_referent` | refers to something outside the supplied bundle — a draft, a rejected option, an internal decision | `minor` | "we considered"; "an earlier draft" |
| `frame_error` | describes the reviewer's OWN prior experience incorrectly | `major` | the 285-accession panel the reviewer never saw |

`frame_error` is the highest-value kind and the only one that is a **factual
bug** rather than a readability one. A `frame_error` tells the reviewer something
false about what they read. Report these first and say so plainly; do not soften
them into "could be clearer".

Severities are limited to `major | minor | suggestion`
(`tools/reviews.py:27`) — map as in the table and put the kind name in the
comment text so the author can sort.

## The context bundle

The harness assembles this. **The reviewing agent must not widen it**, and that
includes not reaching for anything convenient.

### Per-reviewer run

| Include | Notes |
|---|---|
| the ORIGINAL SUBMISSION | the snapshot the decision was issued against — **not** the current manuscript |
| that reviewer's OWN report | theirs only: `list_reviews(slug, source='reviewer')`, filtered to one `reviewer_name` + `round` |
| the response letter | the deliverable under review |
| the revised manuscript | **only if the letter cites it**, and only the cited sections |

Nothing else. No session transcript. No `analysis/**`. No intermediate figures.
No prior drafts of the letter. **No other reviewer's report** — different
reviewers held different material, so a passage that is legible given Reviewer
1's report may be a `missing_premise` for Reviewer 2. That is a real finding and
it disappears the moment you merge the reports.

**Run one agent per reviewer.** Not one agent over all reports.

### Editor run (cover letter) — separate run

| Include | Notes |
|---|---|
| the decision letter | the editor's own words |
| the ORIGINAL SUBMISSION | same snapshot |
| reviewer reports | optional; include only if the cover letter refers to them |

The cover letter is written to the editor's frame, not any reviewer's. Do not
fold it into a reviewer run.

### Getting the original submission

There is **no manuscript version history** in this system — verified: nothing in
`tools/sections.py`, `tools/papers.py` or `tools/exports.py` stores a
point-in-time manuscript, and `get_manuscript(slug)` returns only the current
assembled blob. So:

1. `list_exports(slug)` — the submitted `.docx`/`.pdf` is normally there.
2. `get_paper_state(slug)` → `paper.submission` (`manuscript_id`,
   `submitted_at`) to corroborate which one.
3. `list_materials()` — the submitted PDF is often uploaded here.

**Ask the user which file was submitted and wait for an answer.** The newest
export is often wrong (a superseded revision package sorts to the top by date;
see `/tracked-changes-export` step 1 for the case where this shipped). Every
check in this skill is blind to a wrong baseline: the run completes, the findings
look plausible, and they are measured against a document nobody read. If no
snapshot of the submitted manuscript exists, **say so and stop** — with the
current manuscript as the baseline this skill cannot detect a single
`frame_error`, which is its whole reason to exist.

`list_materials()` is **project-wide, not per-paper**, and its docstring names
"prior drafts" as expected content. Do not hand the agent the material list.
Select specific `material_id`s yourself and pass only those files.

## Making the isolation real

The reviewing agent will usually be spawned from a session that already knows
everything. Isolation is therefore something you construct, not something you
have.

**Nominal isolation does not work.** "Pretend you don't know about the 285
accessions" fails: the number is in context, the model has read it, and the
sentence still parses. If the current session has read the analysis, it cannot
run this check on itself — it will supply case 3 silently, which is exactly what
already happened.

**So: spawn a subagent with a restricted prompt.** A fresh context is the
mechanism; the prompt is the contract.

Put in the prompt:

- The verbatim reporting rule from above.
- The role: "You are Reviewer 2 of <journal>. You read this manuscript once,
  months ago. You have your own report in front of you and nothing else."
- **File paths, not contents**, for the bundle — let the agent read them with its
  own file tools. Paths keep the boundary auditable; pasted text does not.
- The three kinds and the output shape (below).
- An explicit refusal clause: "If you find yourself wanting a file that is not
  in this list, do not open it. Report the sentence that made you want it as a
  finding."

Do NOT put in the prompt:

- any part of this session's transcript, reasoning, or plan
- the current manuscript, unless the letter cites it
- numbers, cohort sizes, K values, or panel contents from your own context —
  writing "note the cohort is now 285" into the prompt destroys the check
- the other reviewers' reports
- the letter's revision history, or what a previous frame-check run found
- reassurance about what the letter means ("this refers to Figure 2b") — that IS
  the finding

Two honest limits, worth stating to the user rather than papering over:

- **A subagent that inherits the parent's conversation is not isolated.** If
  your harness cannot give a genuinely fresh context, this check is degraded, not
  performed. Say that instead of reporting clean.
- **You cannot verify isolation from inside.** What you can verify is the bundle:
  list the exact files handed over, and let the author see the list. If the list
  is right, the run is worth trusting; if it includes `analysis/` or a session
  log, it isn't.

### Output shape (require exactly this)

```
kind:      frame_error | missing_premise | absent_referent
span:      "<verbatim quote from the letter, 5–20 words>"
supplied:  <what you had to infer, guess, or look up — one sentence>
why:       <what the reviewer's own material actually says, for frame_error>
```

Reject any finding without a verbatim `span`; it cannot be anchored, and an
unanchored finding leaves the triage flow.

## Emitting the findings

The letter must be a **section** first, or anchors dangle. `add_review` does not
validate `anchor_text` (only `update_review`/`resolve_paper_comment` do —
`tools/reviews.py:57`), so a comment anchored to a standalone `.docx` is accepted
and then silently fails to highlight. Save the letter per `/response-letter`
step 3:

```
mcp__co_scientist__add_section(slug, key='response_letter',
  title='Response to Reviewers', sort_order=<after the last section>, body=…)
```

`sort_order` is required (`tools/sections.py:91`). Note the letter then exports
with the paper — check that against the journal package the author wants.

One row per finding:

```
mcp__co_scientist__add_review(
  slug,
  comment="[frame_error] Reviewer 2 saw the 69-accession panel, not 285. "
          "Supplied from outside: that the removed panel matched the current cohort.",
  source="ai",
  reviewer_name="Frame Check (Reviewer 2)",
  section="response_letter",
  severity="major",
  anchor_text="<verbatim span from the letter>",
  manuscript_ref="section:response_letter",
)
```

- `source='ai'` is correct and deliberate: these are internal findings and must
  never reach a response letter (`source='reviewer'` is the journal's real
  points; see `/response-letter`).
- `reviewer_name` carries which run produced it — `Frame Check (Reviewer 2)`,
  `Frame Check (Editor)`. This is the only place the per-reviewer split survives.
- One row per finding even at 30 findings — the dashboard is built around
  per-passage anchoring.
- Use `anchor_prefix` / `anchor_suffix` when the span repeats.
- Then confirm: `list_reviews(slug, source='ai', status='open')`.

## Where it fits

**In `/paper-revision`, before the letter is final.** After the reviewer points
are addressed and the letter is compiled, before it is shown as done. The
findings then flow through the same `source='ai'` loop `/paper-revision` already
documents: address → `resolve_paper_comment` anchored to the revised span, or
defer → `update_review(response='…')`.

**In `/paper-export`, at pre-flight.** Report open frame-check findings alongside
`prepare_export`'s warnings. Report, not refuse.

**Never blocking.** The author decides, exactly as with the review-comment loop.
A `frame_error` is worth saying twice and stopping to name out loud — but if the
author says ship it, ship it. Do not gate `export_to_path` on this skill.

Re-run after the letter is edited: a rewrite that fixes one span routinely
introduces a new `missing_premise`, and the second run is cheap.

## Gaps

Real capabilities this skill needs and the system does not have. Stated so they
are not rediscovered:

- **No manuscript version history.** The single biggest gap. There is no tool
  returning the manuscript as submitted — no `list_journal_versions`, nothing
  equivalent (verified across all ~200 tools in
  `apps/local-mcp/co_scientist_local/mcp_server.py`). The baseline is whatever
  file the author points at, which is why the confirmation step above is a gate.
  A snapshot written at `set_paper_submission(status='submitted')` would close
  this and make the check reliable.
- **Reviewer reports are not scoped as bundles.** `list_reviews(slug,
  source='reviewer')` returns every reviewer's points together; the per-reviewer
  split is done by filtering `reviewer_name` + `round` in the caller. Nothing
  enforces that one run saw only one reviewer's material.
- **No decision-letter or cover-letter object.** The decision letter exists only
  as whatever the author pasted or uploaded to `list_materials()`, and the cover
  letter only as a section or a local file. The editor run therefore depends on
  the author naming both.
- **No finding-kind field on reviews.** The kind is carried as a `[frame_error]`
  prefix in `comment` because `severity` has only three values
  (`tools/reviews.py:27`) and there is no free-form label field. Filtering by
  kind means string-matching the comment.

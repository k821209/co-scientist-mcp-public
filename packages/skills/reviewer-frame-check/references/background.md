# Why this check exists, calibrating it, and what it cannot do

_Part of `/reviewer-frame-check`. Read from `SKILL.md` once per paper to calibrate, or when a run's findings look wrong._

## Why the existing tools miss this

| Tool | Reads | Blind to |
|---|---|---|
| `/paper-review` | the MANUSCRIPT, judging science | whether the LETTER is legible from outside |
| `lint_manuscript` | phrase lists and near-duplicate sentence pairs | anything whose words are all ordinary |

Four real failures, all on one response letter, all surviving four consecutive
human corrections:

1. *"we considered"* — an internal deliberation the reviewer never saw. A
   wordlist could catch this; the lint's does not contain it.
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

## Calibrating it (do this once per paper, not per run)

A run that returns findings proves it is sensitive; it does not prove it
discriminates. The first live run returned 38 findings on a letter that had been
through four rounds of author correction plus two greps for exactly this class —
encouraging, and not yet evidence that it says *nothing* when there is nothing to
say.

So, once, before you trust it as a gate on a given paper: run it against a
**pre-correction** version of the letter and confirm it recovers the defects the
author already caught by hand. If it misses those, the bundle is wrong (almost
always: no submitted manuscript, so the `frame_error` third is dead) rather than
the check being weak.

This cannot be a unit test. The check is a language model reading prose, so there
is nothing deterministic to assert; the calibration is a procedure, and the honest
version is to record its outcome in project memory next to the submitted-baseline
pointer.

## Gaps

Real capabilities this skill needs and the system does not have. Stated so they
are not rediscovered:

- **The baseline is whatever the user registered.** `list_submissions` returns
  the file they said was sent; nothing can check that it is the file the
  reviewers actually opened, so the confirm-once step stays a gate.
- **Per-seat scoping is available but not enforced.** `list_reviews` now takes
  `reviewer_name` and `round`, so isolating one seat's registered points is a tool
  call rather than hand-slicing. What nothing can enforce is the FILE side: if the
  decision letter was uploaded as one document containing every reviewer, passing
  it wholesale merges the seats no matter what the filters say. The agent's
  `bundle_note` is the only backstop, and it is a report after the fact.
- **No decision-letter or cover-letter object.** The decision letter exists only
  as whatever the author pasted or uploaded to `list_materials()`, and the cover
  letter only as a section or a local file. The editor run therefore depends on
  the author naming both.
- **No finding-kind field on reviews.** The kind is carried as a `[frame_error]`
  prefix in `comment` because `severity` has only three values and there is
  no free-form label field. Filtering by
  kind means string-matching the comment.

# The editor's first page

_Part of `/paper-writing`. Read from `SKILL.md` when the title or the abstract is being finalised, when a cover letter is written, and before a paper goes to a journal — the first time, or again after a rejection._

An editor at a selective journal has described what the first decision is made
from: a screen showing **the title, the abstract and the cover letter — not
even the author list** — and, as a second impression, **the figures and their
captions**, where many reviewers also start. The same editor handles 50 to 100
papers a month and rejects most without review, and suspects that some of
those had real significance nobody could see through the way they were
written (W. S. Warren, "Beating the odds for journal acceptance", *Sci. Adv.*
8, eadd9147, 2022, doi:10.1126/sciadv.add9147). That is one editor at one
journal. It is used here for what it says an editor HOLDS at each step, which
is what a reader check needs; the house rules of any particular journal come
from `/journal-requirements`.

So three pieces of text carry the paper before anyone reads it, and none of
them is a section the body-text rules were written for.

## The title

- **The most essential finding, said plainly.** If the paper has one result a
  reader should leave with, the title is that result or its subject — not the
  method's name, not a question, not a pun.
- **No adjective of merit.** "Novel", "robust", "comprehensive",
  "unprecedented" tell the editor how to feel and nothing about what was
  found. The rule against judgmental adjectives in §2a applies here with the
  least room: there is no sentence beside the title to carry the measurement.
- **No word the reader has to look up.** A title that needs a dictionary was
  written with one.
- **Proofread it as its own document.** A slip in a title is read as a
  statement about the care taken with the data.

## The abstract, as the editor reads it

`/paper-writing` §1 says what an abstract contains and `/cold-read` checks that
it stands alone. One thing is added by this seat: the abstract is read **for
why the work matters to someone outside the subfield**, and its first sentence
is read hardest. Overstatement lowers interest — for the editor and for the
readers after them — so the claim is the size the result supports (§2d-ter),
and the first sentence is checked for grammar before anything else is.

## The cover letter

It is not a summary of the abstract and not a list of the authors'
credentials. The editor reads it beside the abstract, so it says what the
abstract has no room for:

1. **The finding, in a sentence**, matching the abstract's — the same number,
   the same claim. A letter and an abstract that disagree is the first thing a
   reader with both in front of them sees.
2. **Why it matters beyond the field** — who else changes what they do or
   believe because of it.
3. **Where it stands among what was known.** The work it builds on and departs
   from, named, with what that work could not do and this does. "Broader
   context" means the landscape of the field; a list of papers from
   high-profile journals is not context.
4. **The fit**: why this journal's readers, in a sentence (the scope and
   audience recorded by `/journal-requirements`).
5. Only if they apply — see the next two sections: what happened to the paper
   before, and whom the authors suggest.

Store it as a section with `key="cover_letter"` so it exports with the paper
and the reader below can be handed it. Draft it in the language the journal
reads.

**The comparison to prior work is the part to get right, and it is the same
comparison the manuscript makes.** The closest earlier work is cited where the
reader meets the claim, described fairly, and not made smaller than it was:
its author is a likely reviewer. If you cannot name the closest work, that is
a gap for `/literature-review`, not a sentence to write around.

## A paper that has been somewhere before

Register what was sent where (`list_submissions(slug)` is the record; the
guide's "submitted baseline" section says how it is kept). Then:

- **Sent to another journal and rejected.** Rejection is not the problem;
  ignoring the reviews is — the same reviewer is often asked again. Bring the
  earlier reports in as comments (`/response-letter` does this for a decision
  letter) and address them before resubmitting elsewhere. In the new letter,
  say what changed; offering the earlier reviews with an account of the
  changes is something an editor has described as working. **Check every
  journal name in the letter and the manuscript** — a letter addressed to the
  previous journal sets the tone for everything after it.
- **The same journal again.** Not a near-duplicate under a new title. Unless
  the editor asked for a resubmission, send it again only for a reason that is
  stated at the top of the letter — new data, a changed conclusion.
- **A transfer the journal offers.** Accept one only to a journal whose
  readers are the paper's readers; say no to a sibling title that is not.

## Suggesting an editor and reviewers

Only when the journal asks, and only from what the USER tells you — these are
people, and a name you propose from a reference list is a guess about someone's
expertise and independence.

- **An editor**: the one whose field covers the work. If no editor on the
  journal's list fits, say that to the user — it is evidence about the fit, and
  the same editor reads repeated refusals the same way.
- **Reviewers**: competent in the field AND independent of the authors. Not a
  close colleague, not a recent co-author or collaborator, not a former
  advisor or student — a conflict found after the review is in can get the
  review discarded and costs weeks. For each name the user gives, ask what
  makes them suited and whether any author has published with them recently;
  `search_works` can check a co-authorship, and cannot show that there is
  none. The letter may say why a person would be a good reviewer.
- Follow the journal's own rule on how many and on exclusions; record it in
  the requirements' notes.

## Before it is sent: the reader

Whether the title, the abstract and the letter say what you think they say is
not a question you can answer — you know what was meant. Hand exactly those
three to the reader: `/reviewer-frame-check`, "First submission — the editor's
first page" (`profile: first_page`). It answers in its own words what the
finding is, why it matters and what it advances, or says `not stated`. Compare
that with what you meant; the difference is the edit.

For the second impression, `/cold-read` has the matching run: the display
items alone.

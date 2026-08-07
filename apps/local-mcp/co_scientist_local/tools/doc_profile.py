"""What kind of document is this, and whose job does it serve?

Review checks are not document-agnostic, and getting this wrong pushes a document
the WRONG WAY. The two failure directions are opposites:

  - In a MANUSCRIPT, deferring elsewhere is the defect. Self-containment is the
    standard; "the diagnostics are in Methods" is a hole.
  - In a RESPONSE LETTER, deferring is correct behaviour. The letter's job is to
    say what was asked, what was done, and where to find it. A letter that
    re-derives the analysis is a worse letter.

Measured, on a real revision: a frame check run without this distinction returned
17 "missing premise" findings against a response letter which, taken at face value,
were instructions to write the paper a second time — acting on them would have
grown the letter past 5,000 words, while acting on the findings that DID apply
correctly shortened it from 3,600 to 2,580.

The rule that separates them is not "is this explained?" but **can the recipient do
their job without it?**

  | recipient's job                              | so a pointer elsewhere is |
  |----------------------------------------------|---------------------------|
  | reviewer deciding whether a point was met    | fine                      |
  | editor deciding whether to send it back out  | fine                      |
  | reviewer evaluating the science (manuscript) | the defect                |

What does NOT vary by document: a factual error about the copy the recipient
already holds, and a claim the document itself makes but does not support. Those
are defects everywhere.
"""
from __future__ import annotations

MANUSCRIPT = "manuscript"
RESPONSE_LETTER = "response_letter"
COVER_LETTER = "cover_letter"

# Section keys that are correspondence rather than manuscript body. `add_section`
# takes a free-form key, so match the spellings the skills actually create
# (/response-letter writes key='response_letter') plus the obvious variants.
_KEY_KINDS = {
    "response_letter": RESPONSE_LETTER,
    "response_to_reviewers": RESPONSE_LETTER,
    "responses_to_reviewers": RESPONSE_LETTER,
    "rebuttal": RESPONSE_LETTER,
    "reviewer_response": RESPONSE_LETTER,
    "cover_letter": COVER_LETTER,
    "letter_to_editor": COVER_LETTER,
}


def section_kind(key: str | None) -> str:
    """Classify one section by its key. Defaults to MANUSCRIPT.

    Deliberately keyed on the section, not on the paper: a revision keeps its
    response letter as a section ALONGSIDE the manuscript body, so the two live in
    one paper and `doc_type` ("paper" / "report") cannot separate them.
    """
    if not key:
        return MANUSCRIPT
    return _KEY_KINDS.get(str(key).strip().lower().replace("-", "_"), MANUSCRIPT)


def is_correspondence(key: str | None) -> bool:
    """True for a response/cover letter section — a document whose recipient is
    deciding compliance, not evaluating method, so pointing elsewhere is correct."""
    return section_kind(key) != MANUSCRIPT

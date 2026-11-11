---
name: tracked-changes-export
description: Build a real tracked-changes .docx showing what changed between the previously submitted manuscript and the current revision. Use when the user says "tracked changes," "marked-up version," "changes file," "변경 추적," "what did we change since submission," or a journal asks for a marked copy alongside the clean one.
---

# /tracked-changes-export

**Triggers:** "make a tracked-changes version," "marked-up manuscript,"
"changes docx," "변경 추적본," "show the reviewer what we changed," "journal
wants a marked copy."

## What this produces

A `.docx` carrying genuine OOXML revision marks (`w:ins` / `w:del`) between the
previously submitted manuscript and the current one. Word shows them in the
review pane with working Accept / Reject; Google Docs opens them as suggestions.

It needs two rendered documents, and which two is step 1. For a paper that
has been submitted, the new one is NOT a fresh `/paper-export` — step 1 says
why.

## Hard rules

1. **Compare two rendered `.docx` files. Never diff the markdown.**
   A markdown diff converted to `.docx` produces coloured strikethrough text
   with **zero** `w:ins`/`w:del` elements — Word's review pane shows nothing and
   nothing can be accepted or rejected. It also leaks markdown into the body
   (`**Authors:**` appearing literally). This is not hypothetical: the vcf2hash
   2026-07-28 submission shipped exactly that file.
2. **Edit OOXML with `lxml`, never with regular expressions.** A regex pass that
   unwrapped `<w:ins>` produced a `mismatched tag` document. LibreOffice still
   opened it, so "it opens" proves nothing.
3. **Never conclude text is MISSING from a `.docx` on python-docx's word.**
   `paragraph.text` and `paragraph.runs` do not expose runs inside `w:sdt`
   (structured document tags / content controls) — Zotero and Mendeley citation
   fields are exactly that, so a journal manuscript is where this is likeliest.
   The text is present, renders in Word, and is invisible to the reader you used.
   Read raw `w:t` before you believe any absence. See "Absence is a claim about
   your reader" below; this is rule 2 applied to READING, and it has shipped a
   duplicated sentence into a submitted manuscript.
4. **Validate before shipping.** See the checklist at the end.
5. **Never pick the baseline yourself — ask, and wait for an answer.** Every
   validation check in this skill is blind to which OLD file you chose, so a wrong
   baseline ships a file that passes all seven checks and diffs against a document
   the reviewers never saw. See step 1; this is a gate, not advice.

## Flow

### 1. Locate the two documents

- **OLD** — the version the reviewers actually received:
  `list_submissions(slug)` → `get_submission(slug)`. If it is empty, ASK — do not
  substitute an export. (An earlier version of this step said to look in
  `list_exports` under `exports/.<label>/`; that is the newest-export trap hard
  rule 5 exists to prevent, and nothing in the exports tool writes such a path.)

  Before either document: if `get_paper_state(slug)["paper"]["submission_sync"]`
  reads `unreconciled`, the SECTIONS may not match the sent file — see
  `/paper-revision` "If this paper has been SUBMITTED". A revision built on
  sections that drifted from the baseline diffs against text nobody sent.
- **NEW** — the revised document. **Edit a COPY of the OLD file; do not export a
  fresh one from co-scientist.** The submitted `.docx` carries material that never
  existed in the sections and cannot be regenerated: Key Points, a Biographical
  Note, the journal's author/affiliation formatting, content controls from a
  reference manager. A `/paper-export` looks complete and silently omits all of
  it. That shipped: a R2 revision was started from a fresh export and the Key
  Points and Biographical Note were simply gone — the user caught it by reading
  the file ("제출본의 키포인트 같은것들이 다 빠지네").

  So the revision is applied TO the submitted document. Use `/paper-export` for a
  fresh manuscript, not for a revision of one that has already been sent.

**STOP and confirm the pairing with the user before running — this is a gate.**
Name both files and wait for an answer; do not proceed on your own inference.
Nothing downstream can catch a wrong choice: the marked-up file will be
structurally perfect and diffed against a document nobody has read.

**The newest archived export is often the WRONG answer.** A revision package
prepared and then superseded before it was ever submitted is the classic trap, and
it sorts to the top by date and looks more authoritative than the file that was
actually sent. This happened: a marked-up copy was built against an n=69 revision
packaged locally on Jul 28 but never submitted (the cohort had grown to n=285),
so the diff was against a document that existed nowhere outside the repo. Asking
cost one question, and the answer was the OLDER file.

Directory mtimes are not evidence of what the journal received. **Call
`list_submissions(slug)` first** — the first entry is the registered baseline,
with the file, the journal, the date it was sent, and a checksum;
`get_submission(slug)` downloads it verified. That is the whole of step 1 when
it is there.

If it is EMPTY, ask the user and have them register it (the paper page's
Exports → Submitted card takes an upload of the file they actually sent).
Older projects may still carry the pointer as a `Submitted baseline for <slug>:`
line in `get_project_memory()` with the snapshot in Materials — read that too,
and offer to register it properly. `paper.submission` (`manuscript_id`,
`status`) corroborates but does not identify the file.

Sanity signal worth surfacing, not an error: the intended pair should share a
title and author block. If your comparison inserts the entire author/affiliation
front matter as one huge insertion in the first paragraph, the two files use
different front-matter formats — which often means they are from different eras.
Say so and re-confirm.

### 2a. Build the marks directly — the first attempt

`build_tracked_changes(old_path, new_path, out_path, author)` writes NEW with
every difference from OLD as real `w:ins` / `w:del`, with no LibreOffice
involved, and **verifies itself before writing**: accepting every mark must
reproduce NEW and rejecting every mark must reproduce OLD, paragraph for
paragraph. That is a check the LibreOffice path cannot make, and it is the
one that catches a deleted paragraph landing one slot early — invisible to
every row of the step 6 table. On a real revision round it produced the
marked main text in seconds where the LibreOffice macro path produced nothing
(soffice idle, exit 0, empty log) on Linux, and the user reports the same
flakiness on macOS.

Read the tool's return: what it does not produce (formatting-only revisions,
moved text — shown as delete + insert) is listed there. When the revision is
mostly of that kind, or the result reads wrong, go on to the LibreOffice
compare (step 2); otherwise skip to step 5 (tables) and step 6.

### 2. If the builder cannot do it — the LibreOffice compare

`build_tracked_changes` does not produce formatting-only revisions or moved
text, and it refuses rather than write a file it cannot verify. For those
cases the fallback is LibreOffice's own document compare, run headless:
`references/libreoffice-fallback.md` — an isolated profile, the compare
macro, how to DIAGNOSE a run that produced nothing (do not just retry), and
stamping the author on its marks, which otherwise all say "Unknown Author".
Its output goes through steps 5 to 7 like the builder's.

### 5. Resolve tracked changes inside tables

Google Docs' importer crashes on row-level table revisions:

```
TableImporter.handleRowSuggestStart → RunContentChange.getAuthor()
  NullPointerException
```

The XML is valid when this happens — every element has an author, deleted rows
use `w:delText` correctly — so this is an importer limitation, not a defect to
repair. Remove the failing construct instead, keeping every body-text change:

- delete `w:del` elements inside `w:tbl` (accepts the deletion)
- unwrap `w:ins` elements inside `w:tbl`, keeping their children; remove
  empty ones, which are `trPr`/`rPr` markers
- **then drop any table left with no text and no graphics** — a wholly deleted
  table otherwise survives as an empty row skeleton

Tables regenerated wholesale carry no useful row-by-row diff anyway, so nothing
a reviewer needs is lost. Say in the response letter that tables were rebuilt.

```python
import lxml.etree as ET
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def unwrap(el):
    par = el.getparent(); i = list(par).index(el)
    for j, ch in enumerate(list(el)):
        par.insert(i + j, ch)
    par.remove(el)

for tbl in root.iter(W + "tbl"):
    for d in list(tbl.iter(W + "del")):
        if d.getparent() is not None:
            d.getparent().remove(d)
    for ins in list(tbl.iter(W + "ins")):
        if ins.getparent() is None:
            continue
        ins.getparent().remove(ins) if len(ins) == 0 else unwrap(ins)

for tbl in list(root.iter(W + "tbl")):
    has_text = any((t.text or "").strip() for t in tbl.iter(W + "t"))
    has_gfx = any(True for _ in tbl.iter(W + "drawing")) or \
              any(True for _ in tbl.iter(W + "pict"))
    if not (has_text or has_gfx):
        tbl.getparent().remove(tbl)
```

### 6. Validate — all of these, every time

| Check | How |
|---|---|
| XML well-formed | `lxml.etree.fromstring(document.xml)` |
| Zip intact | `zipfile.ZipFile(f).testzip() is None` |
| Opens as a document | `docx.Document(f)` — report paragraph and table counts |
| Real revision marks | count `w:ins` / `w:del` — must be non-zero |
| Every mark attributed **to a real name** | `Counter(e.get(W+"author") for e in ins + dele)` — **print the set**, and FAIL when it is empty, contains `None`, or contains any of `Unknown Author` / `Unknown` / `Author` / `""`. A marked-up copy normally has exactly one author |
| Media accounted for | `word/media/` count matches **the input you compared** — normally every figure, since you compare the real documents. 0 is only correct if you took the `strip_images()` fallback, which must then be stated in the response letter |
| No empty tables | every `w:tbl` has text or graphics |
| **python-docx sees the whole document** | compare its text against raw `w:t` — see below. Run this BEFORE any edit premised on something being absent |
| **Accept-all == NEW and reject-all == OLD** | `verify_tracked_changes(marked, old, new)` — on the builder's output this already ran; on LibreOffice's output it is the only check that sees a mark in the wrong slot. Both booleans must be true |

Report the insertion / deletion counts to the user **and the author set** —
`authors: {'Yang Jae Kang': 848}`. Printing the value is as important as failing on
it: `5 all authored: OK` is a line an operator skims past, and that is precisely how
848 marks attributed to `Unknown Author` shipped through a checklist that "passed".

The general shape, worth carrying to every check you write here: **a validation that
asks "is the field populated" cannot see a populated-but-useless field**, and a
placeholder emitted by a tool is exactly the case that satisfies presence while
failing intent. Test the value, and show it.

The ratio is informative too: insertions far exceeding deletions means the revision
mostly *added* material, which is worth stating in the response letter.

### Absence is a claim about your reader, not about the document

Before you report anything as missing, truncated or divergent — and before you
"restore" it — check that the reader you used can see the whole document:

```python
import zipfile
import lxml.etree as ET
from docx import Document

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def readable_text(path):
    """What python-docx shows, and what is actually in the file."""
    pd = "\n".join(p.text for p in Document(path).paragraphs)
    raw = "".join(
        t.text or ""
        for t in ET.fromstring(
            zipfile.ZipFile(path).read("word/document.xml")).iter(W + "t"))
    return pd, raw

pd, raw = readable_text(src)
# Not equality: python-docx drops table and header text by this measure too.
# A LARGE shortfall is the signal — sdt, text boxes, or anything else it skips.
assert len(raw) - len(pd) < 0.02 * len(raw), (
    f"python-docx sees {len(pd)} chars of {len(raw)}; something is hidden from "
    f"it. Search the raw text before concluding anything is missing.")
```

To check one specific string, search `raw`, never `pd`:

```python
raw.count("independently constructed")     # the answer
pd.count("independently constructed")      # a fact about python-docx
```

> **Recorded: a caption "restored" that was never broken** (GeneReL,
> DATABASE-2026-0057.R1, 2026-08-27). A Figure 4 legend read as truncated
> mid-sentence — the rest of it sat in a `w:sdt` between two runs, so
> `paragraph.text` skipped it. It was reported to the user as a defect in their
> submitted file, "repaired", and shipped: the same sentence appeared TWICE in
> the clean and tracked-changes documents, and the user caught it by eye. The
> same blind spot also produced three confident false reports — `44.7` "absent"
> (present twice), `independently constructed` "absent" (present), and a
> manuscript/submission "divergence" that did not exist — which cost the user a
> pointless which-file-is-real question and reversed a revision decision on a
> false premise.
>
> Same lesson as the images retraction above, from the other direction: **"I
> cannot see it" is evidence about the instrument.** The skill already forbade
> editing OOXML with the wrong tool; nothing said the same about reading it, and
> reading is where the damage started.

### 7. Upload

`export_to_path` does not touch this file — it was built locally. Attach it
explicitly, or it will not appear on the dashboard:

```
mcp__scivo__attach_export(slug, local_path=..., scope="main")
```

## If Google Docs still refuses

Fall back in this order:

1. Ask the user to open it in desktop Word, which is more tolerant.
2. Have the user run Word's own **Review → Compare** on the two documents. Both
   are already on the dashboard, so this needs nothing from us.
3. Only as a last resort, produce a colour-marked copy — and tell the user
   plainly that it is not real tracked changes and cannot be accepted or
   rejected.

## Requirements

- Python with `lxml` and `python-docx` (the builder in 2a needs nothing else)
- LibreOffice (`soffice`) on PATH — only for the fallback compare

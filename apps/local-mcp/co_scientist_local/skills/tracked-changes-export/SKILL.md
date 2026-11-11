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
   (`**Authors:**` appearing literally).
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

The guide's "The SUBMITTED BASELINE" (under "Project memory") is the rule for
both documents — read it first. On this skill's surface:

- **OLD** — the version the reviewers actually received: `list_submissions(slug)`,
  then `get_submission(slug)` downloads it verified. Empty → ask, and have the
  user register the file they actually sent; never substitute an export (the
  newest-export trap). Directory mtimes are not evidence of what the journal
  received, and `paper.submission` (`manuscript_id`, `status`) corroborates but
  does not identify the file. An older project may carry the baseline as a
  note in `get_project_memory()` instead — the guide says how to treat it. If `submission_sync` reads `unreconciled`, the
  sections may not match the sent file — reconcile first, per the guide.
- **NEW** — **edit a COPY of the OLD file; do not export a fresh one** (the
  guide's "And the reverse direction"). Use `/paper-export` for a fresh
  manuscript, not for a revision of one that has already been sent.

**STOP and confirm the pairing with the user before running — this is a gate.**
Name both files and wait for an answer; do not proceed on your own inference.
Nothing downstream can catch a wrong choice: the marked-up file will be
structurally perfect and diffed against a document nobody has read.

Sanity signal worth surfacing, not an error: the intended pair should share a
title and author block. If your comparison inserts the entire author/affiliation
front matter as one huge insertion in the first paragraph, the two files use
different front-matter formats — which often means they are from different eras.
Say so and re-confirm.

### 2a. Build the marks directly — the first attempt

`build_tracked_changes` is the first attempt: no LibreOffice, and it verifies
its own round trip before writing (its description says what it does and does
not produce). The LibreOffice path cannot make that check and is flaky on Linux
and macOS. When the revision is mostly what the builder does not produce, or the
result reads wrong, go on to the LibreOffice compare (step 2); otherwise skip to
step 5 (tables) and step 6.

### 2. If the builder cannot do it — the LibreOffice compare

For what the builder does not produce, or refuses to write, the fallback is
LibreOffice's own document compare, run headless:
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

**"I cannot see it" is evidence about the instrument.** A "restore" of text that
was only hidden from python-docx ships the same sentence twice.

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

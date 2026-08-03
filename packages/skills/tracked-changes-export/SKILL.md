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

This is a companion to `/paper-export`, not a replacement. Run `/paper-export`
first so a clean current `.docx` exists.

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
3. **Validate before shipping.** See the checklist at the end.

## Flow

### 1. Locate the two documents

- **OLD** — the version the reviewers actually received. Check
  `mcp__co_scientist__list_exports(slug)`; submitted files are usually archived
  under `exports/.<label>/`. If the previous submission was never exported to
  `.docx`, say so and stop — there is nothing to compare against.
- **NEW** — the current clean export from `/paper-export`.

Confirm the pairing with the user before running. Comparing against the wrong
baseline produces a plausible but wrong marked-up file.

### 2. Prepare an isolated LibreOffice profile

Use a scratch profile so the user's own LibreOffice settings are untouched.

```bash
PROF=/tmp/lo_profile
rm -rf $PROF && mkdir -p $PROF
soffice -env:UserInstallation=file://$PROF --headless --terminate_after_init
```

### 3. Install the compare macro

Write to `$PROF/user/basic/Standard/Module1.xba`, substituting absolute paths:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script"
               script:name="Module1" script:language="StarBasic">
Sub DoCompare
  Dim aHidden(0) As New com.sun.star.beans.PropertyValue
  Dim aCmp(0)    As New com.sun.star.beans.PropertyValue
  Dim aSave(0)   As New com.sun.star.beans.PropertyValue
  Dim oDoc As Object, oDisp As Object
  aHidden(0).Name = "Hidden" : aHidden(0).Value = True
  oDoc = StarDesktop.loadComponentFromURL("file://NEW_PATH", "_blank", 0, aHidden())
  oDisp = createUnoService("com.sun.star.frame.DispatchHelper")
  aCmp(0).Name = "URL" : aCmp(0).Value = "file://OLD_PATH"
  oDisp.executeDispatch(oDoc.getCurrentController().getFrame(), _
                        ".uno:CompareDocuments", "", 0, aCmp())
  aSave(0).Name = "FilterName" : aSave(0).Value = "MS Word 2007 XML"
  oDoc.storeToURL("file://OUT_PATH", aSave())
  oDoc.close(False)
End Sub
</script:module>
```

Load the NEW document and merge the OLD one into it, not the reverse — that
orientation makes additions appear as insertions.

### 4. Run it, and expect flakiness

```bash
soffice -env:UserInstallation=file://$PROF --headless --norestore \
  "vnd.sun.star.script:Standard.Module1.DoCompare?language=Basic&location=application"
```

Then poll for the output file. **This step is unreliable** — in the vcf2hash run
it produced nothing on two of four attempts and once hung past eight minutes.

- `pkill -f soffice`, wait a few seconds, retry.
- **Keep the extracted working tree from any successful run.** A later re-run may
  fail, and the salvaged tree lets you finish the post-processing without
  comparing again.
- Cap the wait. Do not let a hung `soffice` consume the turn.

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

Repackage with `[Content_Types].xml` written first.

### 6. Validate — all of these, every time

| Check | How |
|---|---|
| XML well-formed | `lxml.etree.fromstring(document.xml)` |
| Zip intact | `zipfile.ZipFile(f).testzip() is None` |
| Opens as a document | `docx.Document(f)` — report paragraph and table counts |
| Real revision marks | count `w:ins` / `w:del` — must be non-zero |
| Every mark attributed | no `w:ins`/`w:del` without `w:author` |
| Images preserved | `word/media/` count matches the clean export |
| No empty tables | every `w:tbl` has text or graphics |

Report the insertion / deletion counts to the user. The ratio is informative:
insertions far exceeding deletions means the revision mostly *added* material,
which is worth stating in the response letter.

### 7. Upload

`export_to_path` does not touch this file — it was built locally. Attach it
explicitly, or it will not appear on the dashboard:

```
mcp__co_scientist__attach_export(slug, local_path=..., scope="main")
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

- LibreOffice (`soffice`) on PATH
- Python with `lxml` and `python-docx`

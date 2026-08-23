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
4. **Never pick the baseline yourself — ask, and wait for an answer.** Every
   validation check in this skill is blind to which OLD file you chose, so a wrong
   baseline ships a file that passes all seven checks and diffs against a document
   the reviewers never saw. See step 1; this is a gate, not advice.

## Flow

### 1. Locate the two documents

- **OLD** — the version the reviewers actually received. Check
  `mcp__co_scientist__list_exports(slug)`; submitted files are usually archived
  under `exports/.<label>/`. If the previous submission was never exported to
  `.docx`, say so and stop — there is nothing to compare against.
- **NEW** — the current clean export from `/paper-export`.

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

### 2. Prepare an isolated LibreOffice profile

Use a scratch profile so the user's own LibreOffice settings are untouched.

```bash
PROF=/tmp/lo_profile
rm -rf $PROF && mkdir -p $PROF
soffice -env:UserInstallation=file://$PROF --headless --terminate_after_init
```

### 3. Install the compare macro

**Order matters, and getting it wrong fails silently.** Initialising a fresh
profile makes LibreOffice write its OWN `Standard/Module1.xba` containing an empty
`Sub Main`. If you write the macro *before* step 2, init overwrites it,
`DoCompare` no longer exists, and soffice exits instantly having done nothing — no
output file, no error, exit code 0. That is indistinguishable from the flakiness
below, so the documented remedy (fresh profile + retry) reproduces the bug: three
cycles of up to 20 minutes were lost to exactly this. Always **init first, then
write the module, then `grep -c DoCompare` the file** to confirm it survived.
Run that same `grep` again at DIAGNOSIS time (step 4): an empty stage log has two
possible causes and this is the check that separates them.

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

### 4. Run it, then DIAGNOSE — do not just retry

```bash
soffice -env:UserInstallation=file://$PROF --headless --norestore \
  "vnd.sun.star.script:Standard.Module1.DoCompare?language=Basic&location=application"
```

Have the macro append a stage marker to a log file at each step — `start`,
`loaded-new`, `compared`, `stored`, `done` — and poll THAT log, not just the
output file. All three failure modes look identical ("no output file"), so
without the stage log plus one look at CPU you cannot tell which remedy applies —
and one of them is made WORSE by retrying:

Two of the modes below stop at the SAME stage (`loaded-new`). What separates them
is whether the process still **exists** — check that before anything else, because
one of them cannot be fixed by retrying and the other is fixed by nothing else:

| symptom | evidence | cause | remedy |
|---|---|---|---|
| exits immediately | no stage log at all | macro overwritten by profile init (step 3) — **or the process was killed before it wrote `start`**; the two are byte-identical from outside | `grep -c DoCompare` the EXISTING `Module1.xba` **first** — see below |
| never returns, **process ALIVE**, sustained 0% CPU, stderr quiet | stages stop at `loaded-new` | **stale `.~lock.<input>#` beside an input document** | delete the lock files (below) — retrying NEVER clears it |
| never returns, **process GONE** | stages stop at `loaded-new`, `Abort trap: 6` / `Fatal exception: Signal 6` in stderr | crash in LibreOffice's headless child-window path | retry — succeeds within 2 attempts. Fires on roughly HALF of runs, so budget for it |

`ps -p <pid>` (or `pgrep -f soffice`) once, at the moment you notice no output, is
the whole diagnosis. Reading only "no output file + 0% CPU" makes a crash and a
lock-hang look like one phenomenon — that mistake produced two wrong reports and
a since-retracted claim about images (below).

The crash stack is worth recognising; it is LibreOffice trying to open the Manage
Changes panel under `--headless`:

```
SalAbort → Application::Abort → Desktop::Exception
  → SfxWorkWindow::ShowChildWindow_Impl → SwView::Execute
  → SfxDispatcher::Execute → DispatchHelper::executeDispatch
```

**An empty stage log does not prove the macro is missing.** `Mark("start")` is the
first statement in `DoCompare`, but process startup, profile load and Basic
resolution all happen before it — a kill inside that one-to-two-second window
leaves zero markers, which looks exactly like the macro never existing. So
discriminate before you act:

```bash
grep -c DoCompare "$PROF/user/basic/Standard/Module1.xba"   # 1 = macro intact
```

If it returns 1, **do not rebuild the profile** — the macro was never lost and
something killed the run. Rebuilding on this evidence has already cost one
session a full profile reconstruction on a profile that was fine (and the rebuilt
profile then failed where the original succeeded).

**Never put `pkill` inside a retry loop.** `soffice` detaches and returns
immediately, so the loop reaches `pkill` while the compare it just launched is
still starting — the kill lands in the pre-`start` window, the stage log comes
back empty, and the next iteration does it again. A loop shaped like this cannot
succeed, and it manufactures the "macro missing" signature every time:

```bash
for i in 1 2 3; do                 # ✗ DO NOT
  soffice … DoCompare
  [ -f OUT ] && break
  pkill -f soffice; sleep 5        # kills the run this loop just started
done
```

**Retrying is right — the ordering is what was wrong.** Because the crash fires on
about half of runs, plan for 2–3 attempts. Clean at the TOP of each iteration,
never after launching, and read the stage log between attempts:

```bash
for i in 1 2 3; do
  pkill -9 -f soffice; sleep 5                  # clean FIRST…
  find "$(dirname "$NEW")" "$(dirname "$OLD")" -maxdepth 1 -name '.~lock.*#' -delete
  rm -f "$OUT" "$STAGELOG"                      # …and prove the output is absent
  soffice … DoCompare
  # poll $STAGELOG until `done`, or until the process is gone / stalls at loaded-new
  [ -s "$OUT" ] && break
  cat "$STAGELOG"; pgrep -f soffice             # which mode was it? (table above)
done
```

**When a pair hangs, re-run a pair you know worked.** If the known-good pair hangs
too, the fault is environmental (a lock, a leftover process) and not the documents
— stop investigating the documents. This one step would have prevented both wrong
reports behind the retraction above: the control pair from the previous day hung
as well, which ruled out the documents immediately.

**zsh footgun: never write `rm -f .~lock.*#`.** With no match, zsh's `nomatch`
aborts the WHOLE command line, so anything sharing that line silently does not
run. In one session that left the previous attempt's output file in place, and the
next poll read it as a fresh success — caught only because the byte size matched
the earlier run. Use `find … -delete` (above), and confirm `$OUT` is gone before
launching rather than assuming the cleanup fired.

**Before any launch or relaunch, clear the process table AND every lock.** This is
the precondition that actually matters, and the input-side lock is the one people
miss — `pkill` does not remove it and neither does profile cleanup:

```bash
pkill -9 -f soffice; sleep 5
ps -eo comm | grep -ci soffice                   # must be 0 before launching
rm -f "$PROF/.lock" "$PROF/user/.lock"
# THE ONE THAT MATTERS — LibreOffice writes this next to the document itself:
find "$(dirname "$NEW")" "$(dirname "$OLD")" -maxdepth 1 -name '.~lock.*#' -delete
ls -l "$OUT" 2>/dev/null && echo "STALE OUTPUT — delete it or you will read it as success"
```

**Why the input-side lock is the whole ballgame.** Every killed `soffice` leaves a
`.~lock.<filename>#` next to the file it had open, and a stale one deadlocks the
next compare of that file: alive, 0% CPU, silent. So **the second run of any pair
inherits the first run's lock** — which is precisely the shape of an investigation
where you time out and retry. The failure appears to become deterministic exactly
because you are retrying.

Better than remembering to clean: **copy both inputs to fresh names for each
attempt.** A new filename cannot have a stale lock, so the failure mode becomes
structurally impossible instead of something to police.

> **Retracted: "embedded images deadlock the compare."** Earlier versions of this
> skill said figure-bearing documents deadlock deterministically and told you to
> strip images by default. That was wrong, and the mechanism above is why the
> evidence looked so strong: stripped copies were always written to NEW filenames,
> so they never carried a lock, while the originals were retried under their own
> names and inherited one every time. Images were perfectly confounded with
> "fresh filename". A later retest of the same pair that had "hung 4/4" — after
> clearing `.~lock` files — crashed once and then succeeded in 38 s with all 7
> figures intact, and the revision-mark counts came out identical to the stripped
> build (`w:ins` 522 / `w:del` 240 either way). Stripping cost the figures and
> bought nothing. Recorded here so the hypothesis is not rediscovered.

**Keep the figures.** Compare the real documents; the marked-up copy a reviewer
reads should have its figures in place. `strip_images()` below is a FALLBACK, not
the default — reach for it only if a pair still fails after locks are cleared and
2–3 attempts, and if you do use it, strip COPIES, never the originals.

```python
import zipfile
import lxml.etree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/package/2006/relationships}"

def strip_images(src, dst):
    """Copy `src` docx to `dst` with all images removed. Returns dst.

    Deletes w:drawing / w:pict, drops word/media/*, and removes the image
    RELATIONSHIPS too — leaving a dangling r:embed is what makes Word complain
    about a corrupt file."""
    with zipfile.ZipFile(src) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    out = []
    for info, data in items:
        name = info.filename
        if name.startswith("word/media/"):
            continue                                    # drop the bytes
        if name.endswith(".xml") or name.endswith(".rels"):
            try:
                root = ET.fromstring(data)
            except ET.XMLSyntaxError:
                out.append((info, data)); continue
            if name.endswith(".rels"):                  # drop image relationships
                for rel in list(root):
                    if str(rel.get("Type", "")).endswith("/image"):
                        root.remove(rel)
            else:                                        # drop the picture nodes
                for tag in (W + "drawing", W + "pict"):
                    for el in list(root.iter(tag)):
                        if el.getparent() is not None:
                            el.getparent().remove(el)
            data = ET.tostring(root, xml_declaration=True,
                               encoding="UTF-8", standalone=True)
        out.append((info, data))
    # [Content_Types].xml must be written first.
    out.sort(key=lambda kv: kv[0].filename != "[Content_Types].xml")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in out:
            zout.writestr(info, data)
    return dst
```

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

## Stamp the author — every mark says "Unknown Author" until you do

`.uno:CompareDocuments` writes `w:author` from the LibreOffice profile's user
name, and the isolated profile this skill mandates has **none**. So the isolation
that keeps the user's settings untouched is exactly what produces the defect: it
fires on EVERY run, not intermittently. One resubmission shipped 848 marks all
attributed to `Unknown Author`, in Word's review pane and Google Docs' suggestion
list alike, and passed every check below.

Do it in the same `lxml` pass as the table work, before repackaging. Post-processing
beats configuring the profile: the config surface can fail silently and leaves you
with nothing to verify, while this is deterministic and the check below proves it
took effect.

```python
def set_author(root, author: str) -> int:
    """Rewrite every w:author in this part. Covers w:ins / w:del AND the
    *PrChange elements (rPrChange, pPrChange, tblPrChange…), which carry their
    own author attribute and are easy to miss."""
    n = 0
    for el in root.iter():
        if el.get(W + "author") not in (None, author):
            el.set(W + "author", author)
            n += 1
    return n
```

Run it over **every part that can carry revisions** — `word/document.xml` plus any
`word/header*.xml` / `word/footer*.xml`. A header change otherwise keeps the
placeholder while the body looks fixed, and the check would then catch you.

The name comes from the PAPER, never a hardcoded string:

```python
authors = paper.get("authors") or []
author = next((a["name"] for a in authors if a.get("corresponding")),
              authors[0]["name"] if authors else "Authors")
```

Corresponding author first, then the first author, then the literal `"Authors"`.
What must never appear is `Unknown Author` — that is the failure, not a fallback.

**The `date` attribute is the compare-run time, and that is correct.** Every mark
carries the moment the diff was generated, not when the edit was made; a
two-document compare cannot know the latter. Do not try to "fix" it — a reviewer
seeing 848 changes at one timestamp is seeing the truth about how the file was
built.

Repackage with `[Content_Types].xml` written first.

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

# The LibreOffice compare — the fallback

_Part of `/tracked-changes-export`. Read from `SKILL.md` when `build_tracked_changes` cannot do the job: the revision is mostly formatting-only changes or moved text, or its result reads wrong._

### 2. Prepare an isolated LibreOffice profile — the fallback

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
a false claim that images deadlock the compare.

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
— stop investigating the documents.

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

Images do not deadlock the compare: a stripped copy written to a new filename
simply carries no stale lock.

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

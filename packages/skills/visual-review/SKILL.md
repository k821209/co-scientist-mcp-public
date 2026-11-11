---
name: visual-review
description: Read a rendered artifact as its viewer — the whole set first, then each frame — and keep fixing until a full pass finds nothing. Use before calling any rendered thing done (a deck, a schematic, a study page, a video), or whenever you have pixels and need to know whether they are good.
---

# /visual-review

The reader step for anything that ends up as pixels, the way `/cold-read` is
the reader step for prose and `/reviewer-frame-check` is for a letter. The
author cannot see these faults from inside: the code that drew the slide is
the same code that believes the slide is fine.

**Trigger:** before you tell the user a rendered artifact is done, and after
any batch edit to one.

## The loop

1. **Look at the whole set first.** One sheet of every frame, not a good
   frame. See [Getting the pixels](#getting-the-pixels).
2. **Then zoom.** Re-render the frames the sheet flagged, one at a time, full
   size.
3. **Write the complaint and the fix, not a score.** "S3's headline is
   centered, killing the asymmetric tension a thesis slide needs" + "left-align
   at col=1 span=8". A number with no sentence attached fixes nothing.
4. **Fix, re-render, go back to 1.**
5. **Stop when a full pass finds nothing** — not when a budget runs out. "Three
   rounds" is a stopping rule that stops on tiredness; this one stops on the
   artifact. If a pass keeps finding the same fault, the generator is wrong,
   not the frame: change tactic (simpler blueprint, bespoke rewrite) rather
   than editing the output again.

Two rules that outrank the loop:

- **Never report a fix you have not re-rendered and looked at.** The edit that
  was supposed to move the label is the edit that moved it under the arrow.
- **Never score a render you could not see.** When the PNG did not come out
  (no LibreOffice, no PyMuPDF, no render host), say that to the user with the
  missing piece named, and do not substitute the warning lists for having
  looked. They catch what they catch.

## What only the whole set can show

This is why step 1 exists, and why it is first. Each of these is invisible in
a frame that is fine on its own:

- **One accent doing every job.** An accent that marks everything marks
  nothing. It should be on the thing that is changing, in that frame.
- **Drift.** Chrome that thins out after frame 8; a density cliff in the back
  half; type that creeps a size per section.
- **Two frames drawing the same thing differently.** Same entity, two shapes;
  same relation, two arrow styles.
- **No rhythm.** Every frame the same shape for twenty frames, or no two alike.

## Every frame, on its own

- **One focal point.** Is it obvious at a glance, or does the eye hunt?
- **Nothing clipped, nothing crowding an edge.** Text cut off, a box running
  past the canvas, a label hard against the margin.
- **Labels never cover what they name**, and never sit where a reader will
  mistake which thing they belong to.
- **It reads at the size it will be seen** — projected across a room, or on a
  phone. Not at the size you are reading the PNG.
- **It says what it claims.** Arrows point the way the mechanism goes; the
  numbers on the frame match the data behind it.

## Getting the pixels

| Surface | The whole set | One frame | That surface's own checks |
|---|---|---|---|
| Deck slides | `preview_deck_sheet` (tiles every slide; `current: false` means refresh first) | `preview_slide`, or `export_deck_to_pptx` once at the end | `/paper-deck` — rubric, automatic-FAIL warnings, density + chrome |
| Schematic / diagram | the figure's own PNG | `generate_image` output | `/scientific-image` — weighted checklist in its `templates/` |
| Study page | the published page in a browser | — | `/study-design` |
| Video | `vh.qc` contact sheet (output and source) | a still at a timecode | `/video-harness` |

Read the image with the `Read` tool — you are multimodal, and the only
evidence that counts here is the render itself.

## Traps already hit

Record one here when a render lies about its own state, with the symptom that
identifies it — these are the ones that cost a session each.

- **A stale sheet read as current.** Tiles come from the last render, so a
  slide edited since shows its old PNG. `preview_deck_sheet` captions those
  STALE and sets `current: false`; a sheet read past that warning scores a
  deck nobody is looking at.
- **A de-tagged export faking the symptom.** Reading a rendered artifact
  through a converter can drop the very element under investigation. Read the
  shipped file.
- **A missing font substituted silently.** LibreOffice swaps an uninstalled
  face without saying so, so the PDF/PNG diverges from what PowerPoint will
  show — "the PPT looks right but the export is misaligned".

---
name: study-design
description: Design a Study document — the explainer that reads inline in the dashboard's Study tab — on top of its base stylesheet, check the rendered page, and keep a standalone copy from drifting. Use before write_study, when a study reads as an unstyled wall of text, or "스터디로 정리해줘".
---

# /study-design

**Triggers:** "write this up as a study," "make a study document," "스터디로
정리해줘," "이 스터디 읽기 힘들다," "설명 문서 하나 만들자."

Read this **before `write_study`**. Four studies shipped as bare semantic HTML
in one project before anyone opened the tab and found a wall of undifferentiated
text with borderless tables. Nothing in the tool said what the surface does, so
the agent guessed, and guessing wrong is invisible from this side.

## What the surface actually is

The document is rendered in a **sandboxed iframe of its own** (`srcDoc`, no
`allow-same-origin`). `write_study`'s description states what follows from that
— the layered base sheet, `asset:` images, links in a new tab, scripts off. What
it does not:

- **CSS scope.** The document owns its page. `:root`, `body` and bare element
  selectors are yours and leak nowhere — it is a separate document, not an
  injection into the dashboard.
- **Motion is CSS.** `@keyframes` and `transition` run without scripts; the base
  sheet turns them off under `prefers-reduced-motion` — do not re-enable it.
- **Editing.** `update_study(study_id, html=…)` amends in place and re-stamps
  `sources`. `write_study(study_id=…)` replaces the whole record (every field)
  and does not re-stamp. Never write-new-then-delete.

**Compose with the base; do not rebuild it.** The base publishes its colours as
tokens — `--scivo-ground`, `--scivo-surface`, `--scivo-ink`, `--scivo-muted`,
`--scivo-rule`, `--scivo-accent` — that already follow the reader's theme. A
card is `background: var(--scivo-surface); border: 1px solid var(--scivo-rule)`
and it is right in both modes with no media query. Set your own colour only
where the document needs a colour the base does not have, and then give both
themes. (Before 2026-09-11 the first `<style>` block switched the base off
entirely; a partial sheet then left everything else unstyled. That is gone —
a `<style>` block with one rule is now the normal case, not a trap.)

## Which of the two to write

**Bare semantic HTML — the default.** `<h2>`, `<p>`, `<table>`, `<blockquote>`,
`<code>`. The tab makes it readable, every study in every project looks
consistent, and you spend your attention on the argument. Choose this unless
you have a reason not to.

**A designed page.** Worth it when the document's structure IS the content — a
comparison that wants a real table layout, a stepwise argument that wants
numbered cards, a result that wants one figure given room. Style that
structure, on top of the base:

- **Use the tokens for colour.** They follow the reader's theme; a colour of
  your own must be given for both — the frame sets `data-scivo-theme` on
  `<html>` (`light`/`dark`) and `color-scheme`, so both `[data-scivo-theme="dark"]`
  and `@media (prefers-color-scheme: dark)` resolve correctly.
- **Keep the measure.** The base sets ~46rem on `body`, centred; one element
  that needs the full width breaks out with `margin-inline: calc(50% - 50vw)`
  rather than widening the page.
- **Wide content scrolls inside itself.** A table or a code block in its own
  `overflow-x: auto` container; the page must never scroll sideways. The base
  gets this by setting `display: block` on `table`, which has one consequence
  worth knowing when you combine it with the line above: a table is then a
  block box, so inside a full-bleed wrapper it fills the frame and its rows sit
  at the far left. The base now also sets `width: fit-content`, which is what
  makes `figure.wide table { margin-inline: auto }` centre anything at all — if
  you override `width` on a table, you take that back.
- **Preformatted text needs `white-space: pre`.** A monospace box with a
  background looks like a code block and collapses every newline and every run
  of spaces without it — a ten-row histogram rendered as one line, and the
  AUTHOR was the detector (feedback de487cc198d4). `preview_study` checks for
  this now; do not rely on it noticing.
- **An inline element ignores `width` and `height`.** A `<span>` with
  `width: 25%` and no `display` renders at zero size, which is how a bar chart
  came out with no bars. `display: inline-block` first.
- **Fonts are handled.** The base stack covers Korean and Latin without a
  request; font CDNs do not load here, so do not reference one.
- **One accent colour** (`--scivo-accent`), used for the thing the reader
  should find first. A study is an argument, not a dashboard; every additional
  colour is a claim that something else matters equally.
- **Motion, if any, is CSS and is small.** A reveal or a highlight; nothing
  the argument depends on, because the base disables it for readers who asked
  for no motion.

## What makes it a STUDY and not just a page

`sources`, `summary` and `follows` are in `project_guide(topic="study")` and
`write_study`'s description. The rule this skill adds: record a source for
**every measured value in the document** — a study full of numbers and no
sources will quietly go stale and be quoted anyway.

## Also publishing a standalone copy

A study lives next to the paper and carries sources and staleness. A
standalone copy has its own URL and can be shared outside the project. **The
host-independent way is Scivo's own `publish_page(title, html=…)`** — an
unlisted URL that works the same from Claude Code, Codex and Pi, and needs no
host feature. A host's own page tool (Claude Code's Artifact, say) is an
alternative when the user asks for it; nothing here depends on one. Publishing
is outward-facing: the guide's rule applies — only after the user says so.

When both are wanted, **build both from one source** — but they are not the
same file:

- **Images.** A standalone page does not get `asset:` resolution (and an
  external host may block outside images altogether), so figures must be
  inlined as base64 there. In a study that is pure waste: use `asset:` and let
  the tab resolve it. The same page was 95 KB inlined and 25 KB by reference.
- **Links.** Both need `target="_blank"`.

**Record the copy with `mark_study_published(study_id, url)`** right after
publishing and after every republish (its description says what that buys).
When a rewrite warns that the copy is behind, republish and re-record, or
forget the copy. Also put the copy's URL in the study as an ordinary anchor so
a reader can open it.

## Before you call it done

1. **Read it back** — `read_study(study_id)`. The one failure this catches is
   double-escaped HTML: `&lt;h2&gt;` renders as visible tags. `write_study`
   now refuses the obvious case, but a document that mixes real markup with
   escaped entities gets through.
2. **Check every number has a source** in `sources`.
3. **Look at it: `preview_study(study_id, theme="both")`, then Read the
   PNGs** — its description says what to look for and what to do with no
   browser; do not report the page as checked without the look. The loop around
   that look is `/visual-review`: fix, re-render, look again, and stop when a
   full pass finds nothing — a fix you have not re-rendered and looked at is not
   a fix.

## Questions on it, after it ships

Questions vs comments, `changed_study`, and asking your own with
`ask_study_question` are in `project_guide(topic="study")`. Specific to this
surface: a question may be **about the whole document** (`quote` is null).

The reader picks a paragraph and its text arrives as `quote`. Match on the
quote first; `block_index` is where that paragraph sat when they asked, and the
document may have moved since.

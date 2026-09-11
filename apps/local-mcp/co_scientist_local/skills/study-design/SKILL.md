---
name: study-design
description: Design a Study document — the explainer that reads inline in the dashboard's Study tab. Covers what the surface actually does (sandboxed frame, layered base stylesheet and its tokens, asset: images, links open in a new tab), how to design one on top of the base, how to see the rendered page before calling it done, and how to keep a standalone copy (a `publish_page` URL, or any host's page) from drifting. Use before write_study, or when a study reads as an unstyled wall of text.
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
`allow-same-origin`). Everything below follows from that, and none of it is
guessable:

| | |
|---|---|
| **Styling** | The dashboard's CSS does NOT reach the document. The tab injects a base sheet into every document — measure, type scale, ruled tables, tabular numerals, a Latin+Korean font stack, both colour themes — as a cascade layer (`@layer scivo-base`). Your own `<style>` block sits above the layer and **adds to it**: style the one element that needs it and the rest stays typeset. |
| **Images** | `<img src="asset:FILENAME">`, where FILENAME is what `add_asset` stored. The tab resolves it to a download URL before rendering. |
| **Links** | Work, and open a NEW TAB. Write `<a href="…" target="_blank" rel="noopener">`. The frame is not allowed to navigate the dashboard away. |
| **Scripts** | Off unless the reader turns them on. The document must be readable without them. Motion is CSS: `@keyframes` and `transition` run without scripts, and the base sheet turns them off under `prefers-reduced-motion` — do not re-enable it. |
| **CSS scope** | The document owns its page. `:root`, `body` and bare element selectors are yours and leak nowhere — it is a separate document, not an injection into the dashboard. |
| **Editing** | `update_study(study_id, html=…)` amends in place, and passing `html` **re-stamps `sources` as read-now** — rewriting the tables is what makes them current. `write_study(study_id=…)` replaces the whole record (every field) and does not re-stamp. Never write-new-then-delete: it breaks any `follows` chain and changes the URL. |

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
  `overflow-x: auto` container; the page must never scroll sideways.
- **Fonts are handled.** The base stack covers Korean and Latin without a
  request; font CDNs do not load here, so do not reference one.
- **One accent colour** (`--scivo-accent`), used for the thing the reader
  should find first. A study is an argument, not a dashboard; every additional
  colour is a claim that something else matters equally.
- **Motion, if any, is CSS and is small.** A reveal or a highlight; nothing
  the argument depends on, because the base disables it for readers who asked
  for no motion.

## What makes it a STUDY and not just a page

`sources` is the reason this surface exists rather than a document in Materials:

```
sources=[{"kind": "analysis", "ref": "mlm-eval", "label": "bits/bp"}]
```

Record one for **every measured value in the document**. It stamps "read now",
and when that analysis is next updated the study shows as out of date on its own
— nobody has to remember. A study full of numbers and no sources is a document
that will quietly go stale and be quoted anyway.

`summary` is for the reader, in the list: what this explains. Your caveats and
reasoning go in a material's `ai_note`, not here.

`follows` chains a series into reading order.

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

**Record the copy: `mark_study_published(study_id, url)` right after
publishing, and again after every republish.** The study's staleness tracking
stops at the study's own edge; this is the one step past it. From then on a
rewrite of the study warns in its return value that the copy is behind, and
`list_studies` / the tab show `published_behind` — so the standalone copy
cannot sit behind a link that reads as current after the study moved on. When
that warning comes back, republish and re-record, or forget the copy with
`url=None`. Also put the copy's URL in the study as an ordinary anchor so a
reader can open it.

## Before you call it done

1. **Read it back** — `read_study(study_id)`. The one failure this catches is
   double-escaped HTML: `&lt;h2&gt;` renders as visible tags. `write_study`
   now refuses the obvious case, but a document that mixes real markup with
   escaped entities gets through.
2. **Check every number has a source** in `sources`.
3. **Look at it: `preview_study(study_id, theme="both")`, then Read the
   PNGs.** It renders the html the way the tab does — same base sheet, same
   theme attribute, `asset:` images inlined — in a headless browser on this
   machine. What you are looking for: a wall of unstyled text, a table without
   rules, sideways scroll, a missing image, a dark theme that did not follow.
   If it reports no browser, ask the user to look at the tab and do not report
   the page as checked — the whole reason this file exists is that four studies
   were filed before anyone looked.

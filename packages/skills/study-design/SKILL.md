---
name: study-design
description: Design a Study document — the explainer that reads inline in the dashboard's Study tab. Covers what the surface actually does (sandboxed frame, default stylesheet, asset: images, links open in a new tab), how to design one deliberately, and when the same document should also be a standalone Artifact. Use before write_study, or when a study reads as an unstyled wall of text.
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
| **Styling** | The dashboard's CSS does NOT reach the document. The tab injects a readable default — measure, type scale, ruled tables, tabular numerals, the reader's light/dark theme — but **only when the document has no `<style>` block or stylesheet link of its own.** |
| **Images** | `<img src="asset:FILENAME">`, where FILENAME is what `add_asset` stored. The tab resolves it to a download URL before rendering. |
| **Links** | Work, and open a NEW TAB. Write `<a href="…" target="_blank" rel="noopener">`. The frame is not allowed to navigate the dashboard away. |
| **Scripts** | Off unless the reader turns them on. The document must be readable without them. |
| **CSS scope** | The document owns its page. `:root`, `body` and bare element selectors are yours and leak nowhere — it is a separate document, not an injection into the dashboard. |
| **Editing** | `write_study(study_id=…)` replaces in place. Without the id you get a new document, and deleting the old one breaks any `follows` chain and changes the URL. |

**The styling switch is all-or-nothing.** Adding a `<style>` block turns the
default off entirely, so a partial stylesheet leaves everything you did not
cover unstyled — worse than either extreme. Bring one only when you are
designing the whole page.

## Which of the two to write

**Bare semantic HTML — the default.** `<h2>`, `<p>`, `<table>`, `<blockquote>`,
`<code>`. The tab makes it readable, every study in every project looks
consistent, and you spend your attention on the argument. Choose this unless
you have a reason not to.

**A designed page.** Worth it when the document's structure IS the content — a
comparison that wants a real table layout, a stepwise argument that wants
numbered cards, a result that wants one figure given room. Then take the whole
page:

- **Define colours as tokens on `:root`, and give BOTH themes.** The frame
  carries the reader's setting; a page that only works in light mode is a white
  slab in a dark dashboard. Use `@media (prefers-color-scheme: dark)` — the
  default sheet sets `color-scheme`, so this resolves correctly.
- **Set a measure.** Long-form text running the width of a monitor is the most
  common way a designed page reads worse than the default one. ~46rem.
- **Wide content scrolls inside itself.** A table or a code block in its own
  `overflow-x: auto` container; the page must never scroll sideways.
- **System font stack.** Font CDNs do not load here. `ui-sans-serif, system-ui,
  "Noto Sans KR", sans-serif` covers Korean and Latin without a request.
- **One accent colour**, used for the thing the reader should find first. A
  study is an argument, not a dashboard; every additional colour is a claim
  that something else matters equally.

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

## Also publishing it as an Artifact

A study lives next to the paper and carries sources and staleness. An Artifact
is standalone, has its own URL and can be shared outside the project. When both
are wanted, **build both from one source** — but they are not the same file:

- **Images.** An Artifact's CSP blocks external hosts, so figures must be
  inlined as base64 there. In a study that is pure waste: use `asset:` and let
  the tab resolve it. The same page was 95 KB inlined and 25 KB by reference.
- **Links.** Both need `target="_blank"`.

Link the two: put the Artifact URL in the study as an ordinary anchor so a
reader can open the standalone copy.

## Before you call it done

1. **Read it back** — `read_study(study_id)`. The one failure this catches is
   double-escaped HTML: `&lt;h2&gt;` renders as visible tags. `write_study`
   now refuses the obvious case, but a document that mixes real markup with
   escaped entities gets through.
2. **Check every number has a source** in `sources`.
3. **Ask the user to look at the tab.** You cannot see the rendered page from
   here — the whole reason this file exists is that four studies were filed
   before anyone did.

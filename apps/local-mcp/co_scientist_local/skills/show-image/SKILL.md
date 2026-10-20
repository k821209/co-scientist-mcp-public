---
name: show-image
description: Put an image you produced in front of the user — a render, a screenshot, a plot — on whichever surface they are actually watching (terminal, the Scivo web chat, the dashboard). Use when the user says "show me," "보여줘," "띄워줘," right after generating or fetching an image, or when an image you referenced came out as a broken link or plain text.
---

# /show-image

**Triggers:** "show me the render," "보여줘," "이미지 띄워줘," and — without
being asked — immediately after you produce an image the user is waiting on.

## The one question this skill answers

An image you just wrote is a path on this machine. Which path works depends on
**where the user is looking**, and that is not something you can see, so ask
once if it is not obvious from the conversation:

| the user is on | what reaches them | what does not |
|---|---|---|
| this terminal | the path, written plainly | nothing needed — they open it |
| the Scivo **web chat** (control page) | `![alt](/abs/path.png)` — the harness inlines it | a path outside the allowed roots (below) |
| the **dashboard**, now or later, or another machine | `add_material(local_path=…)` → the Materials tab previews it and returns `dashboard_url` | a local path, always |
| someone with **no Scivo account** | `publish_page` with the image, or a shared paper figure | both of the above |

A broken image in a chat panel is almost always this: the right markdown aimed
at the wrong surface.

## The web chat path, and its one rule

The harness rewrites `![alt](path)` into a data URI before it publishes, so the
page shows the picture itself rather than a link the browser cannot fetch. Two
things to know, both of which you will otherwise hit:

- **Only under the project root, or a directory the session was started with
  (`--add-dir`).** The reference is text you wrote, and the rewrite uploads
  without asking anyone, so `![x](../../.ssh/id_rsa.png)` must not be able to
  ship a private key's screenshot to a web page. A render pipeline that writes
  to its own output directory needs that directory declared once, at launch —
  or write the file under the project instead, which is simpler.
- **500 KB per image after downscaling, 1.5 MB per message.** Over that, the
  reply carries a `[name: 2048 KB — not inlined for the web view]` note instead
  of the picture: loud, not silent. Re-render smaller, or register it (next
  section) and send the link.

## When it should outlive the message

`add_material` is the project's **curated** store of source files, and the
Materials tab is where the user looks for them. So:

- A result, a figure draft, a screenshot of something that matters later →
  `add_material(local_path=…, ai_note="what it is")`. Use
  `overwrite=True` when replacing a file you registered before, or you leave
  two rows and every reference points at the old one.
- A figure that belongs to a paper → `add_figure(slug, figure_number=…,
  local_path=…)` with its caption or legend, not a material. It then renders in
  the manuscript and travels into the export.
- **A throwaway preview → neither.** Inline it in the message. Twenty "look at
  this one" renders in the Materials tab is twenty rows the user has to tell
  apart later, and the tab stops being a place where anything can be found.

## Say which one you did

"Registered as a material — it is in the Materials tab" and "inlined above" are
different promises, and the user is looking at exactly one surface. One line,
with the link when there is one.

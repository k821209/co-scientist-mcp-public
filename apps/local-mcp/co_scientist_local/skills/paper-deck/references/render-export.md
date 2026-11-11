# Rendering and export

_Part of `/paper-deck`. Read from `SKILL.md` when every slide has its content and it is time to render, preview or export._

## Rendering + export (Phase 3 — shipped)

After every slide has its body / prompt / notes filled:

```
mcp__scivo__render_deck(slug, deck_id)
```

This walks every slide and:
- `text`         → nothing to render; it becomes native PPTX text at
                   export. Returned in `skipped[]` with that reason.
- `paper-figure` → copies the existing figure blob into a slide image
- `ai-image`     → substitutes `{accent}` etc. from `deck.concept`,
                   calls `generate_image`
- `hybrid`       → renders every region it can (`paper-figure` /
                   `ai-image` regions); `code-shape` regions land in
                   `skipped[]` for you to do via `render_region`.
- `code-shape`   → returned in `skipped[]` because the MCP can't safely
                   exec arbitrary Python. Run the slide's `code` block
                   yourself locally (matplotlib/seaborn/etc. into a
                   PNG), then pass that path back:

```
mcp__scivo__render_slide(
  slug, deck_id, slide_id,
  local_path="/abs/path/to/slide-3.png",
)
```

For a **hybrid** slide's `code-shape` region, render that one region:

```
mcp__scivo__render_region(
  slug, deck_id, slide_id, region_id,   # e.g. region_id="r2"
  local_path="/abs/path/to/region.png",
)
```

`paper-figure` / `ai-image` regions need no `local_path` — the MCP
renders them (an ai-image region's aspect ratio is matched to its
box). A hybrid slide is "done" when every region has an image.

Once every non-`text` slide has an `image_blob_path`, the deck's
`status` flips to `"rendered"`. To export from Claude Code:

```
mcp__scivo__export_deck_to_pptx(
  slug, deck_id,
  output_path="~/decks/my-talk.pptx",
)
```

Export behavior:
- **Image slides** embed the rendered PNG, aspect-fitted and centered.
- **`hybrid` slides** get a themed title frame plus each region placed
  as its own separately-editable PPTX picture at its `x/y/w/h` box,
  with an optional caption.
- **`text` slides** (and any slide still missing a render) become
  NATIVE editable text — title + bullets — themed from the concept's
  `accent` / `bg` / `text` colors. Not a picture: the user can edit
  the words in PowerPoint.
- Page size follows the deck's `aspect_ratio`.
- The exported **`.pptx` opens in Keynote as well as PowerPoint /
  LibreOffice.** `export_deck_to_pptx` strips the stale
  `<p:sldSz type="screen4x3">` attribute python-pptx leaves after a
  16:9 resize, and registers `<p:notesMasterIdLst>` (python-pptx adds
  a notesMaster relationship for speaker notes but never registers it —
  a dangling relationship Keynote refuses). Do NOT tell the user the
  PPTX is Keynote-incompatible or steer them to the PDF for that
  reason; just hand them the `.pptx`.
- A sibling **`.pdf`** is produced when LibreOffice (`soffice`) is
  installed — a convenience for read-only sharing, NOT a Keynote
  workaround.

Returns `{ local_path, blob_path, pdf_local_path, pdf_blob_path,
pdf_skipped, aspect_ratio, slide_count, image_slides, text_slides,
hybrid_slides, missing_renders }`. `missing_renders[]` is the non-text slides that
came out as text fallbacks because they weren't rendered yet — render
those and re-export. **If `pdf_skipped` is true, read `render_missing` and
`pdf_skipped_reason` and tell the user exactly what to install** — each
entry names the piece and the command. Without a PNG the visual check of
this skill cannot run; `layout_warnings` is then the only verification, and
say so rather than reporting the deck as looked at.

python-pptx ships with the base install. LibreOffice (PDF, and every PNG
comes from it), PyMuPDF (PDF → PNG; a declared dependency, so its absence
means the install skipped dependencies) and a Korean font are the render
host's extras — `preview_slide` reports which are missing.

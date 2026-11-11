# Hybrid slides and regions

_Part of `/paper-deck`. Read from `SKILL.md` when a slide carries bullets beside a figure, several images, or an image the user uploaded from the dashboard._

### 5b. Hybrid slides — bullets + figure, or several images (regions)

Two distinct uses of `set_slide_regions` / hybrid:

**(a) Title + bullets + one figure** — the most common mixed slide.
Put the bullets in `body` (markdown) on `add_slide`, then set ONE
image region for the figure on the right:

```
mcp__scivo__set_slide_regions(
  slug, deck_id, slide_id,
  regions=[
    { "render_mode": "ai-image",
      "prompt": "{accent} schematic of 2-week pipeline vs 30-sec MCP query",
      "x": 0.54, "y": 0.22, "w": 0.42, "h": 0.65,
      "fit": "contain" },
  ],
)
```

The slide's `body` renders as native bullets in the LEFT half; the
image region renders in its box on the right. The bullets stay
editable text in the .pptx; only the figure is an image.

**Keep the body tight on hybrid slides.** The body box is half-width,
so each bullet wraps onto more lines than on a full-width `text`
slide. As a rule, aim for ≤ 4 bullets, each ≤ 2 wrapped lines (i.e.
~80 Korean characters / 120 English characters). Dense bullets will
overflow the box even at the reduced 20pt body type.

**(b) Several images on one slide** — a generated schematic next to a
data plot next to a manuscript figure:

```
mcp__scivo__set_slide_regions(
  slug, deck_id, slide_id,
  regions=[
    { "render_mode": "paper-figure", "figure_number": 2,
      "x": 0.05, "y": 0.22, "w": 0.42, "h": 0.62, "fit": "contain",
      "caption": "Fig 2 — measured response" },
    { "render_mode": "ai-image", "prompt": "{accent} pathway schematic …",
      "x": 0.52, "y": 0.22, "w": 0.43, "h": 0.62, "fit": "contain",
      "caption": "Proposed mechanism" },
  ],
)
```

- On a slide with no `code`, this makes it `render_mode="hybrid"`. A slide
  that is in `code` mode or already carries a snippet STAYS `code` — its
  regions are then the image placeholders the snippet places (see the
  image-placeholder workflow in `references/patterns.md`). Regions get ids
  `r1..rN` in order.
- `x/y/w/h` are **fractions of the slide** (0–1) — keep `y ≥ ~0.2` so
  regions clear the title. Useful layouts:
  - **2-up**: `r1` x=0.05 w=0.42, `r2` x=0.52 w=0.43 (both y=0.22 h=0.62)
  - **big-left + 2 stacked right**: `r1` x=0.05 y=0.22 w=0.55 h=0.62;
    `r2` x=0.64 y=0.22 w=0.31 h=0.29; `r3` x=0.64 y=0.55 w=0.31 h=0.29
  - **2×2**: four 0.42×0.34 boxes at x∈{0.05,0.52}, y∈{0.22,0.60}
- Each region has its own `render_mode` (`ai-image` / `code-shape` /
  `paper-figure`) and source. A region can't itself be `hybrid`/`text`.
- **`fit`** decides how the image fills its box:
  - `contain` (default) — letterbox, never crop. Use for figures,
    charts, tables, schematics — anything where cropping loses data.
  - `cover` — fill the box, crop the overflow. Use for an eyecatch /
    decorative / photo region where edge loss is fine.
- `render_region` records the rendered image's real pixel size
  (`image_width` / `image_height`) on the region — handy if you want
  to nudge a box to match the image's true aspect on a second pass.
- At export each region becomes a **separate, individually editable
  PPTX picture** — the user can nudge them in PowerPoint.

**(c) User-uploaded images (dashboard "Upload image").** From the
Presentations tab a user can upload an image (screenshot, photo) straight
onto a slide. This does NOT go through `add_figure` / materials / assets —
**it will NOT appear in `list_materials` or `list_assets`.** It lands on the
slide itself in one of two shapes:

- **Full-slide upload** → the slide gets `image_blob_path` set, `render_mode`
  `"code-shape"`, and `image_source: "upload"` (renders full-bleed).
- **Slot / positioned / auto upload** → the slide becomes `hybrid` with one
  region per uploaded image, `image_source: "upload"`. A slide can hold
  **several** uploads; ids are `"upload_1"`, `"upload_2"`, … (a legacy single
  upload may just be `"upload"`):
  ```
  {"id": "upload_1", "image_source": "upload", "render_mode": "code-shape",
   "image_blob_path": ".../slides/{slide_id}/regions/upload_1.png",
   "x":…, "y":…, "w":…, "h":…, "fit": "contain",
   "placement": "auto" | "manual",
   "note": "demo screenshot — put it big on the right"}  # user's hint to YOU
  ```

To find them: they're regions, so **`list_slides(slug, deck_id,
fields=["regions"])`** surfaces them — match on `image_source == "upload"`
(the id may be `upload`, `upload_1`, …). Don't tell the user an upload is
inaccessible just because materials/assets are empty.

Handling them:
- **`note`** is a free-text hint the user typed next to the image in the
  dashboard ("put this big on the right", "this is the result plot"). Read it
  and honor it — it tells you what the image is and how to place / merge it.
- **`placement == "auto"`** means the user deferred positioning to you: read
  the slide's title/body/whitespace and the note, then drop it into the frame
  that fits (e.g. the empty right half of a title+bullets slide) rather than
  leaving it in the default box. If a placeholder frame already occupies that
  spot, replace it. **`placement == "manual"`** = the user set the box; keep it.
- In a **code** slide, place each by id like any region:
  `h.image_region(slide, 'upload_1', left=…, top=…, width=…, height=…, fit='contain')`.
- Multiple uploads → lay them out together (e.g. a 2-up / grid) guided by
  each region's `note`.

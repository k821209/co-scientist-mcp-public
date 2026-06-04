---
name: paper-import
description: Import an existing manuscript (.docx, .pdf, .odt, .tex, .html, .md) into co-scientist as a new paper, splitting it into canonical sections so the user can keep writing here. Use when the user says "import this paper," "I already wrote this in Word," "bring in this PDF," "continue this manuscript here."
---

# /paper-import

**Triggers:** "import my paper," "I wrote this in Word — bring it in,"
"start from this PDF/docx," "load this manuscript," "continue this
draft in co-scientist."

## What it does

Takes a finished-or-draft manuscript file and turns it into a
co-scientist paper: converts the file to markdown, splits it into the
canonical sections, creates the paper, and registers any figures it
can recover. The user then keeps writing with the normal skills.

Division of labour:
- **MCP `import_document`** — deterministic conversion (file → markdown
  + extracted media). No interpretation.
- **You (the agent)** — the LLM judgment: figure out where each
  section begins/ends and map them to the canonical keys.

## Supported inputs

| Format | Path | Quality |
| ------ | ---- | ------- |
| `.docx` `.odt` `.rtf` | pandoc | Good — headings + embedded images preserved |
| `.html` `.tex` `.epub` `.md` | pandoc | Good |
| `.pdf` | pypdf text extraction | **Lossy** — PDF has no section structure; figures/tables NOT recovered. Prefer the original .docx if the user has it. |

## Flow

### 1. Get the file + confirm

Ask for the absolute path to the manuscript file and the title for the
new paper (default: derive from the filename or the document's first
heading).

If the user offers a PDF *and* mentions they have the Word original,
recommend the .docx — much better fidelity.

### 2. Convert

```
result = mcp__co_scientist__import_document(local_path="/abs/path/paper.docx")
```

Returns `{ source_format, markdown, media[], warnings[], char_count }`.

Surface every entry in `warnings[]` to the user (especially the PDF
lossy warning).

### 3. Split into canonical sections — YOUR job

Read `result.markdown`. The canonical section keys co-scientist seeds
for a new paper are:

    abstract · introduction · methods · results · discussion · conclusion

Identify each section's boundaries in the imported markdown. Real
manuscripts vary — headings may be "1. Introduction", "MATERIALS AND
METHODS", "Results and Discussion" (a merged section), "Conclusions",
etc. Map intelligently:

- "Materials and Methods" / "Experimental" → `methods`
- "Results and Discussion" merged → put the bulk in `results`, or
  split if clearly separable; tell the user what you did
- "Background" → `introduction`
- Front-matter (authors, affiliations) → NOT a section; capture
  authors for `create_paper`, drop affiliations or note them
- References / Bibliography → NOT a section; handle in step 6

If the manuscript has sections that don't map (e.g. "Acknowledgements",
"Author Contributions"), ask the user whether to drop them or append
them to the nearest section.

### 4. Create the paper

```
mcp__co_scientist__create_paper(
  title="...",
  authors=[...],          # parsed from the front matter if present
  journal="...",          # if the document names a target journal
  abstract="...",         # the abstract text, if found
)
```

`create_paper` seeds the six canonical empty sections.

### 5. Populate the sections

For each canonical section, write the imported text:

```
mcp__co_scientist__update_section(
  slug, key="introduction", body="<imported markdown for that section>",
  status="draft",
)
```

Preserve the author's prose verbatim — this is an import, not a
rewrite. Clean up only conversion artifacts (stray pandoc escapes,
broken list markers). Inline `{doi:…}` markers: if the source had
real citations, see step 6.

### 6. References

The imported bibliography is plain text — co-scientist wants
structured references. For each entry that has a DOI:

```
mcp__co_scientist__add_reference_by_doi(slug, doi="10.…")
```

For entries without a DOI in the text, try `search_works` with the
title to find the DOI, confirm the match with the user, then
`add_reference_by_doi`. Don't fabricate DOIs.

Then, where the body cited that work, insert an inline `{doi:…}`
marker so the citation pipeline picks it up. (Imported manuscripts
usually have "[1]" / "(Author, 2024)" style cites — converting those
to `{doi:…}` is a judgment call; do the ones you can confidently map
and tell the user which you couldn't.)

### 7. Figures (docx only)

`result.media[]` lists images pandoc extracted from the docx. For each
that's a real paper figure (skip logos, equation images):

```
mcp__co_scientist__add_figure(
  slug, figure_number=N,
  title="...", caption="...",
  local_path="<path from result.media>",
)
```

Match them to the manuscript's "Figure N" references by reading the
order they appear in the markdown. Ask the user if uncertain.

For PDF imports there are no extracted figures — tell the user they'll
need to re-add figures via `add_figure` or `/scientific-image`.

### 8. Report

Tell the user:
- N sections populated (and any merge/split decisions you made)
- N references registered (and which couldn't be resolved)
- N figures imported (or "none — PDF import")
- Anything that needs their attention

Then suggest next steps: `/paper-review` to sanity-check the import,
`/literature-review` to fill citation gaps, normal `/paper-writing`
to continue.

## Rules

- **Preserve the author's text.** Import ≠ rewrite. Fix only
  conversion artifacts.
- **Never fabricate DOIs.** Resolve via `search_works` +
  `add_reference_by_doi`, or leave the citation as plain text and
  flag it.
- **Surface every `warnings[]` entry** — especially the PDF lossy
  warning, so the user knows figures/tables didn't come across.
- **Tell the user every judgment call** — merged sections you split,
  citations you couldn't map, images you skipped.

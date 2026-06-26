---
name: paper-export
description: Export a paper to .docx / .tex / .pdf / .md via Pandoc. Use when the user says "export," "download as Word/PDF/LaTeX," "send to journal," or any phrasing that asks for a finished document file.
---

# /paper-export

**Triggers:** "export to docx," "give me a PDF," "download as LaTeX,"
"submit-ready file," "save the paper," "convert to Word."

## What this skill does (high level)

Calls the MCP's `prepare_export` to gather everything Pandoc needs
(assembled manuscript, BibTeX from registered references, figures /
tables / supplementary, placeholders + unresolved DOI warnings), then
`export_to_path` to actually run Pandoc and upload the resulting file
to Cloud Storage under `papers/{slug}/exports/`.

No re-implementation of the export pipeline in the skill — the MCP
tools encapsulate the whole flow. The skill's job is to ASK what
format/path, surface warnings, and call the right tool.

## Flow

### 1. Resolve the target paper

- If the user already named a slug, use it.
- Otherwise call `mcp__co_scientist__list_papers()` and ask which one.

### 2. Run `prepare_export(slug)` — pre-flight check

The tool returns a bundle with a `warnings` array plus dedicated lists:

- `placeholders[]` — TBD / TK / XXX / TODO / FIXME / `[...]` markers
- `unresolved_citations[]` — `{doi:…}` references not in `references/`
- `warnings[]` — short human-readable summary
- `csl_filename` / `csl_slug` / `csl_source` / `csl_status` — the
  citation style resolved from `paper.journal` (see step 4). Resolved
  offline here; the file is downloaded at export time.
- `requirements_check` — the journal / paper-type submission check
  (word limits, figure & table caps, required sections). If
  `configured` is false, the paper has no journal spec yet — suggest
  `/journal-requirements`. If `violations[]` is non-empty, list each
  (e.g. "abstract 178/150 words") and ask whether to fix before
  exporting — a submission system will bounce an over-limit manuscript.

If any of these are non-empty, **surface them to the user and ask
whether to proceed**:

> "Found 3 placeholders and 2 unresolved DOIs. Continue with export
> anyway, or fix first?"

Recommended fixes BEFORE export:

- Placeholders → grep the section bodies for `TODO`/etc. and either
  resolve them or strip the markers.
- Unresolved DOIs → call `add_reference_by_doi(slug, doi)` for each
  missing DOI (CrossRef-backed; refuses fakes).
- Empty sections → ask the user whether they're intentionally blank.

If the user wants to proceed despite warnings, continue.

### 3. Decide format + output path

- Default format: **docx** (most common journal submission target).
- Other accepted formats: `tex`, `pdf`, `md`.
- Default path: `./{slug}.{ext}` in the current working directory
  unless the user supplied one.

### 4. Run `export_to_path`

```
mcp__co_scientist__export_to_path(
  slug,
  output_path="<absolute path or ./{slug}.{ext}>",
  fmt="docx" | "tex" | "pdf" | "md",
  scope="main",   # "main" | "supplementary" | "all"
)
```

**Main vs supplementary (`scope`).** A journal receives a main manuscript
containing only the MAIN figures/tables; supplementary items (figure/table
number ≥ 101) belong in a separate file. So:
- `scope="main"` (default) — manuscript text + main figures/tables only.
- `scope="supplementary"` — a standalone *Supplementary Material* document
  with only the supplementary figures/tables (no main body).
- `scope="all"` — everything in one file (legacy; use only if asked).

If `prepare_export` shows any `supplementary_figures` / `supplementary_tables`,
deliver BOTH files: run once with `scope="main"` to `{slug}.{ext}` and again
with `scope="supplementary"` to `{slug}_supplementary.{ext}`. Tell the user
both paths.

The tool:
- Re-runs `prepare_export` (so warnings are fresh)
- Writes manuscript.md + references.bib + every figure file into a
  temp dir
- **Resolves + downloads the journal's CSL citation style** (see
  "Journal citation style" below)
- Invokes Pandoc with appropriate flags (citeproc + `--csl` when a bib
  exists, `-t latex` for tex, etc.)
- Uploads the output blob to Storage at
  `papers/{slug}/exports/{filename}` so it's downloadable from the
  dashboard.

Returns `{ local_path, blob_path, format, size_bytes, csl_filename,
csl_status, warnings, placeholders, unresolved_citations }`.

### Journal citation style (CSL)

The export matches the **journal's citation format** automatically — no
manual CSL handling. The pipeline:

1. `prepare_export` resolves `paper.journal` → a CSL filename, offline,
   in this order:
   - the project's **CSL registry** (entries you pinned earlier)
   - an **in-code map** of ~30 common journals
   - a **kebab-case guess** of the journal name
2. `export_to_path` downloads that `.csl` from the public
   citation-style-language/styles repo and passes it to Pandoc.
3. A successful download of a *guessed* slug is **auto-registered** in
   the project registry, so the next export of that journal is exact.

`export_to_path` returns `csl_status`:

- `downloaded` — style fetched + applied. Report `csl_filename`.
- `explicit` — you passed `csl_path=` with a local CSL file; used as-is.
- `missing` — the resolved filename isn't in the styles repo (or the
  network failed). Export still succeeds with Pandoc's **default**
  style; a warning carries the filename that failed.
- `no_journal` — `paper.journal` is empty; default style used.
- `no_references` — the paper has no references, so CSL is moot.

**When `csl_status` is `missing`:** the journal name probably doesn't
kebab-case to a real style slug. Look up the correct filename at
https://github.com/citation-style-language/styles and pin it:

```
mcp__co_scientist__register_journal_csl(
  journal="<exact paper.journal value>",
  csl_filename="journal-of-experimental-botany.csl",
)
```

Then re-export. `list_journal_csls()` shows what's pinned;
`delete_journal_csl(journal)` removes an entry. Never guess a CSL
filename into the registry — only pin one you verified exists in the
styles repo.

### 5. Confirm + tell the user where the file is

- Local path: `output_path` (the file on the user's machine).
- Cloud copy: dashboard's Paper → Manuscript card will list it under
  Exports.

If `rc != 0` or stderr mentions errors, surface them. Most failures are:
- Pandoc not installed → ask the user to `brew install pandoc` /
  `apt install pandoc`
- LaTeX engine missing (for PDF) → suggest `--pdf-engine=...` or
  fall back to DOCX
- Unicode math errors → tell user to check `prepare_export`'s
  warnings

## Safety rules

- **NEVER skip `prepare_export` warnings silently**. The dashboard's
  DOI-verification system depends on those warnings being surfaced to
  the user.
- **NEVER re-invent the export pipeline** in the skill (don't manually
  build BibTeX, don't manually run pandoc). The MCP tools already do
  it; deviating risks shipping stale figure data — the original
  co-scientist had a May 2026 incident where re-implemented assembly
  shipped an outdated figure caption.
- **NEVER hardcode or guess a CSL filename**. CSL resolution is
  harness-managed: `prepare_export` resolves it and `export_to_path`
  downloads it. The only manual lever is `register_journal_csl` with a
  filename you *verified* exists in the styles repo — used to correct a
  wrong guess, never to invent one.

## Common follow-ups

- "Make it ready for Nature" → set `paper.journal = "Nature"` via
  `update_paper`, then re-export — the Nature CSL is resolved and
  downloaded automatically.
- "The citations look wrong for this journal" → check `csl_status` in
  the export result. If `missing`, pin the correct style with
  `register_journal_csl` (see "Journal citation style") and re-export.
- "Strip references" → call `delete_reference` for each; warnings will
  shift to "unresolved citations" instead. Decide with the user
  whether to leave inline DOI markers as plain text or remove them.
- "Export the supplementary only" → `export_to_path(..., scope="supplementary")`
  produces a standalone Supplementary Material file with just the
  supplementary figures/tables (≥ 101). The default `scope="main"` export
  excludes them; export both files when supplementary content exists (see
  step 4).

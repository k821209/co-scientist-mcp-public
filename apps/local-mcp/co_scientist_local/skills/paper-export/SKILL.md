---
name: paper-export
description: Export a paper to .docx / .tex / .pdf / .md / single-file .html via Pandoc. Use when the user says "export," "download as Word/PDF/LaTeX," "send to journal," or any phrasing that asks for a finished document file.
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


## Re-running an analysis invalidates its prose — all of it

Nothing downstream of a rerun updates itself, and the failures are FACTUAL, not
merely stale. Three shipped-ready cases in one session:

- **A legend described a panel that no longer exists.** A figure was restructured
  by editing its plotting script; the legend still listed four panels with `(C)` =
  MDS, and the figure had three with `(C)` = the heatmap. A reviewer would have
  looked for a panel that is not there and found panel C under the wrong letter.
  This is a STRUCTURAL mismatch, not a wrong number — no numeric check sees it.
- **A supplementary caption was a whole cohort out of date**: "top 200 novel
  candidates … Two-sheet workbook … AMI range 0.349–0.738 … five of six", against
  a file with 3 sheets, 477 rows, AMI 0.011–0.108, four of six. Every claim wrong.
- **Two supplementary tables had no caption at all**, while being cited in the
  manuscript. `prepare_export` now warns for this one.

So after any rerun or figure restructure, diff each of these against the
regenerated artifact — the legend, the supplementary caption, and the table
description. `prepare_export` catches the classes it can see (a linked analysis
newer than the artifact, an uncaptioned supplementary item); the panel-letter and
in-file claims are yours to check.

## Flow

### 1. Resolve the target paper

- If the user already named a slug, use it.
- Otherwise call `mcp__scivo__list_papers()` and ask which one.

### 2. Run `prepare_export(slug)` — pre-flight check

The tool returns a bundle with a `warnings` array plus dedicated lists:

- `placeholders[]` — TBD / TK / XXX / TODO / FIXME / `[...]` markers
- `unresolved_citations[]` — `{doi:…}` references not in `references/`
- `legend_warnings[]` — figure/table legends that are over-long or restate the
  Results (one line each). Run `lint_legends(slug)` for the full detail
  (flags, duplicated spans, trim suggestion). A legend should describe the
  panels + key numbers + cross-refs; move derivation/interpretation to Results.
- `warnings[]` — short human-readable summary
- the resolved citation style (see "Journal citation style")
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
- Incomplete citations (no volume/issue/pages) → run
  `backfill_references(slug)` once; it fetches CrossRef for every DOI and
  fills the missing locators across the whole bibliography.
- Biology/botany papers → `set_reference_taxa([genus, …])` so genus and
  infrageneric names in reference titles render italic even when CrossRef
  didn't mark them up (seed from the paper's study species; family/order
  ranks like -aceae/-ales are left roman automatically).
- Empty sections → ask the user whether they're intentionally blank.

If the user wants to proceed despite warnings, continue.

### 3. Decide format + output path

- Default format: **docx** (most common journal submission target).
- Other formats, and `html` with its `theme` for material that travels as a
  file rather than to a journal: see `export_to_path`'s description.
- Default path: `./{slug}.{ext}` in the current working directory
  unless the user supplied one.

### 4. Run `export_to_path`

`export_to_path(slug, output_path=…, fmt=…)` — its description carries the
formats, `scope`, `page_size` and `theme`.

**Where tables and figures land.** By default a registered table or figure is
collected into a `Tables` / `Figures` section at the END of the document, which
is right for a journal manuscript and wrong for almost everything else. To put
one IN the body, the author (or you) puts its embed **alone on its own line**
where it belongs:

```markdown
아래 표와 같이 요구사항을 모두 충족한다.

![](table:107)

다음 절에서는 …
```

That renders the caption + table at that spot and it is **not** repeated in the
appendix. Same for `![](figure:5)`. Two rules matter:

- **Alone on its line.** An embed sharing a line with prose can't become a block
  without breaking the paragraph, so it degrades to a bold `**Table 107**` text
  reference instead. Visible, but not the table.
- **An alt-less embed inherits the registered caption.** Write `![](table:8)`,
  not `![Table 8](table:8)`, unless you deliberately want to override the
  caption for this position — an authored alt REPLACES the registered legend.

For a report or proposal (`doc_type="report"`), placing every table and figure
inline this way is normally what the reader expects: a proposal whose 100 tables
sit forty pages away from the prose that cites them does not function as a
document.

**Citations in a report or proposal.** The python-docx path has no citeproc,
so `export_to_path` numbers them itself: `{doi:…}` / `{cite:key}` become `[n]`
in order of first appearance (a run merges to `[1, 2]`), and a References list
is generated from the registered references — at `![](references)` if the
author placed one alone on a line (a commissioned-report template often has
"참고문헌" as a numbered item in the middle), else at the end. No journal style
applies; `csl_status` reads `not_applicable`. `prepare_export` says how many
markers will render this way before the file exists. Never replace markers by
hand: the numbering then has to be kept in step with every added reference.

**Raw HTML in a report.** The python-docx path renders `<br>` — a line break,
including inside a table cell, which is the one way markdown has to break a
cell — and no other tag. Anything else is dropped and named in the export's
warnings (and in `prepare_export` beforehand); write it as markdown instead.

**Main vs supplementary (`scope`).** The ≥ 101 supplementary convention
applies to `doc_type="paper"` ONLY — in a report or proposal, table 100 is the
hundredth table, and every item is body content. `scope="all"` is legacy; use
it only if asked. If `prepare_export` shows any `supplementary_figures` /
`supplementary_tables`, deliver BOTH files (`{slug}.{ext}` and
`{slug}_supplementary.{ext}`) and tell the user both paths.

**Read the `warnings` for dangling references.** A warning of the form
"the body references Table 107 … excluded by scope='main'" means the reader gets
a reference with nothing behind it. Do NOT hand over the file until it is
resolved — the reference count is the thing to check, not the file's existence.

**A very large document.** `prepare_export` on a ~100-table document exceeds the
tool-reply limit and spills to a file. Ask for the keys you need instead:
`prepare_export(slug, fields=["sections", "tables"])`. Add
`stage_dir="/tmp/…"` to also write every figure's image file to disk and get a
`local_path` per figure — needed only if you are assembling a document yourself
rather than using `export_to_path`.

### Journal citation style (CSL)

The export matches the **journal's citation format** automatically from
`paper.journal` (resolution order: `register_journal_csl`'s description); a
successful download of a guessed style is auto-registered for next time.
Report `csl_filename` from the export result.

**When `csl_status` is `missing`** the export still succeeded, with Pandoc's
default style. Find the correct filename and pin it with
`register_journal_csl(journal="<exact paper.journal value>", csl_filename=…)`,
then re-export. `list_journal_csls()` shows what's pinned;
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
  it; deviating risks shipping stale figure data.
- **NEVER hardcode or guess a CSL filename**. CSL resolution is
  harness-managed: `prepare_export` resolves it and `export_to_path`
  downloads it. The only manual lever is `register_journal_csl` with a
  filename you *verified* exists in the styles repo — used to correct a
  wrong guess, never to invent one.

## Common follow-ups

- "This is a proposal/report, not a paper" → the document should have
  `doc_type="report"` (`update_paper(slug, doc_type="report")`). That switches
  the .docx engine to python-docx (Hancom-safe) and turns OFF the +100
  supplementary convention. Then place tables/figures inline (see step 4);
  A4 is already the default page size.
- "Make it A4" / "the RFP requires A4" → already the default. Pass
  `page_size="letter"` only when a US journal asks for Letter.
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
- "The journal also wants a marked-up / tracked-changes copy" →
  `/tracked-changes-export`, which marks the differences between the
  submitted file and the revised one as real `w:ins`/`w:del` revisions. Read
  its step 1 before assuming this export is the revised one: for a paper
  already sent, the revision is applied to a copy of the SUBMITTED file, which
  carries material no export can regenerate. Do NOT diff the markdown for this: that produces coloured
  strikethrough with zero revision marks, which Word's review pane cannot show
  and a reviewer cannot accept or reject.
- **Anything you build locally is NOT uploaded.** `export_to_path` uploads its
  own output only; a locally produced file (tracked-changes docx, response
  letter, converted table) needs an explicit
  `attach_export(slug, local_path=…, scope=…)` or it never appears on the
  dashboard.
- **If `export_to_path` times out, check before retrying** — its description
  says how.
- **A separate document exports under ITS OWN slug.** Exporting a response
  letter / cover letter that lives as its own paper puts the blob at
  `papers/<that-slug>/exports/…`, so it never shows on the manuscript's Exports
  tab. The "local artifacts need attach_export" rule doesn't cover this —
  `export_to_path` DID create the file, just somewhere else. When the deliverable
  belongs to a submission package assembled on another paper, follow the export
  with `attach_export(slug=<manuscript>, local_path=…, scope="main")`.

## When this file is what actually goes to the journal

An export is normally edited by hand before it is sent. When the user tells you
which file was submitted, `register_submission(slug, local_path=…)` — that copy,
not this export — so the baseline `/tracked-changes-export` and
`/reviewer-frame-check` need exists, and `submission_sync` can say whether the
sections still match it. Only from what the user says was sent; never infer it.

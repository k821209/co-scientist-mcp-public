"""Canonical agent-facing guide for the co-scientist MCP.

Returned by the `project_guide()` MCP tool. Update HERE (not in the
dashboard's CLAUDE.md template) so changes flow to all users on
`pip install --upgrade co-scientist-local` — even those whose CLAUDE.md
on disk was downloaded months ago.

CLAUDE.md on the user's project directory stays tiny (project identity
only) and refers the agent here on every session start.
"""
from __future__ import annotations

GUIDE_VERSION = "2026-07-04a"


def render_guide() -> str:
    """The canonical session-start guide, rendered as markdown."""
    return f"""# co-scientist MCP — session guide (v{GUIDE_VERSION})

## How this project works

A human collaborator views the dashboard and can leave inline comments on
specific passages by drag-selecting in the manuscript. Each comment lands
in Firestore as a `review` with `source='user'`, `status='open'`, plus an
`anchor_text` field containing the exact selected passage and a
`manuscript_ref` like `section:<key>`. The dashboard renders the anchor
as a yellow highlight in the rendered manuscript; clicking the highlight
opens a popover with the comment. The highlight is re-matched against the
*current* text on every render (not pinned to a stored offset), so editing
elsewhere never breaks it — but a comment whose stored `section` points at
the wrong section can still fail to highlight. After bulk edits (import,
mass section rewrites, `/paper-revision`) run
`mcp__co_scientist__reconcile_review_anchors(slug, dry_run=True)` to preview
which comments need their `section` corrected, then re-run with
`dry_run=False` to apply; comments reported as `truly_missing` are ones
whose passage is genuinely gone — review those with the user. To correct a
single comment by hand use `update_review(slug, review_id, section=…,
anchor_text=…)`, and to retract a wrong AI reviewer note use
`delete_paper_comment(slug, review_id)`.

When you ADDRESS a comment by rewriting the sentence it pointed at, re-anchor
it in the same step so the highlight follows to the revised text:
`resolve_paper_comment(slug, review_id, status="accepted", response=…,
new_anchor_text="<verbatim phrase from the new text>")`. Without this the old
anchor no longer matches and the dashboard can only fall back to the top of
the section.

On every session start:

1. Call `mcp__co_scientist__whoami()` once — verifies the MCP is bound to
   the project_id your CLAUDE.md mentions. If they differ, STOP and tell
   the user — they likely mixed `.mcp.json` and `CLAUDE.md` from two
   different dashboard projects. (The MCP also prints a stderr warning
   banner on startup when this mismatch is detected.)
   whoami also returns `update_available` / `update_hint`: if
   `update_available` is true this install is behind the latest published
   build — tell the user to run the `update_hint` command (`git pull` +
   `pip install -e` in the public checkout) and restart before you rely on
   tool behavior, since a bug you're about to hit (or report) may already
   be fixed upstream.
2. Call `mcp__co_scientist__get_project_memory()` — the project's durable
   knowledge (user preferences, decisions, gotchas). Treat it as standing
   context for the whole session. See "## Project memory" below. Also call
   `mcp__co_scientist__get_project_skills()` — freeform, project-scoped
   playbooks/instructions the user defined in the Memory tab; follow them for
   THIS project (they complement the built-in skills). Skip if it returns "".
3. Call `mcp__co_scientist__list_papers()` then, for each paper,
   `mcp__co_scientist__count_open_user_comments(slug)`. If non-zero,
   call `mcp__co_scientist__list_reviews(slug, status="open")` to get
   the open comments with their `anchor_text` — use that quoted passage
   to locate the exact place in the manuscript the user is pointing at,
   then offer `/paper-revision`. Each comment also carries a `decision`
   the author sets in the dashboard (`accepted` / `pending` / `rejected`):
   act only on `accepted` ones, never on `rejected`, and ask before
   touching `pending` ones. `list_reviews(slug, status="open",
   decision="accepted")` is the approved work list.
   `mcp__co_scientist__review_triage_summary(slug)` gives the whole
   picture in one call — including `rejected_without_rationale`, the
   rejected comments still missing a rebuttal (those block a clean export
   and need a `response` via /paper-revision), and `ai_open`, the
   `/paper-review` self-review findings still open. After acting on an AI
   finding you MUST resolve it (`resolve_paper_comment(slug, review_id,
   status="accepted", new_anchor_text="<verbatim from the revised text>",
   response="<what changed>")`); a finding you defer stays open but needs a
   `response` stating the plan. Editing the manuscript never auto-resolves a
   finding, so drive `ai_open` to 0 before calling a review handled.
   For any deck on the paper, also call
   `mcp__co_scientist__list_deck_comments(slug, deck_id)` — open slide
   comments are the deck's revision to-do list; revise the slide, then
   `resolve_deck_comment`.
4. For each paper, call `mcp__co_scientist__check_requirements(slug)`.
   If `configured` is true and `violations` is non-empty, surface them
   (e.g. "abstract 178/150 words — over the Short Communication limit")
   and offer to fix. If `configured` is false and the paper has a
   target `journal` set, suggest `/journal-requirements` so the
   journal's word/figure/section limits get tracked.
5. Call `mcp__co_scientist__list_servers()` — the project's registered
   compute (HPC nodes, workstations). Treat this as the inventory of
   where analyses can run. See "## Compute resources" below.

## Compute resources

The user's compute — HPC nodes, lab workstations, their cores/RAM/GPUs
and conda/venv/module environments — is **structured data**, not memory.
It lives in the servers registry (`/projects/{{pid}}/servers`) and drives
the dashboard's **Runs tab**, the politeness caps, and `submit_remote_job`.

- When the user describes a machine they compute on (host, login user,
  cores, GPUs, an HPC alias from their `~/.ssh/config`), register it with
  `add_server(...)`; register each environment with `add_server_env(...)`.
  Update specs with `update_server(...)` when they change.
- **NEVER** write hardware specs, hostnames, core counts, or env names
  into project memory. That is the single most common mistake — memory is
  for *soft* knowledge, the registry is for *machines*. If you catch
  compute details sitting in memory, move them to the registry and prune
  the memory entry.
- `ssh_key` stores a *path on the user's disk*, never key material.

## Available skills

- `/paper-writing [title]` — create or update manuscript sections
- `/paper-import [file]` — import an existing .docx/.pdf/.odt/.tex
  manuscript: `import_document` converts to markdown, the agent splits
  it into canonical sections, registers figures + references.
- `/paper-revision` — address open user comments (anchor_text-anchored)
- `/response-letter` — turn a journal's decision letter into a point-by-point
  response. Real reviewer points are registered as `source='reviewer'`
  comments (with `reviewer_name` + `round`), triaged like any comment
  (accept→revise, reject→rebuttal in `response`), then compiled into the
  letter. Internal `/paper-review` (`source='ai'`) is never included.
- `/journal-requirements` — capture a target journal's submission spec
  for a paper type (Article / Short Communication / Letter / Review …):
  the agent reads the journal's live author guidelines and stores word
  limits, figure/table caps, structured-abstract + required-section
  rules; `check_requirements` then measures the manuscript against them.
- `/paper-export [docx|tex|pdf|md]` — pandoc-based export with placeholder/
  unresolved-DOI pre-flight check; auto-resolves the journal's CSL
  citation style (in-code map → kebab guess → per-project registry,
  downloaded from the CSL styles repo); uploads result to Storage so the
  dashboard's Paper page lists it.
- `/literature-review [topic] [slug?]` — CrossRef keyword search via
  `search_works`, candidate-then-pick UX, registers selected via
  `add_reference_by_doi`, writes a structured synthesis.
- `/paper-review [slug] [mode?]` — three-persona AI review (methods /
  stats / domain) + consistency pass; each finding becomes one
  Firestore review row (`source="ai"`) anchored to the offending
  passage so the dashboard renders inline highlights.
- `/analysis-run [name]` — wrap a computation (local or registered HPC)
  in a tracked run, then `add_figure` / `add_table` selected outputs.
  Dashboard Runs tab streams logs in real time.
- `/scientific-image` — staged pipeline (classify → blueprint →
  generate → critique) around `generate_image` for schematics
  (pathway, network, workflow, comparison, architecture, tree).
  Real data plots go through `/analysis-run` instead.
- `/paper-deck [slug] [audience] [duration_min] [--theme slug]` —
  full presentation pipeline: deck concept + slides + render
  (`render_deck`) + PPTX export (`export_deck_to_pptx`).
  **Iteration discipline:** while editing slides, preview with
  `preview_slide` (one slide → PNG, seconds). Call `export_deck_to_pptx`
  only ONCE the deck is done (or when the user asks for the file) — it
  re-renders every slide (tens of seconds to minutes). Don't re-export
  after each edit. **After a design / batch / large-text edit: run
  `preview_slide`, `Read` the returned PNG yourself to verify it (catch
  code errors, overflow, the warning lists — incl. `inner_margin_tight`, a
  bespoke label hugging a band/card edge: fix by anchoring labels to the
  diagram's rail/centre `rail_y ± offset`, not the band edge), then ASK the
  user to confirm before the next slide/batch** — don't fire-and-forget
  `update_slide`.
  (A one-char typo fix is exempt.)
  **User-uploaded slide images:** images the user uploads from the dashboard's
  Presentations tab land ON the slide (NOT in materials/assets —
  `list_materials`/`list_assets` won't show them). Each is a region with
  `image_source=='upload'` (ids `upload_1`, `upload_2`, … — a slide can have
  several); find them via `list_slides(slug, deck_id, fields=['regions'])` and
  place each with `h.image_region(slide, '<id>', …)`. Each region's **`note`**
  is the user's hint on what the image is / how to place it — read and honor
  it. `placement=='auto'` means the user left positioning to you (pick the
  frame that fits the note + layout); `'manual'` keeps their box. Never tell
  the user an uploaded slide image is inaccessible.
- `/promote-result [slug] [analysis]` — map an analysis group's
  output files onto manuscript figures/tables (map mode → promote mode).
- `/supplementary-material [slug]` — identify + register supplementary
  figures/tables/text (the +100 figure_number offset convention).
- `/reorder-supplementary [slug]` — renumber/reorder SFigs or STables
  (`reorder_supplementary`): moves docs + figure blobs server-side and
  rewrites `{{fig:N}}`/`{{tab:N}}` + `![](figure:N)` refs; reports prose
  mentions to fix.
- `/analysis-audit [slug]` — scan analysis scripts for hardcoded
  literals + verify cited manuscript numbers against live data.
- `/release-publish [slug] [analysis]` — audit + publish an analysis
  release folder as a standalone GitHub repo (git workflow, gated).

## Tool surface (~60 tools under `mcp__co_scientist__*`)

papers · sections · reviews · figures · tables · references · materials
· analyses · runs · servers (HPC) · exports · journal CSL · requirements
· project memory · todos + activity · image gen · whoami · project_guide

**To-dos + activity timeline** — the dashboard's **Activity tab** shows a
shared checklist and a unified, reverse-chronological feed of what's
happening. Record planned work with `add_todo(text)` and flip items with
`update_todo(todo_id, status="in_progress"|"done")` so the human sees
progress. Routine writes (papers/sections/reviews) post to the timeline
automatically; use `log_activity(title, detail)` for milestones or decisions
that wouldn't otherwise appear. Read it back with `list_todos()` /
`list_activity()`.

**Materials** are user-uploaded source files shared across the project
(PDFs to read, datasets, prior drafts, notes) — distinct from `references`
(cited works). Call `list_materials()` at session start; pull any you need
with `get_material(material_id)` (downloads to disk), then read the
returned path with your file tools. Each material has two separate notes:
`user_note` (the user's — NEVER write or overwrite it) and `ai_note` (yours).
Once you've figured out what a file is, record it with
`update_material(material_id, ai_note=…)` so it shows in the dashboard; never
touch `user_note`.

## Project memory

`get_project_memory()` returns this project's durable knowledge — a
markdown document stored in the cloud at `/projects/{{pid}}/memory`,
shared across machines and editable in the dashboard's **Memory** tab.
It is the **source of truth for soft project knowledge**.

- **Read** it at session start (step 2 above) — standing context.
- **Record** new durable facts with `append_project_memory(note)`;
  reorganize/prune with `update_project_memory(content)`.

WHAT belongs here: the user's writing preferences, decisions taken and
why, approaches tried and rejected, domain gotchas, target-journal
history — knowledge NOT recoverable from the papers / sections /
reviews / figures themselves.

WHAT does NOT belong here — each of these has a structured home; put it
there, never in memory:
  - compute servers / HPC specs / hostnames / env names → `add_server`,
    `add_server_env` (servers registry → Runs tab)
  - analysis runs, commands, results, log output → the run records
    created by `/analysis-run` (Runs tab)
  - section text, review comments, figure captions, citations → already
    in the structured data; never duplicate it
  - transient session state ("currently editing X", "next I'll do Y") —
    that is task tracking, not durable knowledge

Memory is a **curated digest, not an append-only log.** Before adding,
check whether the fact has a structured home (above) or already exists in
memory. Keep entries concrete and short, and `update_project_memory` to
prune stale/duplicate lines — don't just keep appending.

This is separate from Claude Code's own local auto-memory (a harness
feature, machine-local). Project knowledge goes HERE — cloud-backed, so
it survives a new machine and the user can see it.

## Citation format + hallucination check

Inline DOI: `{{doi:10.1234/example}}`. References auto-managed via
`mcp__co_scientist__add_reference_by_doi(slug, doi)` — fetches title,
authors, journal, year from CrossRef so you never invent them. Refuses
DOIs CrossRef can't find (404 → almost always a hallucinated citation).

Two-axis verification model — and the MCP only owns one of them:

  - **DOI axis** (server-decidable): does CrossRef know this DOI?
    Browser Sync button and `validate_references` both write this.
    Deterministic — no LLM needed.
  - **Context axis** (YOU decide, not the server): does the cited
    paper's content actually fit the manuscript's claim around its
    `{{doi:X}}` marker? Word-overlap is too weak a proxy; only you
    have the manuscript intent loaded.

Workflow YOU follow per session:

1. Call `mcp__co_scientist__validate_references(slug)`. It returns a
   facts pack:
     - `unresolved[]` — CrossRef 404s. Almost always fake DOIs.
     - `missing_doi[]` — references with no DOI to check.
     - `results[]` — one entry per resolved DOI with:
         * `crossref`: title, abstract, subjects, authors, year, journal
         * `manuscript_contexts`: every `{{doi:X}}` occurrence with
           full sentence + ±240 char context + `stacked_with` peers
         * `signals`: raw overlap counts (HINTS, not verdicts)
2. For each `results[]` entry, READ the crossref abstract/title and
   compare against `manuscript_contexts`. Decide if the citation fits.
3. Record your decision:
     `acknowledge_finding(slug, doi, verdict="approved"|"rejected",
        note="<why>")`
   - approved → context_verified=true → dashboard ribbon turns green
   - rejected → context_verified=false → fix the citation (delete or
     replace via `add_reference_by_doi`) before next session

For unresolved DOIs, just delete the reference (or replace via
`add_reference_by_doi(slug, real_doi)`) and `acknowledge_finding(slug,
doi, note="hallucinated, removed")`.

The dashboard shows two ribbons per reference (`✓ DOI` / `✓ Context`).
`?` Context means you haven't judged it yet. Both green = trusted.

**On every session start, also call**
`mcp__co_scientist__list_verification_findings(slug)` for each paper.
Returns unacknowledged problem findings (unresolved hallucinations,
title mismatches, errors). If non-empty:
  1. Surface them to the user.
  2. Fix each (delete bad ref / replace with real citation / re-fetch
     via `add_reference_by_doi`).
  3. Call `acknowledge_finding(slug, doi, note="...")` once handled
     so it stops surfacing.

For single-citation spot checks: `verify_doi(doi)` returns metadata
without writing anything.

## Prose for non-English audiences (todo 001)

When generating prose for a non-English audience — Korean, Japanese,
Chinese, etc. — draft *natively* in that language. Do not write English
first and translate; the result reads as translation-ese (em-dash
chains, mixed sentence endings, English noun + native particle pairs)
that a native reader spots on first pass. Keep English **only** for
field-standard abbreviations (GWAS, BLUP, MCP, F4, GO, OTU). Translate
everyday English nouns (shortcut → 지름길, process → 과정). Keep sentence
endings consistent within a unit (Korean: all `~합니다` or all `~한다`).

Self-check before delivery: "Could a native speaker mentally reverse-
translate this word-for-word to English?" If yes, rewrite.

This applies across `/paper-deck`, `/paper-writing`, `/paper-revision`,
`/paper-export` — any skill generating user-visible text.

## Math mode (Pandoc)

Use `$...$` (inline) or `$$...$$` (display) for variables with
sub/superscripts, Greek letters as variables, fractions, sums. Leave
`n = 69` / `q < 0.005` / `α-helix` as plain text. `prepare_export` returns
`math_warnings` flagging violations.

## Remote job rule

**Never** launch a long-running remote job via raw `ssh <alias> "nohup ..."`.
Use `mcp__co_scientist__submit_remote_job` so the run is tracked in
`analysis_runs` and visible in the dashboard.

## Image generation

`mcp__co_scientist__generate_image` routes through the Firebase Cloud
Function (Cloud Run gen2) backed by OpenAI gpt-image-2.

**Plan gating** — the function enforces:
  - `plan_id="free"`   → HTTP 403 (`PermissionError` on the client).
  - `plan_id="pro"`    → up to 200 images / month
  - `plan_id="max"`    → up to 2000 / month
    (`enterprise` is a legacy alias for `max`, same 2000 quota)

Free-tier users who want image generation do it OUTSIDE this MCP —
wire up another image-gen MCP / built-in Claude Code tool with their
own API key. The skill `/scientific-image` will surface the 403 to the
user and suggest the upgrade.

### The figure's stored prompt is the source of truth

The user can edit a figure's generation prompt (and its aspect ratio /
quality) directly in the dashboard and re-render it there. That edited
prompt is saved back onto the figure. So your own memory of how you
first drew a figure may be **stale** — the user may have changed it.

Before you regenerate or overwrite any existing figure:

1. **Always `get_figure(slug, n)` first** and read its stored `prompt`,
   `aspect_ratio`, and `quality`. That is the latest intent (the user's
   dashboard edit wins over your remembered prompt).
2. Use that stored prompt as the **base**, apply only the change being
   requested as a diff on top, and keep `aspect_ratio`/`quality` unless
   asked to change them. Then `generate_image(..., figure_number=n,
   overwrite=true)`.
3. **Never** overwrite a figure with a freshly-written prompt from your
   own memory — that silently discards the user's edit.

A figure with `rerender_pending=true` means the user edited the prompt
in the dashboard and is asking for a re-render: render it from the
stored `prompt` (overwrite clears the flag automatically).
"""

"""Canonical agent-facing guide for the co-scientist MCP.

Returned by the `project_guide()` MCP tool. Update HERE (not in the
dashboard's CLAUDE.md template) so changes flow to all users on
`pip install --upgrade co-scientist-local` — even those whose CLAUDE.md
on disk was downloaded months ago.

CLAUDE.md on the user's project directory stays tiny (project identity
only) and refers the agent here on every session start.
"""
from __future__ import annotations

GUIDE_VERSION = "2026-08-07d"


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
the section. Re-anchoring a comment you are CLOSING also files the passage as
it read before, so the addressed card shows the reader "was … / now …" — you
don't need to restate the old wording in `response`, just say what changed and
why.

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
   be fixed upstream. **`null` means UNKNOWN, not current** — an
   editable/source install whose version can't be compared; then trust
   `git_sha` and have the user check the checkout itself
   (`git status -sb && git pull`), because `pip install --upgrade` is a
   no-op there. Only `false` means "checked, and current".
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
It lives in the ACCOUNT-wide servers registry (`/users/{{uid}}/servers`,
shared across every project; managed on the dashboard **Servers** page) and
drives each project's **Runs tab**, the politeness caps, and
`submit_remote_job`.

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

## Analysis provenance — RECORD EVERY RUN (not optional)

Every computation that produces a manuscript figure, table, or number —
whether a local Bash command, `launch_local_job`, or an HPC job — MUST leave
a run record, so the paper can state *which server, which command, which git
version produced which result*. That provenance is exactly what reviewers and
reproducers need, and this is the #1 silently-skipped step: running an
analysis via raw Bash/ssh and moving on leaves a permanent gap.

- **Prefer the recording paths** — `/analysis-run`, `launch_local_job`, or
  `submit_remote_job`. They create the run record (host, command, env_name,
  log_path, pid) automatically. Do NOT hand-roll a raw `ssh <alias> "nohup …"`
  or a bare local Bash run for a result-producing analysis.
- **Already ran it ad-hoc?** Back-fill immediately: `create_analysis(...)`
  then `record_analysis_run(..., host=, command=, env_name=, log_path=, pid=)`.
  A quick `zcat | …`, a figure script, a one-off `gm_compare` — all count.
- **Figure/table generation IS an analysis** — record the command that made
  each `figure_N.png` / table CSV, not just the "big" jobs.
- **Link the artifact back to its analysis**: pass `source_analysis="<analysis
  name>"` to `add_figure` / `update_figure` / `add_table` / `update_table`. With
  the link, `prepare_export` warns when that analysis has produced output since
  the artifact was last updated — the one check that catches an artifact left
  behind by a RERUN. This has shipped wrong once: a QTL analysis was re-run,
  the prose and legend moved to the new number, the supplementary table kept
  the old one (28.7% vs 33.3%), and every structural check passed because the
  file was perfectly well-formed. Without the link that export is silent, so
  set it whenever you register a generated figure or table. Adding the link to an
  artifact that already exists is safe and does NOT mark it current — the check
  reads when the DATA last changed, so only replacing the content (new `content`,
  or new bytes via `local_path`) clears a warning. Editing a caption or legend
  deliberately will not; if a warning persists, regenerate the artifact or say
  why it is unaffected.
- Reconcile periodically: `list_analysis_runs` shows what's recorded;
  `scan_untracked_jobs` finds detached job-like processes with no record.
  If the user asks "which server did we run on / where's the record" and you
  can't answer from `analysis_runs`, that's the gap this rule prevents.

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
- `/reviewer-frame-check` — read a finished response/cover letter with ONLY what
  the recipient holds (their own report + the manuscript they actually saw) and
  report what the text required from outside that bundle. Run it before a letter
  is final. It catches what `lint_manuscript`'s `insider_context` cannot: a
  removed panel described as having shown the CURRENT cohort when the reviewer
  saw the old one, or numbers compared at mismatched parameters — every word
  ordinary, the error only visible to a reader tracking what each number is for.
  ALWAYS name the profile (`response_letter` / `cover_letter` / `manuscript`):
  the same finding is a defect in one document and correct behaviour in another.
  In a manuscript a pointer elsewhere IS the defect; in a letter, deferring to
  the manuscript is the letter doing its job, and 17 of 38 findings from a
  profile-less run were effectively "write the paper again".
  Must run as a subagent with a fresh context; a session that already knows the
  analysis cannot perform this check on itself, only degrade it. The subagent
  SHIPS — `subagent_type: "reviewer-frame-check"`, linked into `.claude/agents/`
  on MCP startup, declared `tools: Read` so it cannot list or grep its way into
  the analysis outputs. Pass it file paths and the seat name, nothing else; do
  not hand-write its prompt, since the caller is by construction the agent that
  knows every contaminating fact.
- `/journal-requirements` — capture a target journal's submission spec
  for a paper type (Article / Short Communication / Letter / Review …):
  the agent reads the journal's live author guidelines and stores word
  limits, figure/table caps, structured-abstract + required-section
  rules; `check_requirements` then measures the manuscript against them.
- `/paper-export [docx|tex|pdf|md]` — pandoc-based export with placeholder/
  unresolved-DOI pre-flight check; auto-resolves the journal's CSL
  citation style (in-code map → kebab guess → per-project registry,
  downloaded from the CSL styles repo); uploads result to Storage so the
  dashboard's Paper page lists it. **Only `export_to_path` uploads by
  itself** — ANY file you build locally (tracked-changes docx, a response
  letter, a converted table) needs an explicit
  `attach_export(slug, local_path=…, scope=…)`, or it silently never
  reaches the dashboard.
- `/tracked-changes-export` — a real marked-up `.docx` (genuine `w:ins`/
  `w:del`) between the submitted version and the current one, by comparing
  two RENDERED docx files with headless LibreOffice. Never diff the
  markdown: that yields coloured strikethrough with zero revision marks —
  Word's review pane shows nothing and nothing can be accepted.
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
- `/video-harness` — for VIDEO projects: raw recording → publish-ready via
  the `vh` toolkit. One-shot `vh run <input> --preset <screencast|
  talkinghead|shorts|shorts_boxed|slides> [--lang ko]` (clean → reframe →
  transcribe → caption); chapters + title cards are a library step
  (Claude-authored `Chapter(start,title)`). Register output with
  `add_video`. With `VH_RENDER_HOST` set, transcription AND encoding
  auto-offload to a remote GPU; unset → everything local. Render host is user
  config only — never hardcode an address.
- `/video-revision` — address open Video-tab timecode comments
  (`list_video_comments` → re-run only the stage each needs →
  `resolve_video_comment`). The video analogue of `/paper-revision`.
- `/video-dub` — dub a video into another language (default English) with free
  Kokoro TTS on the render host: Claude translates each segment →
  `vh.steps.dub` (tts_segments → assemble_dub → mux_audio) + translated captions
  burned via `compose_summary(caption_words=…)` → `add_video` "(EN)" variant.
  Prereq: kokoro in the render host's VH_RENDER_PYTHON env.
- `/video-publish` — publish a Video-tab item to YouTube (`youtube_connect`
  device-flow OAuth → `youtube_upload` from the local mp4 → URL saved on the
  video). Long-form or #Shorts. **Default privacy unlisted; public only on
  explicit user confirmation** (outward-facing). Idempotent (re-run updates
  metadata). Needs the user's YOUTUBE_CLIENT_ID/SECRET. Playlists (same OAuth,
  no re-consent): `youtube_create_playlist`, `youtube_add_to_playlist`,
  `youtube_list_playlists`, or pass `playlist=` to `youtube_upload` to file the
  video into a series playlist on publish (created if the title is new).
  Thumbnails: pass `thumbnail=` (local PNG/JPEG ≤2MB — 1280x720 for 16:9,
  1080x1920 for a Short) to `youtube_upload`, or `youtube_set_thumbnail` later.
  Custom thumbnails require a VERIFIED channel; a refusal is reported in
  `thumbnail_error` and never fails the upload. **Shorts caveat:** on a 9:16
  Short a custom thumbnail only replaces the 16:9 cards (search/suggested); the
  vertical thumbnail in the Shorts feed stays a frame YouTube picked and no API
  can set it (only Studio/mobile "choose a frame"). Verified 2026-08-04 by
  comparing renditions on live Shorts AND against the official reference, which
  never mentions Shorts or 9:16 — every documented rendition is 16:9. So do
  not plan thumbnail back-fills as a way to lift Shorts-feed views.
- `/news-short` — synthesize a vertical news Short from text (no source video):
  fact-check → script → `news.edge_tts_speak` (free Korean neural TTS; Kokoro
  has no Korean) → `news.align_to_script(transcribe(...), script)` for accurate
  captions → `news.montage` Ken-Burns image band → burned captions → `add_video`
  (9:16) → `/video-publish`. Guardrails: source + publish date on screen, AI
  images disclosed. Prereq: `pip install edge-tts`.
- `/science-short [topic]` — a science explainer Short with DOI-verified
  references: research (2-source) → fact-check vs primary paper → reference
  management in co-scientist (`search_works` → `verify_doi` →
  `add_reference_by_doi(cited_in=[short_id])`, never hand-typed) → self-drawn
  graphics + `news.build_short` → reference card + description auto-built from
  `list_references(slug, cited_in=short_id)` via `vh.refs_card`.
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

### The SUBMITTED BASELINE pointer (record this — it is not derivable)

Nothing in the structured data records **which file the journal actually
received**. The user keeps that snapshot in **Materials**; the pointer to
it belongs HERE, because memory is read at every session start while a
material note is only seen by whoever lists materials.

This matters because the failure is silent: a marked-up copy built against
the wrong baseline passes every validation check and diffs against a
document nobody read. It shipped once, against an n=69 package that was
prepared and then superseded before it was ever submitted — and the newest
archived export is the classic trap, because it sorts first and looks the
most authoritative.

So, ONCE per submission, when you learn which file it was:

1. `list_materials()` — find the candidates. Read `user_note` first: the
   user is the authority on what was submitted, and their note is never
   written by an agent.
2. **Ask the user to confirm, and wait.** One question. Do not infer from
   filenames or dates.
3. Stamp both:
   - `update_material(material_id, ai_note="SUBMITTED BASELINE — <slug>,
     <journal>, submitted <YYYY-MM-DD>. The OLD document for
     /tracked-changes-export; the manuscript the reviewers hold for
     /reviewer-frame-check.")`
   - `append_project_memory("Submitted baseline for <slug>: material
     <material_id> (<filename>), <journal>, <YYYY-MM-DD>.")`

Then no later session has to guess. If no such material exists, say so and
ask the user to upload it rather than substituting the current manuscript —
that substitution silently defeats both skills.

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

Inline DOI: `{{doi:10.1234/example}}`. For a DOI-less registered ref
(software, books, reports, GenBank submissions) cite by its citation_key:
`{{cite:andrews2010}}` (alias `{{ref:key}}`) — otherwise citeproc drops it
from the rendered bibliography even though it's in the .bib. Adjacent citation
tokens of any kind collapse into one parenthetical, so `{{doi:A}}{{cite:b}}`
is fine. References auto-managed via
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

## Write from the READER's context, not yours

You have spent the session inside the analysis and remember all of it. The
reader has read the manuscript once and shares none of your working memory.
That asymmetry is invisible from the inside — every sentence you write reads
as complete to you — and it gets WORSE when you are asked to be concise,
because the clauses that carry reader context are exactly the ones that look
redundant to someone who already knows. **Concision and reader-context pull in
opposite directions; when they conflict, keep the context.**

This is not a style preference: dropped context degrades into factual error. A
letter that reported "genomic inflation falls from λ = 7.03 to 1.23" without
saying which arm it belonged to implied a diagnostic that does not exist for
the other method.

**First-use audit — run it before delivering any prose.** For every technical
term, symbol, threshold, and named cross-reference, find its FIRST occurrence
and confirm that occurrence carries:
  (a) what it means (`K` = "the number of permutation strata", not bare `K`),
  (b) the scale or baseline that makes a value interpretable,
  (c) which method / arm / reviewer it belongs to when more than one is in play
      ("Reviewer 1's Major 3", not "Major 3"; λ attributed to the PLINK arm).
This is mechanical — grep the first index of each term — so do it, don't
aspire to it.

Two corollaries:
- **A number without a scale is not information.** "0.904, on a 0–1 scale where
  1 means the same partition" beats "0.904"; "28.7% against a chromosome-matched
  null of 21.5% ± 2.8%" beats "28.7%". Give the causal step too: "a permutation
  test cannot return a p-value below one over the number of arrangements it can
  draw, so the floor was 8.3e-4".
- **When compressing, cut claims, not the context that makes a claim
  checkable.** The safe cut is a sentence the manuscript already carries in
  full; the unsafe cut is the clause explaining why a number matters.

Applies to `/response-letter` (highest risk — its readers have not seen the new
analysis and are deciding whether to believe it), `/paper-writing`,
`/paper-revision`. Distinct from the plain-English rule below: that one is about
sentence difficulty, this one is about missing premises, which survive any
amount of simplification.

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
`analysis_runs` and visible in the dashboard. Untracked raw-ssh jobs are the #1
reason the Runs tab is both blind to real work and cluttered with stale rows.

Run liveness is **heartbeat + TTL**: a run shows a live spinner only while
`now - last_heartbeat < 4h`; past that the dashboard marks it **stale** (the
launching session likely died) instead of spinning forever. `poll_remote_pids`
refreshes the heartbeat for still-alive PIDs (and finishes dead ones); for a
long job you're actively watching, call `heartbeat_run(slug, analysis, run_key)`
periodically, and `mark_run_finished` when it's done.

A row you wrote with `record_analysis_run` and no `pid` (provenance for a
foreground command) has nothing to poll — close it with `mark_run_finished`
right away. `auto_finish_stale_runs()` also closes such rows now, counting them
as `provenance_closed`; call it with no arguments to sweep every open row
regardless of age (`since_hours` only narrows the sweep).

## Image generation

`mcp__co_scientist__generate_image` routes through the Firebase Cloud
Function (Cloud Run gen2) backed by OpenAI gpt-image-2.

**Plan gating** — the function enforces:
  - `plan_id="free"`   → HTTP 403 (`PermissionError` on the client).
  - `plan_id="pro"`    → up to 200 images / month
  - `plan_id="max"`    → up to 2000 / month
    (`enterprise` is a legacy alias for `max`, same 2000 quota)

Call `mcp__co_scientist__get_plan()` to check the owner's tier + limits
(authoritative, from their billing state) BEFORE attempting a paid-only feature
— it returns `can_generate_images`, `upload_limit_mb`, `project_cap`, etc., so
you can tell the user "image generation needs Pro" instead of hitting a 403.

For a third-party API token that spans the user's projects (e.g. a Zenodo
token), read it with `get_user_secret("<key>")` — an **account-wide** store
(users/{{uid}}/secrets, owner-only), set by the user in the dashboard Account
tab (or `set_user_secret`). It's shared across all their projects and machines,
private to them, and never in a project doc or git. `list_user_secrets()` shows
the key names (not values). Don't put such tokens in project memory/settings.

`generate_image` without a `slug` stores a **project-scoped asset**
(`projects/{{pid}}/assets/`) — use it for a video/other project that has no paper
(no dummy paper needed). Manage them with `list_assets()` (no slug), register a
local file with `add_asset(local_path)`, and pull one back to disk with
`get_asset(id_or_filename, dest_path)` so path-taking tools (ken_burns/montage)
can consume it.

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

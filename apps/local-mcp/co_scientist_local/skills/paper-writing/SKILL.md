---
name: paper-writing
description: Create a new paper or update sections of an existing one. Use when the user wants to start writing, expand a section, or draft text for a specific part of the manuscript.
---

# /paper-writing

**Triggers:** "write the introduction," "draft methods," "create a new paper on X," "expand section Y."

## Flow

### Starting a new paper

1. Ask the user for title + target journal if not provided.
2. Ask which document type this is — **논문(paper) / 보고서(report) / 기타(other)** —
   and pass it as `doc_type`. Default to `"paper"` if the user just wants a
   journal manuscript.
   - `doc_type="paper"` seeds the canonical 6 sections and exports via pandoc
     (journal citation styles, CSL).
   - `doc_type="report"` / `"other"` start with **no sections** (you structure
     the body freely with markdown headings) and export to **.docx via
     python-docx** — a native file that opens cleanly in 한컴오피스/Word.
3. Call `mcp__co_scientist__create_paper(title=..., journal=..., doc_type=...)`.
4. For a `paper`, the canonical 6 sections (abstract, introduction, methods,
   results, discussion, conclusion) are seeded automatically. For
   `report`/`other`, add sections yourself with markdown `##` headings in the
   body as you draft.
5. Suggest next steps: literature review, methods draft, etc.

### Working on an existing paper

1. Call `mcp__co_scientist__list_papers()` if the slug isn't provided.
2. Call `mcp__co_scientist__get_paper_state(slug)` to see the current
   state of all sections and the assembled manuscript.
3. For each section the user wants to write:
   - Ask any clarifying questions (target audience, key claims).
   - Draft the section content **per the Writing craft rules below**
     (section contracts, journal register, no duplication).
   - Call `mcp__co_scientist__update_section(slug, key, body=..., status='draft')`.
4. After updating sections, run `mcp__co_scientist__lint_manuscript(slug)`,
   resolve every warning, then call `mcp__co_scientist__get_paper_state(slug)`
   and show the user a summary of what changed (and the clean lint result).

## Writing craft — read before drafting ANY section

Real reviewers rejected three things: **results bleeding into Methods**,
**non-journal prose**, and **repeated content**. Prevent all three while
drafting, then verify with `lint_manuscript` (below) before you call a
section `complete`.

### 1. Section contracts — what each section INCLUDES and EXCLUDES

Write only the content that section owns. A fact has exactly ONE home.

| Section | Includes | NEVER put here |
|---|---|---|
| **Abstract** | 1–2 sentence background, aim, key result WITH the number, one takeaway | New info absent from the body; sentences copied verbatim from other sections |
| **Introduction** | Context → the gap/problem → this study's aim/hypothesis | Methods detail; results; discussion of your own findings |
| **Methods** | What you DID — materials, procedures, analyses — **past tense**, reproducible | **Any finding, statistic, p-value, or "we found/observed"**; interpretation |
| **Results** | What you FOUND — observations, numbers, stats, figure/table callouts | How-to/procedure ("using the X kit… per manufacturer"); interpretation/"why" |
| **Discussion** | Interpretation, comparison to prior work, mechanism, limitations | **New results/numbers not already in Results**; restating Results sentence-by-sentence |
| **Conclusion** | The single main claim + implication/next step | New data; a paragraph-length recap of Results |

Rule of thumb: **Methods = past-tense procedure, no findings. Results =
findings, no procedure. Discussion = meaning, no new data.**

### 2. Academic register (journal prose, not chat prose)

- **Tense:** Methods & Results in **past** ("cells were treated", "yield
  increased 32%"); established facts & interpretation in **present**
  ("BLUP improves accuracy"). Keep it consistent within a paragraph.
- **One claim per sentence.** Split any sentence over ~40 words. Prefer
  subject-verb-object over nested clauses.
- **Be specific, hedge honestly:** "increased 2.4-fold (p = 0.003)", not
  "increased significantly a lot"; "suggests", not "proves".
- **Cut LLM tells** — never write: *"It is important to note that…",
  "plays a crucial role", "a wide range of", "delve into", "sheds light
  on", "pave the way", "utilize"* (use "use"), *"in order to"* (use "to").
  State the fact directly.
- **Define a term once**, then reuse it; don't re-explain.
- **Korean manuscripts** (보고서/국문 논문): draft natively in Korean
  academic register (`~하였다 / ~로 나타났다`), consistent sentence endings,
  keep only field-standard English abbreviations (GWAS, BLUP, QTL). Don't
  translate from English — it reads as 번역체. Avoid `매우 중요한 역할을 한다`,
  `아무리 강조해도 지나치지 않다`, 완곡어 남발.

### 2b. Clarity over eloquence — draft plain from the start

Default to the **plainest phrasing that stays precise**. "Writerly" LLM prose
gets bounced sentence-by-sentence by a careful PI; each bounce is a
comment→edit→resolve round-trip. Draft in this register from the first pass,
and run this **pre-submission self-check** on every section, caption, and
legend:

1. **Plain declaratives, not writerly contrasts.** Avoid *"not X but Y"*,
   *"larger than X rather than a correction of it"*, decorative em-dash
   appositives, and **elegant variation** (the same idea reworded for flavor —
   name it once, reuse the same term). Say the thing directly.
2. **Every term defined or plainly glossed on first use.** Jargon with no gloss
   ("wall-clock cost", "uniform-confidence set", "structural concordance")
   forces the reader to guess — give a plain phrase or a one-clause definition.
3. **No ambiguous quantity words.** "larger" / "higher" — of *what*? State
   exactly what varies: *more isoforms*, *more exons*, *longer CDS*, *higher
   BUSCO*. Not bare "larger".
4. **Introduce a concept before you invoke it.** Don't reference "the tiers"
   before the confidence-tier idea is defined. Definition precedes use.
5. **One topic per paragraph; no forward references or out-of-place asides.**
   Keep each genome's result in its own section; don't drop another genome's
   number mid-section, a data-availability note mid-analysis, or *"…is
   developed in the Discussion"* pointers. Reorder so the reader has what they
   need where they need it.
6. **Don't overuse a rhetorical word.** If "vetted" / "robust" / "leverage" /
   "comprehensive" appears many times, vary or cut it.
7. **No result-like numbers in Methods.** Methods describes the method; actual
   values/metrics go to Results. (See §1 + the `results_in_methods` lint.)

`lint_manuscript` (§4) now flags several of these deterministically —
`overused_word`, `vague_comparative`, forward-reference/writerly `style_tell`s,
and `results_in_methods` — but the judgment calls (jargon-without-gloss,
term-before-definition, one-topic-per-paragraph) are yours: run the checklist.

### 3. Say it once (de-duplication)

Each finding, definition, and background fact appears **once, in its home
section**. Legitimate cross-references RE-USE by pointing, not by repeating:
the Abstract *summarizes* a result (rephrased, shorter) — it does not paste
the Results sentence; the Discussion *interprets* a result — it does not
restate it. If you catch yourself writing the same sentence twice, delete
one and cross-reference.

### 4. Hard done-gate — `lint_manuscript`

Before marking sections `complete` (and before `/paper-export`), run:

```
mcp__co_scientist__lint_manuscript(slug)
```

It deterministically flags **duplication** (same sentence across sections),
**section leakage** (results/stats in Methods, procedure in Results), and
**style** (LLM-tell + writerly/forward-reference phrases, run-on sentences,
`vague_comparative` bare "larger/higher", `overused_word` repeated rhetorical
words). Treat it like the deck
layout lint: **a section isn't done until its warnings are resolved.** Fix
the offending sentences (each warning quotes the sentence + its section),
re-run until `summary.clean == true`, then report the clean result to the
user. If you leave any warning intentionally, say which and why.

## Citation Format

Inline DOIs: `{doi:10.1234/example}`. You can pre-add references via
`mcp__co_scientist__add_reference(slug, citation_key=..., doi=..., title=..., authors=[...])`
either before or after the prose — `prepare_export` will check for
unresolved citations at export time.

## Formatting

Section bodies are GitHub-flavored markdown rendered in the dashboard.

**Tables — line breaks inside a cell:** use `<br>`, never a real newline.
A markdown pipe table is one row per line, so an Enter/`\n` inside a cell
ends the row and truncates the content. The dashboard renderer honors
`<br>` (and `<br/>`).

```
| Trait        | Value         |
|--------------|---------------|
| Yield<br>(t/ha) | 3.2 ± 0.4   |
```

Wide tables scroll horizontally in the dashboard rather than squishing to
fit — don't hand-wrap columns to make them narrow.

## Status Transitions

Update section status as the work progresses:
- `pending` — placeholder, nothing written
- `in_progress` — actively drafting
- `draft` — first complete draft
- `complete` — content frozen, ready for review (only after
  `lint_manuscript` is clean for that section)

Don't skip stages — the dashboard surfaces `in_progress` to the human so
they know what you're actively editing.

## After Writing

Suggest the human pull up the dashboard at the project's Firebase URL to
read what you wrote and leave inline comments. The comments come back to
you next session via `count_open_user_comments` in the SessionStart banner.

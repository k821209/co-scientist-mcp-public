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
   *"larger than X rather than a correction of it"*, and **elegant variation**
   (the same idea reworded for flavor; name it once, reuse the same term). Say
   the thing directly.
1b. **Prefer commas / colons / parentheses over em-dashes (—).** Many reviewers
   read them as informal, and paired em-dash asides make long sentences hard to
   parse. A single em-dash → a comma (or a colon when it introduces a
   list/definition); a paired aside → parentheses. `lint_manuscript` flags each
   `—` (`em_dash`).
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

### 2c. Write from the reader's context, not yours

You remember the whole analysis; the reader has read the paper once. At FIRST
use, every term, symbol and threshold must carry what it means, the scale or
baseline that makes a value interpretable, and which method/arm it belongs to
when more than one exists ("λ" only where it is defined). A number without a
scale is not information: "0.904 on a 0–1 scale where 1 means the same
partition", not "0.904". This is separate from §2b: plain phrasing does not
supply a missing premise. And when trimming for length, cut claims — never the
clause that lets a reader check one.

### 2d. Never write from inside the authoring session

§2c is about premises the reader lacks. This is the opposite failure: writing
about work the reader has **no frame for at all**. A manuscript can fail both at
once, and one did.

For a revision the reader's frame is exactly **(what they received) → (what they
are receiving now)**. Anything whose frame is our working session is noise, and
worse, it reads as retracting something that never existed for them. Three shapes,
all of which shipped and were caught by the author, not by any check:

| don't write | why |
|---|---|
| "An earlier draft of this revision reported only 174 of them… we have dropped that collapse." | The reviewers saw the SUBMISSION. The intermediate existed only between you and the author. |
| "We considered reducing that list to one lead gene per megabase and decided against it." | A road not taken. If it was rejected there is nothing to report — this was the *fix* for the row above, and it is the same failure in a new costume. |
| "more than we expected", "on reflection", "we judged", "for readers who want the reduced view" | Narrates the authoring process, or hands the reader a choice you should have made. |

This is not merely unhelpful. Framed from inside the session, a removed panel was
described as having shown "the 285 accessions" — the panel the reviewers actually
saw was the 69-accession one. Insider framing produces factual errors about the
reader's own experience.

`lint_manuscript` flags this lexically as **`insider_context`**. Treat it as
advisory: not every hit is guilty ("we withdraw the original explanation" is fine,
because the reviewer read the original explanation). Weigh it highest on a
response letter or cover letter, where the reader's frame is narrowest and you
have the most session history to leak.

### 2d-bis. Make the OBJECT the subject, not the statistic

The single largest source of "말이 어렵다" corrections. Four in one session traced
to this habit, three of them on the same sentence:

| | |
|---|---|
| ✗ | "so a fragmented gene is tested with fewer accessions behind each category rather than penalised on average" |
| ✗ | "The chance adjustment is not biased against fragmented genes, in that their typical adjusted value is no lower than other genes'" |
| ✓ | "**Fragmentation does not lower the score a gene typically gets. It lowers the highest score a gene can get.**" |

Both rejects have an *estimator* as the grammatical subject and a *property of an
estimator* as the predicate ("is not biased against", "in expectation", "typical
adjusted value is no lower"). That register is precise and nearly unreadable, and
it is the default a model reaches for when describing a correction. Estimator
language belongs in **Methods**, where the estimator genuinely is the subject.
Everywhere else, the biological object acts: *Fragmentation lowers X.*

**State statistics as events.** "the top 5% reach 0.046 or above", not "the 95th
percentile is 0.046". And give magnitudes, not only ratios — "halves" without both
numbers leaves the reader no scale.

**Plain is not conversational.** Fixing the sentence above overshot into "the
number that **decides this**" / "does not **tell you** that", which was rejected
too. Two independent axes, and a sentence can pass one and fail the other:

- *concrete subject* — can the reader picture what is doing the acting?
- *declarative register* — no second person, no vague verb standing in for a
  technical relation, no tag clauses

`lint_manuscript` flags both sides: `estimator_voice` (outside Methods) and
`colloquial_register`. They ship together on purpose — correcting one by hand is
how you land in the other.

### 2d-ter. Scope a claim to the case it came from

A heading read *"the two tests are not equally demanding of 285 accessions"* and
our own text contradicted it three sentences later: another locus IS detected in
the same 285. The claim came from one case and was written as a general one.

- The claim sentence **names its case**: "*Detecting E2* asks more of 285
  accessions in one test than in the other."
- Say the link is specific: "the shortfall is specific to E2 rather than general".
- If there is a genuine generalisation, give it its own sentence — and check it
  actually covers the counterexample ("the cohort a gene-level test needs scales
  with that gene's allele-type count" covers both loci; the original did not).

### 2d-quater. Trimming a caption can delete the paper's method

Before cutting anything from a caption or legend, check whether the value exists
anywhere else. A caption can be the **sole carrier** of a parameter, and every
other lint flag here (`long`, `interpretive`, `bare_cross_reference`) invites
deletion.

This nearly shipped: a Figure 6 legend carried "projected … with **± 250 kb
padding**". It reads exactly like method detail whose home is Methods — but
Methods never stated it (it stated a *different* 100 kb constant, for a separate
upstream step), and the paper's headline number depended on it entirely:

| padding | candidates inside a QTL |
|---|---|
| 0 kb | 188/474 = 39.7% |
| 100 kb | 196/474 = 41.4% |
| **250 kb** | **213/474 = 44.9%** ← the manuscript's number |
| 1 Mb | 256/474 = 54.0% |

`lint_manuscript`'s sibling `lint_legends` now flags this as **`caption_only`**,
ranked above every other flag, with the action **RELOCATE, do not delete**.

Two rules follow:

- **A value that depends on a tunable parameter states the parameter AND how much
  the value moves with it.** "44.9% at ± 250 kb, 39.7% unpadded, 54.0% at ± 1 Mb"
  is one sentence and pre-empts "why 250 kb?" at review.
- **State the predicate**, not just the threshold. "Inside a QTL" has two equally
  natural readings — the gene's start point contained in the interval, or its span
  intersecting it. They disagree (one gene, 8 QTL vs 10), the headline percentage
  was identical either way, so no numeric check could ever catch it, and a
  reproducer is left guessing.

#### What belongs where

| Keep in the caption | Move to Methods | Move to Results/Discussion | Delete |
|---|---|---|---|
| panel letters and what each shows; visual encodings (colour, shape, line style, size); axis definitions; `n`; values that appear ONLY in the figure; a note that prevents misreading the panel ("an empty cell means no study reported a QTL there") | test names, correction procedures, software + versions, iteration/restart counts, thresholds, merge conventions, annotation-source IDs, and **any predicate a number depends on** | derived statistics the text already quotes; interpretation; generalisability caveats | only sentences duplicated near-verbatim from a body section — exactly what `body_duplication` enumerates |

Worked example, a table caption 200 → 66 words: the stage list, `52.1 ± 8.5 s`,
`~3.6× faster` and `~64× less RAM` all came out because **each is a cell in the
table itself**; the incremental-append argument came out because it is a
Discussion paragraph. Nothing was lost — because every token was verified present
elsewhere first, which is the check `caption_only` automates.

#### 2d-quinquies. A caption points at numbers; it does not reprint them

The most common padding is a caption walking the reader through values already in
front of them:

> Gene-Miner's all-isoform Complete (C) fraction rises where the RNA-seq captures
> alternative isoforms (rice 93.6% → 96.5%, Drosophila 96.5% → 98.9%, C. elegans
> 95.1% → 98.3%; soybean only 91.9% → 92.1%), whereas BRAKER3's barely changes.

Every one of those percentages is a cell in that same table. The caption has
become a worse-formatted copy of the table underneath it.

- **One headline value is good caption writing.** "Completeness reaches 96.5% for
  rice" earns its place. A walk-through of eight does not.
- **Replace the list with what to NOTICE.** The sentence above is trying to say
  "all-isoform gains track isoform richness; BRAKER3 is flat" — say that, and let
  the numbers stay in the table.
- **Figures are the worse offender**, because nothing structural stops it: a
  figure has no columns, so a caption can carry a whole mini-Results of numbers
  and still look like a caption.
- **Word count will not save you.** A numeric-dense caption can be short, so the
  `long` flag stays quiet.

`lint_legends` reports this as **`number_restatement`** (warn) and lists every
offending number in `duplicated_numbers` with its source (`own_cells` vs
`body_or_other_item`), so one editing pass clears the item. It never fires on the
same token as `caption_only`: a parameter you must relocate and a measurement you
should cut are different things, and the report will not ask you to do both.

#### 2d-sexies. Describe the panel; don't argue from it

The same failure in words rather than numbers. A legend says what the reader is
looking at. The moment it says what the reader should *conclude*, that sentence
belongs in Results.

| legend text | verdict |
|---|---|
| "Darker shading indicates higher coverage." | fine — that IS the legend's job |
| "The lower panel shows the same data on a log scale." | fine — describes the graphic |
| "In rice the models are **overwhelmingly larger** than the reference." | Results |
| "Gene-Miner **approaches** their ceiling and **matches or exceeds** BRAKER3." | Results |
| "The novel loci are **markedly lower**." | Results |
| "They are complete gene models, **as expected** for lineage-specific genes." | Results/Discussion |

The tell is not the comparative word — legends compare all the time — it is
**what the subject is**. When the subject is the graphic (shading, panel, bars,
axis), a comparison describes an encoding. When the subject is a result (the
models, the loci, the pipeline), it is a claim.

`lint_legends` flags these as **`interpretive`** and puts each offending sentence
in `interpretive_spans`. Comparisons in a sentence about the graphic are
deliberately not flagged. One such sentence is `info`; two or more is `warn`,
which is the signal that the legend has grown a mini-Results.

### 2e. Cite display items parenthetically

A figure or table is cited in parentheses, never woven into the sentence as a noun
phrase. `lint_manuscript` flags the prose form as `prose_cross_reference`.

| bad | good |
|---|---|
| "The resulting projection is Figure 4A." | "…using metric multidimensional scaling (MDS; Figure 4A)." |
| "Table 2 places these figures beside an LD-based route…" | "An LD-based route was timed on the same node (Table 2)." |
| "…records are provided in STable 1." | "…records are listed in the supplementary material (STable 1)." |

Multi-item parentheticals are fine and expected: `(Table 1, Figure 7B)`,
`(Figures 3A, 4, Table 1; SFigure 2)`.

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
**section leakage** (results/stats in Methods, procedure in Results, plus
`measurement_in_methods` — a measured size/time/memory/fold reported in Methods —
and `result_only_in_methods`, a number that appears in Methods and in a
figure/table but never in Results), **style** (LLM-tell + writerly/forward-reference
phrases, run-on sentences, `vague_comparative` bare "larger/higher",
`overused_word` repeated rhetorical words, `prose_cross_reference` — see below),
and **insider_context** (§2d). Treat it like the deck
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

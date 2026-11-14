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
3. Call `mcp__scivo__create_paper(title=..., journal=..., doc_type=...)`.
4. For a `paper`, the canonical 6 sections (abstract, introduction, methods,
   results, discussion, conclusion) are seeded automatically. For
   `report`/`other`, add sections yourself with markdown `##` headings in the
   body as you draft.
5. Suggest next steps: literature review, methods draft, etc.

### Working on an existing paper

1. Call `mcp__scivo__list_papers()` if the slug isn't provided.
2. Call `mcp__scivo__get_paper_state(slug)` to see the current
   state of all sections and the assembled manuscript.
3. For each section the user wants to write:
   - Ask any clarifying questions (target audience, key claims).
   - Draft the section content **per the Writing craft rules below**
     (section contracts, journal register, no duplication).
   - Call `mcp__scivo__update_section(slug, key, body=..., status='draft')`
     — for a section you are DRAFTING or rewriting whole. To change part of
     one that already has text, edit that part (`replace_in_section`, or one
     block via `section_blocks`): the author edits paragraphs in the
     dashboard, and re-sending the body overwrites what they typed since you
     read it.
4. After updating sections, run `mcp__scivo__lint_manuscript(slug)`,
   resolve every warning, then call `mcp__scivo__get_paper_state(slug)`
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
| **Title** | The most essential finding or its subject, in plain words | An adjective of merit ("novel", "comprehensive"); a word the reader must look up; the method's name where the result belongs |
| **Abstract** | 1–2 sentence background, aim, key result WITH the number, one takeaway | New info absent from the body; sentences copied verbatim from other sections |
| **Introduction** | Context → the gap/problem → this study's aim/hypothesis | Methods detail; results; discussion of your own findings |
| **Methods** | What you DID — materials, procedures, analyses — **past tense**, reproducible | **Any finding, statistic, p-value, or "we found/observed"**; interpretation |
| **Results** | What you FOUND — observations, numbers, stats, figure/table callouts | How-to/procedure ("using the X kit… per manufacturer"); interpretation/"why" |
| **Discussion** | Interpretation, comparison to prior work, mechanism, limitations | **New results/numbers not already in Results**; restating Results sentence-by-sentence |
| **Conclusion** | The single main claim + implication/next step | New data; a paragraph-length recap of Results |

Rule of thumb: **Methods = past-tense procedure, no findings. Results =
findings, no procedure. Discussion = meaning, no new data.**

### 2. Academic register (journal prose, not chat prose)

**Read the two files in this directory before you draft, and again before you
edit in response to a comment.** `REGISTER-BIO-AI.md` carries this field's
register from a worked exemplar. `REGISTER-LEAKS.md` carries what the author
actually corrects — the four leaks, ranked by frequency across every comment
ever written on AI-drafted prose here (818 comments, 653 edits, 59 papers).
The largest class by a factor of two is deletion of clauses that defend a
claim instead of reporting it, and the leak specific to revision is answering
a comment by appending the answer as a clause.

**For a biology or computational-biology journal, `REGISTER-BIO-AI.md`
comes first.** It carries the field's register from a worked
exemplar — tense, sentence shape, the terms that mean something else in
biology, decimal format, figure-title convention, and the display-item
budget. The rules below are generic; that file is what the field actually
prints. It exists because every rule below was loaded and followed and a
manuscript still came out in ML-workshop register.

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
- **Korean manuscripts** (보고서/국문 논문): the guide's "Prose for
  non-English audiences" applies (draft natively, not translated). Specific to
  a manuscript: academic register (`~하였다 / ~로 나타났다`); avoid
  `매우 중요한 역할을 한다`, `아무리 강조해도 지나치지 않다`, 완곡어 남발.

### 2a. You are drafting inside a coding harness. Its voice is not neutral.

This session's surroundings — the tool descriptions, the skills, the commit
messages, this file — are engineering prose. That register leaks into the
manuscript, and it leaks hardest into the sentences you are proudest of, because
a vivid metaphor feels like good writing while you are writing it.

The specific leak is **metaphor imported from software / ML / economics used for
a literal scientific statement**:

| Instead of | Write the literal thing |
|---|---|
| the two measures are **orthogonal** | the two measures were uncorrelated (r = 0.02) |
| this **buys** accuracy and **pays for** it in interpretability | accuracy improved; interpretability decreased |
| a **cheap** proxy / an **expensive** assay | a fast, low-cost proxy / a labour-intensive assay |
| the effect **surfaces** in the second cohort | the effect was also present in the second cohort |
| a **knob** to tune / **budget** for error | a parameter to adjust / the tolerated error |
| there is no **free lunch** | every method traded one property for another |

Korean drafts carry the same import: **직교한다 · 산다/판다 · 값싸다/비싸다 ·
표면화된다 · 여유(budget)**. Write 상관이 없었다 / 정확도는 올랐고 해석력은
떨어졌다 / 비용이 낮은.

**The test is not "is this word banned" — it is "is this word native HERE."**
`orthogonal` is ordinary vocabulary in a machine-learning paper and a metaphor
the reader must decode in a plant-genomics one. The paper's own reference list
settles it: if none of the works you are citing use the word, you imported it.

**Why it is an error and not a taste dispute:** a metaphor names a quality where
the sentence owes a quantity. Griffies et al., *Elements of Style for Writing
Scientific Journal Articles* (NOAA/GFDL, for *Ocean Modelling*) uses this exact
case — "the simulation ran quickly and **cheaply**" — and its fix is not a
better adjective but the measurement: "required 1200 hours using 100 computer
processors." Ask *what is "cheap" here* and the replacement writes itself. The
same guide rules out **subjective or judgmental adjectives** ("a *simple* model"
— simple against what?) and **expressions of belief** ("we believe this result
to be true" → "we show through our analysis that…"), both of which are the same
move: an impression standing in for evidence.

Same leak, different shape: do not explain in an engineer's voice. *"The point
is…", "which is what makes this safe", "that is the whole feature"* are how a
code comment argues. A manuscript states the finding and its support.

One caution against over-correcting: **field-standard technical terms are not
jargon to remove.** GWAS, BLUP, transcript abundance, orthology — these are the
vocabulary your readers share, and replacing them with plain English makes the
paper vaguer, not clearer. The rule is directional: strip metaphor borrowed from
ANOTHER field, keep the terms native to this one.

### 2b. Clarity over eloquence — draft plain from the start

Default to the **plainest phrasing that stays precise**. "Writerly" LLM prose
gets bounced sentence-by-sentence by a careful PI; each bounce is a
comment→edit→resolve round-trip. Draft in this register from the first pass,
and run this **pre-submission self-check** on every section, caption, and
legend. Items 2 and 4 below (terms defined, definition before use) are the
ones a self-check cannot catch — you always know what your term means — so for
the abstract they are checked by a reader instead: `/cold-read`, in §4.

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
7b. **Keep the subject short — the verb within about twelve words.** A PI
   read lint-clean prose and said the reason it was hard to read was that the
   subjects were too long. Packing every qualification in front of the verb is
   the shortest way to make one sentence carry everything, which is why a
   model does it systematically; the reader holds all of it in mind until the
   verb arrives. Move the qualification behind the verb, or split — same
   length, different order:

   | before (24 words before *is confirmed*) | after |
   |---|---|
   | Structure whose introns were carried by a spliced-read junction in the libraries the catalogue was built from is confirmed in tissues it had never seen at 91.9%. | Where an intron was carried by a spliced-read junction in the libraries the catalogue was built from, it is confirmed in tissues the catalogue had never seen at 91.9%. |
   | Measuring recovery, structural concordance, boundary errors or the value of the confidence tiers requires a trusted annotation to measure against. | Recovery, concordance, boundary error and tier value can only be measured against a trusted annotation. |

   A leading adverbial closed by a comma ("Because it learns …, GeneMark-ETP
   detects …") is not a long subject. The `heavy_subject` lint counts the
   words before the main verb per clause, skipping verbs inside relative
   clauses; when it fires on a section repeatedly, the complaint is the
   cumulative load, not one sentence.

`lint_manuscript` (§4) now flags several of these deterministically —
`overused_word`, `vague_comparative`, `heavy_subject`, forward-reference/writerly
`style_tell`s, and `results_in_methods` — but the judgment calls (jargon-without-gloss,
term-before-definition, one-topic-per-paragraph) are yours: run the checklist.

### 2c. Write from the reader's context, not yours

The guide's "Write from the READER's context, not yours" applies in full (its
first-use audit and its two corollaries). It is separate from §2b: plain
phrasing does not supply a missing premise.

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

**A comparison is a case too: scope the claim to what the two sides SHARE.**
`project_guide()` → *Analysis provenance* names the slots that must match for
a comparison to be a comparison, and the two passes that check them. You
cannot run that check from inside: you chose those two numbers precisely
because they looked comparable from where you were standing. What you CAN do
from inside is write the claim so that a slot turning out wrong costs a clause
instead of the paper. A recorded case, both ways:

- *"This demonstrates that the treatment promotes flowering"* — dies whole the
  moment the denominator turns out to be germinated plants rather than sown
  seed. There is nowhere to retreat to.
- *"The proportion of flowering plants per seed sown was higher under the
  treatment"* — same evidence, and the same discovery changes 1.28-fold to
  another number and leaves the sentence standing.

Scope is the only thing that makes a late discovery cheap. Write the claim to
the shared slots and a mismatch narrows it; write past them and the mismatch
takes everything built on top.

### 2d-quater. Captions and legends — `CAPTIONS-LEGENDS.md`

Read it before writing or trimming ANY caption or legend, and whenever
`lint_legends` fires. The one rule that cannot wait for the file: **before
cutting anything from a caption, check that the value exists somewhere
else.** A caption can be the sole carrier of a parameter, and the lint's
flags all invite deletion.

### 2d-quater-ter. The title, the abstract and the cover letter — `EDITOR-FIRST-PAGE.md`

What an editor decides from before anyone reads the paper. Read it when the
title or the abstract is being finalised, when a cover letter is written, and
before the paper goes to a journal — the first time or after a rejection (it
covers what to do with earlier reviews, and suggesting reviewers). The one
rule that cannot wait for the file: **the letter says what the abstract has
no room for — why it matters beyond the field and where it stands against the
closest earlier work, named — and it agrees with the abstract on every
number.** Whether it does is a reader's question, not yours: the file names
the run.

### 2d-quater-bis. Korean: a line that stands alone — `KOREAN-STANDALONE-LINES.md`

Korean drops what the context restores. A title, a header, a table header, a
figure title stands with no sentence before it, so there is nothing to
restore from: keep who / what / about what inside the line. Read the file
when drafting Korean of that kind.

### 2d-quinque. Name the referent, name the measurement, state the fact here

"의미가 헷갈리는건 니가 대명사나 용어/은어를 막 쓰기 때문이거든" — a user, after a
long session. Three habits, each fluent to write and opaque to read:

| defect | ✗ | ✓ |
|---|---|---|
| **Deictic with no named referent** — 그것/거기서/this/that/it standing in for something the reader must reconstruct | "사전학습이 조성 이상을 담고 있고, 적응이 거기서 더 나아갑니다." / "the two are indistinguishable on the downstream task" | name the three numbers / name the task |
| **Coined term presented as field vocabulary** — a phrase that names a measurement, dressed as a concept | "그 종 데이터로 훈련하는 단계가 그 종의 일을 합니다." / "the interpretability floor", "the arm" | "벼 전사체로 훈련하면 벼 프로모터를 읽는 정확도가 올라갑니다." — use the measurement |
| **Forward or backward reference instead of the fact** | "이 사실이 뒤에서 중요해집니다" / "as noted above" | state the fact here; a section stands alone and a talk cannot flip back |

The English half of the first is worse than it looks: *it / this / that* as a
sentence subject reads fluent and passes every other check. `lint_manuscript`
flags the decidable cases as `unnamed_referent` (a Korean sentence opening on a
demonstrative that names nothing; an English one whose bare demonstrative
subject follows a sentence with two or more candidates) and `deferred_fact`.
The coined-term rule has no lint: `REGISTER-BIO-AI.md` §3 lists the words we
were caught on, but the rule underneath is *if the phrase names a measurement,
use the measurement* — and the author cannot check it on themselves, which is
why `/prose-review` §6 exists.

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
mcp__scivo__lint_manuscript(slug)
```

Its description lists the warning groups and the tri-state `clean`. **A
section isn't done until its warnings are resolved:** fix the quoted sentences,
re-run until `summary.clean == true`, then report the clean result to the user
with `summary.examined` — "clean" over 7 words is a different claim than
"clean" over 4,000. If you leave any warning intentionally, say which and why.

**Then, for the abstract: `/cold-read`.** `lint_manuscript` is clean on an
abstract that uses "condition" three times and defines it nowhere, because
every word is ordinary; the linter cannot know what a reader lacks. The cold
reader can, and the abstract is the one place a reader has no context at all.
Run it before the abstract is marked `complete`, and again after a rewrite.
Its findings arrive as `source='ai'` comments in the usual triage loop.

## Citation Format

The guide's "Citation format + hallucination check" has the `{doi:…}` /
`{cite:key}` tokens and `add_reference_by_doi`. Beyond it: never `[@key]` —
that is pandoc syntax, this system does not resolve it, and it reads as cited
on screen while exporting with no bibliography entry (`lint_manuscript` flags
it as `foreign_citation_syntax`). `add_reference` (typed by hand) is for a work
that HAS no DOI, with the details copied from the source in front of you;
never for one whose DOI you could look up. `prepare_export` checks for
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

Offer `/prose-review` on the finished draft. It reads the text as the journal's
copy-editor and files only register problems, with the replacement sentence —
the pass that catches what §2a describes when it did not hold while drafting.
Offer `/cold-read` on the whole manuscript if it has never had an outside
reader.

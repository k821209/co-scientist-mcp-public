---
name: prose-review
description: Read an already-written manuscript and comment ONLY where the prose does not read like a journal — imported metaphor, chat register, LLM tells, patch-note sentences left by revisions. Writes each finding as a Firestore review row (source='ai') with the replacement sentence. Use when the user says "the writing doesn't read like a paper", "문체가 논문 같지 않다", "check the writing", "does this sound like a journal".
---

# /prose-review

**Triggers:** "the writing doesn't sound like a paper," "문체가 이상하다,"
"이거 논문 문장 맞나," "check the register," "read it as an editor,"
"이 표현 저널에 안 맞는 것 같은데."

Reads a finished draft the way a copy-editor at the journal would, and comments
where the SENTENCE is wrong for the venue. Not what it claims — `/paper-review`
does that.

## What this skill is for, and what it must not become

Every writing rule this checks is already written down in `/paper-writing` §2,
§2a and §2b. **Read those first — they are the specification.** This skill is
the pass that applies them to prose that already exists, because the guidance
only ever ran while drafting, and most text in this system arrives some other
way: imported from a `.docx`, revised against a comment, or written by a session
that never opened the skill.

## Non-negotiable rules

1. **Every finding is a database row** — `add_review(..., source="ai",
   reviewer_name="AI prose editor")`. Markdown-only output does not reach the
   dashboard and `/paper-revision` never sees it.
2. **Every comment carries the REPLACEMENT sentence.** "This is too informal" is
   not actionable; the author now has to invent the fix that you already had in
   mind. Write: `현재: "…" → 제안: "…"`. A comment without a rewrite is not
   worth a round-trip.
3. **Run `lint_manuscript(slug)` FIRST and do not repeat it.** It already
   reports em-dashes, run-ons, vague comparatives, colloquial register,
   overused words, LLM tells, foreign citation syntax and insider context.
   Anything it caught is on its own rail; duplicating it means the author reads
   the same complaint twice from two places and starts skipping both.
4. **Comment, never edit.** Prose is the author's. Even an obvious fix goes in
   as a suggestion.
5. **Anchor to a verbatim span from the stored body** — the smallest phrase that
   carries the problem. Copy it out of `get_paper_state`, not from memory: an
   anchor that does not appear character-for-character resolves to nothing and
   the comment lands at the top of the section with no highlight.

## What to look for

### 1. Metaphor imported from another field

The one this exists for. See `/paper-writing` §2a for the list and the
replacements: *orthogonal* for uncorrelated, *buys / pays for / cheap /
expensive* for a trade-off, *surfaces*, *lands*, *knob*, *budget*, *no free
lunch*; in Korean 직교한다, 산다/판다, 값싸다, 표면화된다.

**The test is not a word list — it is whether the word is native to THIS
paper's field, and the paper's own references settle it.** Before flagging a
term, check `list_references(slug)`: `orthogonal` in a machine-learning paper
whose citations use it constantly is ordinary vocabulary and must not be
touched. The same word in a plant-genomics paper is a metaphor the reader has
to decode.

Say what the sentence owes instead: a metaphor names a quality where the
sentence owes a quantity, so the replacement is usually the measurement —
"ran cheaply" → "required 1200 CPU-hours".

### 2. Sentences left behind by a revision

Text that answers a reviewer instead of stating a finding: *"As noted, we now
clarify…"*, *"This has been revised to…"*, *"we have added"*. That is the
response letter's voice. The reader of the published paper never saw the
comment. Flag every one — they are invisible to the author, who remembers the
exchange.

### 3. Chat and engineering register

*"The point is…"*, *"which is what makes this safe"*, *"that is the whole
feature"*, *"basically"*, *"obviously"*, *"turns out"*. A code comment argues
this way; a manuscript states the finding and its support.

### 4. Register breaks INSIDE a paragraph

One patched sentence in a consistent paragraph — a tense shift, a synonym for a
term already named, a sudden first-person aside. Read paragraphs whole; this is
invisible sentence by sentence, which is why drafting checks miss it.

### 5. Elegant variation

The same thing called three names across a paper — "the model" / "our
framework" / "the pipeline". Name it once and reuse the name. Flag the paper's
worst offender, not every instance.

## Do NOT flag

- **Field-standard terms.** GWAS, BLUP, transcript abundance, orthology, F4.
  These are the readers' shared vocabulary. Stripping them makes the paper
  vaguer, and this is the over-correction that would make the skill harmful.
- **Anything `lint_manuscript` reported** (rule 3).
- **Claims, statistics, citations, structure.** `/paper-review`'s job. If you
  notice a real scientific problem, say so once in the summary and leave it —
  do not file it here, or the two rails' findings interleave and neither reads
  as a coherent review.
- **Korean manuscripts judged against English conventions.** Check §2's Korean
  register rules (`~하였다 / ~로 나타났다`, consistent endings) instead.

## Flow

1. `get_paper_state(slug)` — the stored bodies, which are what anchors match.
2. `lint_manuscript(slug)` — note every span it already flagged; those are off
   limits.
3. `list_references(slug)` — the field's own vocabulary, for the §1 test.
4. Read **section by section, paragraphs whole.** Not sentence by sentence: §4
   only exists at paragraph scale.
5. File each finding with `add_review`, `severity="suggestion"` by default
   (`minor` when the sentence would actually confuse a reader, never `major` —
   register is not a reason to reject a paper).
6. Report the count per section and the single change that would improve the
   manuscript most.

## Budget: at most ~15 comments

A pass that leaves eighty comments is one the author closes without reading, and
it will contain your weakest calls alongside your strongest. Rank, keep the top
findings, and say in the summary how many you set aside and why. **Silence is a
valid result** — a draft written after `/paper-writing` §2a may genuinely have
nothing worth flagging, and inventing findings to look useful teaches the author
to ignore this skill.

## After

`/paper-revision` picks these up like any other open comment. Warn the user
before they run it that a register fix is exactly where a NEW register break
gets introduced (`/paper-revision`'s own section on this), so re-read the
paragraph after each edit.

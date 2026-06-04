---
name: journal-requirements
description: Capture a target journal's submission requirements for a paper type (Article, Short Communication, Letter, Review, …) — word limits, figure/table caps, structured-abstract rules, required sections — and check the manuscript against them. Use when the user names a target journal + paper type, asks "what are the limits for journal X", or "is this within the journal's requirements".
---

# /journal-requirements

**Triggers:** "we're submitting to Nature Comms as a short
communication," "set the journal requirements," "what's the word limit
for journal X," "is the abstract within the limit," "check the journal
requirements."

## What it does

A journal's rules depend on the **paper type** — an Article and a Short
Communication at the same journal have different word limits, figure
caps, and abstract rules. This skill captures that spec on the paper
and checks the manuscript against it.

Division of labour:
- **You (the agent)** — read the journal's *current* author guidelines
  for the chosen paper type and fill the structured fields. This is the
  whole sync strategy: nothing is pre-archived, so reading the live
  guidelines now keeps the spec current.
- **MCP `check_requirements`** — deterministic measurement: counts
  words / figures / tables / references and compares to the limits. It
  does NOT judge the soft rules — that's you.

## Flow

### 1. Resolve paper + journal + paper type

- Which paper (slug)? If unclear, `list_papers()`.
- Which journal? Use `paper.journal` if set; otherwise ask.
- Which **paper type**? Ask explicitly — "Article", "Short
  Communication", "Letter", "Review", "Brief Communication",
  "Perspective", etc. The limits are meaningless without it.

### 2. Get the journal's guidelines — YOUR job

You need the journal's author-instructions for that paper type. Two
ways, in order of preference:

1. **Ask the user to paste** the relevant guidelines text. Most
   reliable — they may have the journal's submission page open.
2. **WebFetch** the journal's "Instructions for Authors" /
   "Author Guidelines" page. Confirm the URL with the user first.
   Read the section for the specific paper type.

Always read the *type-specific* numbers. Journals list a table like
"Article: 5000 words, 8 display items; Letter: 1500 words, 3 display
items." Pick the row for the chosen type.

### 3. Record the spec

```
mcp__co_scientist__set_paper_requirements(
  slug,
  paper_type="Short Communication",
  abstract_max_words=150,
  abstract_structured=false,
  main_text_max_words=2000,
  max_figures=4,
  max_tables=null,
  max_display_items=4,
  max_references=30,
  required_sections=["abstract","introduction","methods","results"],
  notes="Methods may go after Discussion. Cover letter required.",
  source="https://journal.example.org/author-guidelines",
)
```

Rules:
- **Never invent a limit.** If the guidelines state no abstract limit,
  leave `abstract_max_words` null. A null means "no stated limit", not
  zero.
- `required_sections` uses the canonical keys: `abstract`,
  `introduction`, `methods`, `results`, `discussion`, `conclusion`.
- Anything that doesn't fit a structured field goes in `notes` verbatim
  — section-order rules, cover-letter/ORCID requirements, "no
  subheadings", colour-figure fees, etc. You will re-read `notes` every
  session, so keep them concrete.
- `source` = the guidelines URL, so the spec can be re-verified later.

### 4. Check the manuscript

```
result = mcp__co_scientist__check_requirements(slug)
```

Returns `{configured, requirements, metrics, checks, violations, ok}`.
Each entry in `checks` is a deterministic pass/fail (`abstract_words`,
`main_text_words`, `figures`, `tables`, `display_items`, `references`,
`required_sections`).

### 5. Report + act on the soft rules

Tell the user the deterministic result — e.g. "Abstract 178 / 150
words — 28 over. Figures 5 / 4 — one too many." For each violation,
offer a concrete fix (trim the abstract, merge two figures, cut
references).

Then handle what the check **can't** measure — read `requirements`
yourself:
- `abstract_structured: true` → verify the abstract actually uses the
  journal's structured format (Background / Methods / Results /
  Conclusions or the journal's labels).
- `notes` → check each rule by hand and flag anything the manuscript
  violates.

## How this interacts with export

`prepare_export` automatically calls `check_requirements` and includes
`requirements_check` in its bundle, with a summary line in `warnings`.
So `/paper-export` surfaces requirement violations at submission time
even if this skill wasn't run recently — but running it *first* is
better, because it's much cheaper to fix a 200-word overrun while
writing than at export.

## When to re-run

Journal guidelines change. If `requirements.set_at` is old, or the user
switches paper type or target journal, re-run this skill — re-read the
live guidelines and call `set_paper_requirements` again. The stored
spec is a cache of what the guidelines said *then*, not a contract.

## Rules

- **Read the live guidelines** — never fill the spec from memory of a
  journal's rules; they change and vary by type.
- **Never invent limits** — null means "no stated limit".
- **Surface every violation** from `check_requirements`, and every
  hand-checked `notes` rule the manuscript breaks.
- The MCP measures; you judge. Don't ask the MCP to decide whether an
  abstract is "structured enough".

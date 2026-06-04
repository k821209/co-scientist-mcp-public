---
name: literature-review
description: Search the literature on a topic, surface candidate papers, and (optionally) register them as references on a paper. Use when the user says "literature review," "find papers on X," "what's been done about Y," "add references for Z," or wants a synthesis of prior work.
---

# /literature-review

**Triggers:** "review the literature on …", "find papers about …",
"what's been published on …", "add references for X", "I need citations
for the introduction", "look up Smith 2024 on …".

## Inputs the skill asks for (in priority order)

1. **Topic** (required) — the search query.
2. **Paper slug** (optional) — if provided, found refs go into that
   paper's `references/` collection via `add_reference_by_doi`. If
   omitted, the skill produces a synthesis but doesn't write to
   Firestore.
3. **Year window** (optional) — e.g., "2022 onwards" → `year_from=2022`.
4. **How many** (optional, default 10) — soft cap. Multiple narrower
   searches usually beat one broad one.

## Flow

### 1. Decide search strategy

For a single topic, run 2–3 progressively-narrower queries via
`mcp__co_scientist__search_works(query, limit=…, year_from=…)`:

- **Broad** ("plant pangenome") for landscape understanding
- **Narrow** ("Arabidopsis pangenome 27 accessions") for specifics
- **Recent reviews** (`"<topic> review"` filter, year_from = current
  year − 3) to find synthesis papers

`search_works` hits CrossRef. Each result has `title`, `authors`,
`journal`, `year`, `subjects`, `abstract`, `doi`, `url`. No Firestore
writes happen.

### 2. Show candidates to the user

Present a numbered list with title / authors / year / journal / one-line
abstract snippet (or "no abstract on CrossRef"). Mark obvious
duplicates of already-registered references — call
`mcp__co_scientist__list_references(slug)` first to know what's there.

Format suggestion:

```
1. [2024] Smith J et al. — Plant pangenomes at scale
   Nature Genetics. doi:10.1038/...
   "We assemble 35 reference-quality genomes..."  ← abstract preview
```

### 3. Get the user's pick

Ask which they want to register. Accept:

- A list of numbers ("1, 3, 5")
- "all" (register everything)
- "none" (just give me the synthesis — skip step 4)

### 4. Register selected refs

For each picked candidate:

```
mcp__co_scientist__add_reference_by_doi(slug, doi=…)
```

The tool:
- Re-fetches CrossRef with the DOI (definitive metadata)
- Refuses if CrossRef returns 404 (won't happen here since we found
  them via CrossRef, but the guard is harmless)
- Auto-derives citation_key like `smith2024`
- Returns the saved reference doc

Collect any failures and report at the end.

### 5. Synthesis (always do)

Write a structured synthesis using only the registered refs (or the
shown candidates if no slug was given):

```
## What we know about <topic>

<broad framing — 2–3 sentences>

### Methodological approaches
<grouping of papers by approach>

### Recent advances (2024–2026)
<focus on what's new>

### Gaps
<what hasn't been addressed>

### References cited above
[smith2024] Smith J et al, Nature Genetics 2024. doi:10.1038/...
[chen2025] Chen Y et al, Genome Biology 2025. doi:10.1186/...
```

Inline citations use `{doi:10.…}` markers so the manuscript pipeline
picks them up. Don't invent DOIs — only use DOIs that came back from
`search_works`.

## Safety rules

- **NEVER call `add_reference` directly** (the manual one). Always use
  `add_reference_by_doi` so CrossRef metadata is authoritative.
- **NEVER invent DOIs** in the synthesis. Every `{doi:…}` you write
  must be one CrossRef returned during the search this session.
- **NEVER write a synthesis without surfacing candidates first** — the
  user should approve which papers go into the manuscript before any
  Firestore writes happen.
- **CHECK existing references** via `list_references(slug)` before
  registering — duplicate DOIs are auto-rejected by the MCP, but
  showing the user what's already there saves a round-trip.

## After registering

Tell the user:

- N refs added.
- The dashboard's References card will show them with two ribbons
  (✓ DOI / ? Context). Context verification happens via
  `validate_references(slug)` — suggest running it once the inline
  citations are in place.

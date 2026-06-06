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
   - Draft the section content.
   - Call `mcp__co_scientist__update_section(slug, key, body=..., status='draft')`.
4. After updating sections, call `mcp__co_scientist__get_paper_state(slug)`
   again and show the user a summary of what changed.

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
- `complete` — content frozen, ready for review

Don't skip stages — the dashboard surfaces `in_progress` to the human so
they know what you're actively editing.

## After Writing

Suggest the human pull up the dashboard at the project's Firebase URL to
read what you wrote and leave inline comments. The comments come back to
you next session via `count_open_user_comments` in the SessionStart banner.

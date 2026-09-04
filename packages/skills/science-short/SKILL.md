---
name: science-short
description: Produce a fact-checked science Short with real DOI-verified references — research (2-source) → fact-check → reference management in co-scientist → self-drawn graphics + narration → auto-built reference card + description citations. Use when the user says "make a science short about X," "explain this paper as a Short," "science explainer video with sources."
---

# /science-short

> **Video tools missing?** The video/YouTube tool family registers only on
> machines that do video work (a YouTube token exists, or
> `CO_SCIENTIST_ENABLE_VIDEO=1` in the MCP env). If `mcp__co_scientist__add_video`
> / `youtube_*` are absent, add that env var to `.mcp.json` and restart the
> session — needed once per fresh machine; after `youtube_connect` the token file
> auto-enables it.

**Triggers:** "make a science Short about …," "explain this study as a Short,"
"science explainer with references." Builds on `/news-short` (text → vertical
Short) but adds a **rigorous reference pipeline**: every on-screen and
description citation comes from a **DOI-verified** record in the co-scientist
reference store — never hand-typed (a typo is a factual error).

Requires `vh` installed (see `/video-harness`), plus `edge-tts` for narration.

## Hard rules

1. **No hand-typed citations.** Every reference is added via
   `add_reference_by_doi` (CrossRef-verified). Hallucinated DOIs 404 and are
   refused. Never paste an author/journal/DOI you typed from memory.
2. **Two independent sources** for every factual claim; prefer peer-reviewed
   primary literature. Exclude marketing / clinic blogs. ([[factcheck-discipline]])
3. **Verify the risky claims against the primary paper** (WebFetch / PMC), not a
   single review. (Real saves: reversed a "defibrotide suppresses angiogenesis"
   claim; flagged an unresolved in-vitro-only result.)
4. **Copyright-safe visuals only** — self-drawn graphic cards (PIL) + neural TTS.
   No copyrighted clips/BGM unless rights-safe.
5. **Medical topics:** include a "의학 정보 · 의료 조언 아님" disclaimer on the
   reference card and in the description.

## Flow

### 1. Research + fact-check
Gather claims from ≥2 independent sources; for any flagged number/claim, open the
primary paper and confirm. Keep a claim → source map.

### 2. Reference management (co-scientist — the citation source of truth)
Use a per-project references library paper (e.g. `doc_type="other"`,
slug like `aivo-shorts-references`) that accumulates every short's citations:

```
search_works("<title or topic>")                       # CrossRef candidates
verify_doi("<doi>")                                     # 404 = hallucination; abstract re-confirms the fact
add_reference_by_doi(slug="<refs-library>", doi="<doi>",
                     cited_in=["<short-id>"])           # canonical record; citation_key auto,
                                                        # journal_short captured from CrossRef
```

Tag each reference with `cited_in=["<short-id>"]` so a short can later pull
exactly the works it cited.

### 3. Video production
Self-drawn graphic cards (PIL `render_*.py`, zero copyright) + narration via
`news.build_short(script, shots, ...)`. Map every spoken sentence to a frame.

**Keep the spoken script and the on-screen text separate.** edge-tts mangles
mixed alphanumeric IDs (`SN 2024afav`) and mis-chunks big Arabic figures in
Korean (`13조 1700억` → "일 ,삼조…"). In the SPOKEN script spell amounts, years,
and units ≥ 10,000 out in Hangul ("십삼조 천칠백억 원", "삼십오 기가와트"); keep
the digits on the card. `vh.qc.narration_match` folds Korean numerals toward
digits before scoring, so following this costs no ratio.

### 4. Reference card + description — auto-filled from the store
Pull the short's cited works and hand them straight to `vh.refs_card` (input
shape == the reference dicts the store returns):

```python
from vh.refs_card import build_refs_card, format_description

refs = mcp__co_scientist__list_references(slug="<refs-library>", cited_in="<short-id>")
build_refs_card(refs, "gfx/g_refs.png")     # on-screen 참고문헌 card (deep-dive theme)
description_block = format_description(refs) # full bibliography + DOIs for the video description
```

`refs_card` abbreviates journals from each ref's `journal_short`
(CrossRef short-container-title) and formats authors as `Surname Initials`.

### 5. Verify + upload
Frame↔sentence mapping, audio levels (mean ≈ -20 dB / max < 0), pronunciation
check (spell abbreviations in Hangul for the TTS). Then `add_video` →
`youtube_upload(privacy="unlisted")   # public ONLY after the user says so — /video-publish §3` with the citation block in the description.

## Related
`[[shorts-reference-management]]`, `[[factcheck-discipline]]`. Same lineage as
`/news-short`, `build_rank_race`, and `vh.style_gallery`.

## Assembly

Mixed graphics + quoted clips go through `vh.steps.beats.build_beat_short`
(see "3c" in `/video-harness`): one beat per narration unit, audio-led timing,
blur-pad reframing, per-source pre-crop, credit burned on every quoted frame.
Draw the explainer cards with `vh.cardkit` — its `rule()` guard fails the build
rather than shipping a divider line through a number — and verify with
`vh.qc.contact_sheet` (read it) + `vh.qc.narration_match` (≥0.93).

# Concept without a preset

_Part of `/paper-deck`. Read from `SKILL.md` when the user declines the theme gallery and you write the concept yourself — the palette, the type scale, and the fonts for a deck whose body text is Korean, Japanese or Chinese._

**B. Without theme**: invent your own concept. Spell out:

```
mcp__scivo__update_deck(
  slug, deck_id,
  concept="""
    Palette:
      bg: #fafaf7  surface: #ffffff  text: #1a1a1a  accent: #b58900
      muted: #6c757d  secondary: #2e7d32  highlight: #ee5500
    Typography:
      # English-only audience: Inter is fine. For ANY deck whose audience
      # is Korean / Japanese / Chinese (or whose body text mixes scripts),
      # use the matching Noto Sans CJK family — its Latin glyphs are co-
      # designed to share metrics with the CJK script. Pretendard's Latin
      # is taller / heavier than its Hangul and creates a visible seam in
      # mixed-script body text (todo 008 §B).
      #   Korean   audience: display: Noto Sans CJK KR  body: Noto Sans CJK KR
      #   Japanese audience: display: Noto Sans JP  body: Noto Sans JP
      #   Chinese  audience: display: Noto Sans SC  body: Noto Sans SC
      display: Inter Bold     body: Inter Regular     mono: Noto Sans Mono CJK KR
    Type scale:
      # legacy keys (still honored)
      title: 32  head: 26  body: 20  line_spacing: 1.22
      hybrid_body: 18  hybrid_head: 22  cover_title: 40  caption: 12
      # semantic role keys (canonical — prefer these in new code; todo 004 §E)
      display_chapter: 56  display_cover: 48  display_hero: 44
      headline_section: 28  title_slide: 32
      body_large: 22  body_standard: 20  body_small: 16
      label_tag: 12  label_caption: 12  scale_ratio: 1.25
    Motif:
      a single thin horizontal rule under each title;
      a recurring small icon (#b58900) marking the figure-of-merit line
    Design language:
      Grid: 12 columns, 8pt vertical rhythm, Inches(0.6) side margins.
      Whitespace: >= 25% of each slide reads as empty — leave breathing room.
      Max 4 distinct type sizes per slide; type sizes only from `type_scale`.
      Max 3 colors per slide: accent + foreground + one neutral.
      Visual storytelling: every section opener (Era I/II/III) uses a
        chapter-divider pattern distinct from interior slides.
      Iconography: leave room for accent icons (filed for follow-up,
        todo 004 §C); for now use accent-colored shapes as visual anchors.
    # Arc is the narrative spine YOU choose for THIS talk. Don't copy
    # the line below — derive it from the paper. Example arcs below;
    # remix freely.
    #   "question → data → answer → caveat → next"      (lab seminar)
    #   "why → what → how → who → when → take-home"     (proposal pitch)
    #   "context → finding → mechanism → caveat → so-what"  (single paper)
    Arc:
      [the arc that fits THIS paper / talk; pick one or write your own]
  """,
)
```

The `Type scale:` block is **optional** — unspecified keys fall back to
defaults (title 32 / head 26 / body 20 / line_spacing 1.22 / cover 40).
Override any of them per deck:
- **Smaller body** (16–18pt) when slides are dense and projected close.
- **Larger title** (36–40pt) when the audience is at the back of a room.
- **Tighter line_spacing** (1.1–1.15) for code-heavy slides.

Avoid going below 14pt — the export's auto-shrink (TEXT_TO_SHAPE) will
already step down when individual slides overrun.

**Mixed-script typography** (todo 008 §B). When the deck's body text
mixes Latin and CJK in the same paragraph (typical for Korean academic
talks that use English jargon like "BLUP", "GWAS", "MCP"), the
**Latin glyphs need to share metrics with the CJK script** or the two
read as collaged from different fonts. Google's **Noto Sans** pan-CJK
families do this by design — Noto Sans CJK KR / JP / SC ship Latin
glyphs co-designed with the matching Hangul / Kana / Hanzi. Pretendard
and Inter look great in isolation but their Latin glyphs are taller
and heavier than the Hangul they sit next to, so "MCP가 다리" reads
with a visible seam between "MCP" and "가". The default for any non-
English audience should be the matching Noto Sans family.

The `Design language:` block is the deck's **design constitution** —
free-text rules every slide answers to (todo 004 §G). Not parsed by
the renderer; it's a contract you write to yourself as the slide
author. When you draft each slide's `code`, check it against this
block. Defaults to use if you don't write one:
- 12-column grid, 8pt vertical rhythm
- ≥ 25% whitespace per slide
- ≤ 4 type sizes, ≤ 3 colors per slide
- Section openers use a distinct (chapter-divider) layout from
  interior slides

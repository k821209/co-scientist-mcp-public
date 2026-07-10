---
name: news-short
description: Turn a news story or text (no source video) into a vertical news Short — script → free neural TTS → Ken-Burns image montage → burned captions → register in the Video tab. Use when the user says "make a news short about X," "turn this article into a Short," "make a briefing video."
---

# /news-short

**Triggers:** "make a news Short about …," "turn this article into a vertical
video," "daily news briefing video." Unlike `/video-harness` (edits an existing
recording), this **synthesizes** a Short from text — there is no source footage.

Requires `vh` installed (see `/video-harness`) plus **`edge-tts`**
(`pip install edge-tts`, needs network) for the voiceover.

## Why edge-tts (not Kokoro)

Kokoro (`vh.steps.dub`) has **no Korean voice**. For Korean (and other
languages Kokoro lacks) use `news.edge_tts_speak` — free MS Edge neural TTS.

## Caption accuracy (the important part)

edge-tts Korean emits no word boundaries, so caption timing comes from
**re-transcribing the generated audio with Whisper**. But free transcription
mis-hears numbers / homophones (e.g. "정유 4사" → "정유사사"). The fix:

```python
from vh.steps import news
from vh.steps.transcribe import transcribe
words = news.align_to_script(transcribe(wav, language="ko"), script)
```

`align_to_script` transcribes **without a prompt** (complete, no mid-audio
truncation), then difflib-aligns tokens to your script — words come from the
**script** (correct), timing from Whisper (accurate), at **any length**.
(`transcribe(wav, prompt=script)` only helps on short clips and truncates long
ones — use it as a fallback for short clips only.)

## Assembly

1. **Fact-check** with WebSearch / WebFetch; capture the **source + article
   publish date**. Write the script with accurate figures. **Keep two texts
   separate:** the *spoken* script and the *on-screen* text. Do NOT put mixed
   alphanumeric IDs / species codes (e.g. `SN 2024afav`) in the spoken script —
   edge-tts mangles them; say them in words or omit, and show the exact form on
   screen only. (`align_to_script` pulls caption text from the script, so the
   on-screen wording stays exact.)
2. **Images** for the top band. The band is ~square (**1080×1056**) but
   `generate_image` returns **16:9** (1536×1024), center-cropped (~68% of the
   width survives) — so **put "centered composition, subject centered, headroom"
   in the prompt**, or the subject gets cropped off.
   - real photos — `curl` from the article (respect the source / fair-use
     excerpt); `add_asset(local_path)` to track them.
   - AI — `generate_image(prompt=…, aspect_ratio="16:9", apply_style=False)`
     **with no `slug`** → a project-scoped asset (no dummy paper needed).
   Then **`get_asset(id_or_filename, dest_path)`** to pull each image to a local
   file.
3. **Assemble in one call** — `news.build_short` does VO → captions → the
   sentence→image band → 9:16 compose (headline, eyebrow, source·date line, AI
   ribbon, optional disclosure, end card, burned captions) → mux:
   ```python
   from vh.steps import news
   news.build_short(
       script, shots, out="out/short.mp4",
       headline="…\\N…", eyebrow="과학 뉴스",
       source="출처: … (2026.03.11)",
       ribbon="AI 생성 이미지",   # REQUIRED when images are AI-generated (see below)
       disclosure="…",          # optional conflict-of-interest footnote
       badge="…", card="AIVO", card_sub="…")
   ```
   - **Provenance (top-right) — you must choose:** `ribbon` is a *claim* and
     defaults to **None** (asserts nothing). For **AI images** you MUST pass
     `ribbon="AI 생성 이미지"` (the guardrail). For **real photos**, don't set
     ribbon — instead give each shot its credit: `shots=[(anchor, image,
     credit), …]` (e.g. `"사진 · Reuters"`); adjacent equal credits merge.
     Never leave AI images unlabeled, and never let the AI ribbon sit over a
     real press photo (it reads as "this photo was faked").
   - `shots = [(anchor, image_path[, credit]), …]` — one per sentence/clause; `anchor` is
     a phrase near the sentence start. Matching is **whitespace-insensitive and
     spans tokens**, so a Korean multi-word anchor (e.g. `"이 속도를"`) still
     matches even when align splits it; a miss raises with the nearby tokens.
     Same token in two sentences → list it twice, matched in order.
   - Keep enough distinct stills: an image reused across `> max_repeat` (2)
     sentences raises. Long sentences auto-split into ≤3.6 s cuts.
   - This replaces the old ~180-line hand-assembly. Do **not** use
     `compose_summary` here (it asplits a non-existent audio track and snaps
     segments, desyncing captions).
4. **Register + publish:** `add_video(..., aspect_ratio="9:16")` →
   `/video-publish` (news defaults to **unlisted**).

**Briefing compilation:** intro / divider / outro cards + concat the segments.

## Variant: clip-quotation shorts (short YouTube clips + our VO)

For a topic where short **video** quotations beat stills (e.g. an artist
feature), the band is a concat of a few seconds each from source clips instead
of Ken-Burns stills — same VO/captions/overlay pipeline, one call:
```python
news.fetch_clip(url, start="1:12", dur=6.0, dst="raw/s01.mp4")   # per clip
news.build_clip_short(
    script, shots, out="out/clip.mp4",
    headline="…", eyebrow="아이돌 특집", source="영상 출처: … (YouTube · 공식)",
    badge="이름 · 2006 · …",                # optional info chip
    disclosure="…")                        # optional (e.g. corporate/idol COI)
# shots = [(anchor, clip_path, is_vlog, credit), …]
```
- `fetch_clip` downloads **video-only** (`-f bv`, no soundtrack → the quotation
  doesn't reuse the copyrighted audio; our VO carries it) via yt-dlp with
  `--download-sections` + `--ffmpeg-location` (ffmpeg is often off PATH).
- `is_vlog=True` crops the bottom ~18% first (drop the clip's own burned-in
  captions) before reframing; `credit` shows top-right (adjacent equal credits
  merge). Clips are cover-cropped to the band and trimmed to each sentence span.
- **Source safety (required):** quote only **safe-tier** channels — the official
  label channel + members' official personal channels — for news/critique;
  keep an on-screen credit per clip + the bottom source line. Content-ID claims
  are still possible; yt-dlp downloading is a YouTube-ToS grey area — surface
  this to the user.
- **Verify every downloaded segment by eye** (wrong member / b-roll / a title
  card baked into the frame → re-pick the section).

## Guardrails (non-negotiable for news)
- Fact-check every claim; show **source + publish date** on screen.
- **Disclose AI images** on screen. YouTube's "altered/synthetic content"
  disclosure is set in **Studio** (the Data API doesn't reliably set it), so
  tell the user to toggle it there after upload.
- Real photos: stay within citation/fair-use scope and attribute.

### Real people (idols / celebrities)
When the subject is a real person, images/clips carry portrait-rights + Content-ID
risk — be conservative:
- **Never AI-generate a real person's face** (portrait rights + a false image).
- Use only the **label's official press/promo images** (a news photo credited
  "provided by <agency>" is the cleanest source) and **safe-tier video** (official
  label channel + members' official personal channels).
- **Always show provenance** on screen: top-right "사진 · <agency>" / clip credit,
  bottom "출처: <outlets> (연월)".
- **Verify every image/frame by eye** — related-article thumbnails routinely mix
  in a DIFFERENT celebrity; confirm identity before using.
- Cover **verifiable public facts/achievements only** — no private life,
  speculation, or controversy.

### Originality (YouTube policy)
YouTube limits **mass-published near-identical / AI-generated** videos, and this
skill makes churning easy (template + AI images + TTS). Keep **per-video
originality**: your own written script, primary-source fact-check, on-screen
attribution — don't crank out near-duplicate clips. Default privacy
**unlisted**; let the user review before going public. (Publishing goes through
`/video-publish` — see its note on brand-new Google accounts.)

Exact signatures live in the `vh` repo (`vh/steps/news.py`); this skill encodes
the workflow + provenance rules.

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

**Non-Korean shorts:** pass `voice` **and** `lang` together (they must match) —
e.g. `build_short(..., voice="en-US-AriaNeural", lang="en")`. Both builders
default to Korean (`voice="ko-KR-SunHiNeural"`, `lang="ko"`); `lang` sets the
alignment-transcription language, so leaving it "ko" for an English VO silently
drifts the captions/cuts.

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
2. **Images** for the top band — **match the imagery to the topic:**
   - **Conceptual** stories (mechanisms, policy) → abstract/metaphoric **AI art**
     works well.
   - **Date-, number-, or object-driven** stories (holidays, charts, schedules)
     → AI metaphors read as noise (users literally complained "너무 추상적",
     "여기 세로줄 5개가 뭐지"). **Render exact graphics** instead (PIL / matplotlib:
     a real calendar with the right weekday, a real timeline) and let the artwork
     carry the fact. This also makes it your **own graphic** for provenance.
   - **real photos** → `curl` from the article (fair-use excerpt);
     `add_asset(local_path)` to track.
   - **AI** → `generate_image(prompt=…, aspect_ratio="16:9", apply_style=False)`
     **with no `slug`** → a project-scoped asset (no dummy paper).

   The band is ~square (**1080×1056**) but `generate_image` returns **16:9**
   (~68% of the width survives the center-crop) — put **"centered composition,
   subject centered, headroom"** in the prompt. Then **`get_asset(id, dest)`** to
   pull each image to a local file.
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
- **Search summaries are NOT sources.** `WebSearch` snippets paraphrase, misread
  page metadata, and invent causal links. Before a claim reaches the script,
  `WebFetch` the primary document (or the outlet's own article) and confirm the
  exact wording. If it 403s, find another primary source — never fall back to the
  snippet. (Real near-misses: a fabricated "재계 요구", an invented cause-effect,
  a mis-dated approval — all from trusting summaries.)
- **Two-source rule.** A number/date reaches the script only if two independent
  sources agree. If they conflict, drop it or degrade to a qualitative phrase
  ("후반 막판", "지난 6월") — never split the difference. Note what you dropped
  in the video description.
- **Graphics you generate are claims too.** If a rendered image asserts a date,
  weekday, count, or ordering, verify it programmatically (`datetime`/`calendar`)
  against ground truth before shipping — a hardcoded index is as wrong as a
  hallucinated one.
- Show **source + publish date** on screen.
- **Provenance is three-way** — AI-generated / real photo / your own rendered
  graphic — stated per shot (`shots=[(anchor, image, credit)]`): AI → `ribbon="AI
  생성 이미지"`; real photo → `credit="사진 · <source>"`; own graphic → e.g.
  `"그래픽 · AIVO"`. A short with **no** AI images must not carry an AI ribbon
  (it's a false claim). Disclose AI on YouTube in **Studio** (the Data API
  doesn't reliably set the altered/synthetic flag).
- **Licensing:** prefer **public domain / CC BY**; avoid **CC BY-SA** (ShareAlike
  can propagate to the whole video). Never use watermarked comp images, and never
  crop another outlet's watermark off (mis-attribution). Stay within
  citation/fair-use scope and attribute.
- **Resolution / crop:** the band is ~square (1080×1056). Reject a source that
  needs >2× upscale or loses >30% width to the cover-crop — build a contact sheet
  **at the real crop** and inspect it.
- **Verify every frame by eye** (all subjects, not just people): AI images of
  national/cultural symbols hallucinate the wrong nation (a Korean-constitution
  prompt returned the US Great Seal; "Korean lanterns" came back Chinese);
  press thumbnails mix in a different person; comps carry watermarks.

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

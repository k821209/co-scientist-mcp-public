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
2. `news.edge_tts_speak(script, "vo.wav", voice="ko-KR-SunHiNeural")` → VO.
3. `words = news.align_to_script(transcribe("vo.wav", language="ko"), script)`.
4. **Images** for the top band. The band is ~square (**1080×1056**) but
   `generate_image` returns **16:9** (1536×1024), and `news.montage` center-crops
   with `crop` (only ~68% of the width survives) — so **put "centered
   composition, subject centered, headroom" in the prompt**, or the subject gets
   cropped off.
   - real photos — `curl` from the article (respect the source / fair-use excerpt).
   - AI — `generate_image` (gpt-image, 16:9, `apply_style=False`).
5. `news.montage([(img, dur), …], "band.mp4", workdir)` → top band (1080×1056).
   Keep each still **≤ ~3 s** (avoid static), reuse a still only **≥ 5 cuts apart**.
6. **Compose the 9:16 frame yourself — do NOT use `compose_summary`** (it
   `asplit`s an audio track the montage doesn't have, and snaps `segments` to
   sentence boundaries ±5 s, which desyncs against `caption_words`). Instead:
   `ffmpeg` pad the 1080×1056 band onto a 1080×1920 canvas (band on top), then
   **burn one ASS** with `subtitles=`.
   - Captions + title: `caption.build_boxed_ass(words, ..., video_title=<headline>,
     title_end=<when to retire the header, e.g. before an end card>)`. It draws
     the **title header + word-pop captions only** (captions now linger through
     pauses by default — `hold_through_pauses`).
   - **eyebrow / source·publish-date line / accent bar / provenance ribbon have
     NO helper** — hand-author the extra ASS styles + Dialogue and concatenate
     them into the same ASS. libass gotcha: a `\p1` **drawing** anchors its bbox
     to `\pos` differently than text — use `\an7` with non-negative coords and
     compute the top-left yourself (don't rely on `\an5` centering for drawings).
7. **Provenance labels (required):** real photo → "사진·출처 <source>" badge
   (top-right); AI image → "AI 생성 이미지" ribbon (top-right).
8. `dub.mux_audio(band_9x16, vo.wav, out)` → `add_video(..., aspect_ratio="9:16")`
   → `/video-publish` (news defaults to **unlisted**). `mux_audio` now keeps the
   full video length (a silent end card past the VO is preserved).

**Briefing compilation:** intro / divider / outro cards + concat the segments.

## Guardrails (non-negotiable for news)
- Fact-check every claim; show **source + publish date** on screen.
- **Disclose AI images** on screen. YouTube's "altered/synthetic content"
  disclosure is set in **Studio** (the Data API doesn't reliably set it), so
  tell the user to toggle it there after upload.
- Real photos: stay within citation/fair-use scope and attribute.

### Originality (YouTube policy)
YouTube limits **mass-published near-identical / AI-generated** videos, and this
skill makes churning easy (template + AI images + TTS). Keep **per-video
originality**: your own written script, primary-source fact-check, on-screen
attribution — don't crank out near-duplicate clips. Default privacy
**unlisted**; let the user review before going public. (Publishing goes through
`/video-publish` — see its note on brand-new Google accounts.)

Exact signatures live in the `vh` repo (`vh/steps/news.py`); this skill encodes
the workflow + provenance rules.

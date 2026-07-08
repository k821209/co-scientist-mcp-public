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
   publish date**. Write a script with accurate figures.
2. `news.edge_tts_speak(script, "vo.wav", voice="ko-KR-SunHiNeural")` → VO.
3. `words = news.align_to_script(transcribe("vo.wav", language="ko"), script)`.
4. **Images** for the top band:
   - real photos — `curl` from the article (respect the source / stay within
     fair-use excerpt); label them.
   - AI — `generate_image` (gpt-image, 16:9, `apply_style=False`).
5. `news.montage([(img, dur), …], "band.mp4", workdir)` → top band (1080×1056).
   Keep each still **≤ ~3 s** (avoid static), and reuse a still only **≥ 5 cuts
   apart**.
6. Compose the 9:16 frame: top band + bottom zone = **headline + eyebrow +
   source·publish-date + word-pop captions** (`caption_words=words`). Center the
   accent bar when the title is centered.
7. **Provenance labels (required):** real photo → a "사진·출처 <source>" badge
   (top-right); AI image → an "AI 생성 이미지" ribbon (top-right).
8. `dub.mux_audio` the VO → `add_video(..., aspect_ratio="9:16")` →
   `/video-publish` (news defaults to **unlisted**).

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

---
name: video-dub
description: Dub a video into another language (default English) with free open-source Kokoro TTS — translate each segment (Claude-in-the-loop), synth speech on the render host, fit it to the timeline, burn synced translated captions, and swap the audio. Use when the user says "make an English version," "dub this to English," "port this to my English channel."
---

# /video-dub

**Triggers:** "make an English version," "dub this into English/Japanese/…,"
"port this Korean video to English." Sits on top of `/video-harness`; the
video counterpart of translating a paper for a different audience.

## What it does

Turns a (usually Korean) video into a target-language **dub** — translated
voiceover + synced translated captions — using **Kokoro TTS** on the render
host. Free, self-hosted GPU, **$0 API cost**. Screen recordings need no
lip-sync, so it's a clean translate → TTS → fit → mux pipeline.

Translation is **Claude-in-the-loop** (like chapters): you read the transcript
and translate each segment yourself. TTS/assembly/mux are `vh.steps.dub`.

## Prerequisites

- A **render host** configured (`VH_RENDER_HOST` etc. — see `/video-harness`),
  with **kokoro + soundfile (+ espeak-ng)** installed in its `VH_RENDER_PYTHON`
  env (one-time: `pip install kokoro soundfile`). TTS runs there.
- A source video (ideally the summary Short from `/video-harness`) + its
  `words.json` transcript.

## Flow

1. **Pick** the source video + target language.
2. **Segments + translation (you):** take the montage segments (the
   `(start,end)` windows — for a summary dub, reuse the `/video-harness §3b`
   selection) and their transcript text; **translate each segment** into the
   target language, keeping each translation ≈ the segment's spoken length
   (pad the meaning if the slot is long — it reads more naturally than silence).
3. **TTS (remote Kokoro):**
   ```python
   from vh.steps import dub
   meta = dub.tts_segments(translated_texts, workdir="out/<stem>/dub")
   ```
4. **Fit to the timeline:** `slots` = the same `(start,end)` windows.
   ```python
   dub.assemble_dub(meta, slots, out_wav="out/<stem>/dub/track.wav")
   ```
   (Each segment is padded if short, `atempo`'d if long, to match its slot.)
5. **Compose with translated captions burned in:**
   ```python
   from vh.steps.compose import compose_summary
   compose_summary("<src.mp4>", "out/<stem>/dub_video.mp4", segments, words,
                   header="<translated title>",
                   caption_words=dub.caption_words(meta, slot_starts))
   ```
   `caption_words` overrides the original transcript captions with the dub's
   word timestamps, so the burned subtitles match the new voice.
6. **Swap in the dub audio:**
   ```python
   dub.mux_audio("out/<stem>/dub_video.mp4", "out/<stem>/dub/track.wav",
                 "out/<stem>/final_en.mp4")
   ```
7. **Register as a variant:**
   ```
   mcp__co_scientist__add_video(title="<title> (EN)", local_path=".../final_en.mp4",
       aspect_ratio="9:16")
   ```
   Then it can go through `/video-publish` to a target-language channel.

## Config

`VH_DUB_VOICE` (Kokoro voice, default `am_adam`) · `VH_DUB_LANG` (default `a` =
American English). Heavy TTS + ffmpeg run on the **render host** (user-provided
env only — never hardcode an address).

## Notes
- Exact signatures live in the project's `vh` repo (`vh/steps/dub.py`); this
  skill encodes the workflow + co-scientist integration.
- TTS engine is pluggable — Kokoro (free, default); XTTS (voice-clone) /
  ElevenLabs (paid) are possible extensions.

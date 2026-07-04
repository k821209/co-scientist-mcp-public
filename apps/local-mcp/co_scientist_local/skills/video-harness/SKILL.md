---
name: video-harness
description: Turn a raw screen/talking-head recording into a publish-ready video — YouTube 16:9 long-form, 9:16 Shorts, or a boxed vertical — with silence trimming, word-level captions, content-aware chapters, and NVENC encode, then register the result in the project's Video tab. Use when the user says "edit this recording," "make a Short from this," "caption and cut this video," "prep this for YouTube."
---

# /video-harness

**Triggers:** "edit this recording," "cut the silences," "caption this
video," "make a 9:16 Short," "prep this for YouTube," "add chapters,"
"burn captions."

## What it does

Headless recording → publish-ready video. It drives the project's
**`video-harness`** pipeline (the `vh` toolkit that lives in the video
project) and wires the output into co-scientist's **Video tab** via
`add_video`. No CapCut / GUI editor — every stage is scriptable and
**timing-preserving** (captions stay in sync across cuts/inserts).

This skill owns the *methodology + co-scientist integration*. It does NOT
hardcode stage commands — invoke the harness through its own CLI
(`vh --help` / the repo README) so it tracks the installed version.

## Pipeline (run in this order)

1. **clean** — trim dead air. Native `ffmpeg silencedetect` (do NOT rely
   on auto-editor — 29.x is x86_64-only, unusable on aarch64). Preserves
   timing so later caption timecodes stay valid.
2. **transcribe** — Whisper **word-level** timestamps. Backend is chosen
   by env (`VH_ASR_BACKEND` / `VH_GPU_PYTHON`): faster-whisper on a CUDA
   x86_64 GPU when available; on aarch64 (no CTranslate2 CUDA wheel) fall
   back to transformers-Whisper on GPU, or CPU int8.
3. **chapters** — *Claude-in-the-loop*: **you** read the transcript and
   emit a `Chapter(start, title)` list (content-aware section breaks).
   That drives both the YouTube "0:00 Title" description block and, if
   enabled, burned title cards.
4. **captions** — ASS burn. Style `word-pop` (CapCut-style active-word
   highlight) or `line`. Korean/CJK needs Noto Sans CJK KR via the libass
   fontsdir (`VH_CAPTION_FONTSDIR`).
5. **reframe** — aspect-aware; never add blur bars or upscale when the
   source already matches the target aspect.
6. **boxed** (9:16 only, optional) — landscape→vertical with a 3-zone
   layout (top header / centered video band / bottom caption zone), no
   blur bars.
7. **interstitials** (optional) — full-frame chapter title cards spliced
   at boundaries, with captions **re-timed** onto the lengthened timeline.
8. **encode** — NVENC (`h264_nvenc`), configurable via `VH_VENC`.

## Inputs to gather first

- **source**: a Materials mp4 (`get_material` / `list_materials`) or a
  local path.
- **target**: `youtube-16:9` | `shorts-9:16` | `boxed`.
- **preset**: `screencast` | `talkinghead` | `shorts` | `slides`.
- **caption style**: `word-pop` (default) | `line`; **language** (Korean →
  set the CJK fontsdir).
- **chapter cards**: on/off.

## Render host (heavy stages) — user config ONLY

Transcription and encoding are GPU-heavy. When the local GPU is busy they
may run on a **remote render host**, but that host is a **user-provided
setting only** — the harness is portable via env vars
(`VH_FFMPEG`, `VH_FFPROBE`, `VH_CAPTION_FONTSDIR`, `VH_VENC`,
`VH_GPU_PYTHON`, `VH_ASR_BACKEND`). **Never hardcode or store any host /
SSH / IP address** in a skill, doc, code, or feedback. If no remote host
is configured, run locally. If the user wants offload, ask them for their
own host config; don't assume a default.

## After rendering — register in the Video tab

Once the burned mp4 (+ `.srt`/`.ass`) exists, register it so it appears in
the dashboard and opens the review loop:

```
mcp__co_scientist__add_video(
  title="<clip title>",
  local_path="<final .mp4>",
  aspect_ratio="16:9" | "9:16",
  fps=<fps>, duration_s=<seconds>,
  srt_local_path="<.srt>", ass_local_path="<.ass>",
)
```

Then give the user the **YouTube chapter block** (the `0:00 Title` lines
from step 3) to paste into the video description.

## Then hand off to review

Tell the user to leave timecode comments in the **Video tab**. To act on
them later, run **`/video-revision`** — it reads the open comments
(`list_video_comments`) and re-runs only the stages each one needs.

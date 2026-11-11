---
name: video-harness
description: Turn a raw screen/talking-head recording into a publish-ready video — YouTube 16:9 long-form, 9:16 Shorts, or a boxed vertical — with silence trimming, aspect reframe, word-level captions, and NVENC encode, then register the result in the project's Video tab. Use when the user says "edit this recording," "make a Short from this," "caption and cut this video," "prep this for YouTube."
requires: video
---

# /video-harness

**Triggers:** "edit this recording," "cut the silences," "caption this
video," "make a 9:16 Short," "prep this for YouTube," "add chapters."

## What it does

Raw recording → publish-ready video via the project's **`video-harness`**
(`vh`) toolkit — `ffmpeg` + Whisper, no CapCut — then registers the output
in co-scientist's **Video tab** with `add_video`. Everything is
timing-preserving (captions stay in sync across cuts/inserts).

`vh run` is a **one-shot pipeline selected by a PRESET** (not per-stage
subcommands). Chapters + burned title cards are a small **library** step on
top (Claude-in-the-loop).

> **Requires `vh` installed.** `vh` lives in its own git repo; install it once
> (`git clone https://github.com/k821209/co-scientist-video-harness.git ~/co-scientist-video-harness && pip install -e
> ~/co-scientist-video-harness`) so `import vh` works in every project. If you hit
> `ModuleNotFoundError: No module named 'vh'`, it isn't installed — see the
> "Video pipeline" section of setup-user.md. Update with `git -C
> ~/co-scientist-video-harness pull` + restart. Prereqs: ffmpeg, Noto Sans CJK KR (Korean
> captions), optional NVENC; remote offload via `VH_RENDER_*` (your host only).

## 1 — Pick the preset (this is the target + caption style)

`vh presets` lists them. Map the user's intent:

| user wants | preset | aspect | captions | reframe |
|---|---|---|---|---|
| screencast / tutorial | `screencast` | 16:9 | line | none |
| talking head / webcam | `talkinghead` | 16:9 | word-pop | none |
| Short (simple) | `shorts` | 9:16 | word-pop | blur-pad |
| Short (framed 3-zone) | `shorts_boxed` | 9:16 | word-pop | blur-pad (+ `layout=boxed`) |
| slides / deck capture | `slides` | 16:9 | line | none |

Language: pass `--lang ko` (Korean), `--lang en`, … Korean captions need
Noto Sans CJK KR via `VH_CAPTION_FONTSDIR` (see Config).

## 2 — Run the pipeline (common path)

```bash
# module form (works without install):
<python> -m vh.cli run <input.mp4> --preset shorts_boxed --lang ko --out out
# or, if installed (pip install -e .): 
vh run <input.mp4> --preset shorts_boxed --lang ko
```

`run` = **clean** (silencedetect trim) → **reframe** (aspect-aware; no blur
bars/upscale when the source already matches) → **transcribe** (word-level
Whisper) → **caption burn** (ASS). Outputs land in `out/<stem>/`:
`<stem>.final.mp4`, `<stem>.srt`, `<stem>.ass`, `<stem>.words.json`. The CLI
prints the final path, srt, and word count (`Result.final / .srt / .ass /
.words_json / .n_words / .duration_out`).

**Caption invariant (any project):** captions must show **one line at a time**
— Whisper can emit adjacent words with overlapping or reversed timestamps, and
if two caption events overlap, libass stacks them and they cover the frame.
`vh` de-conflicts this centrally in `caption._caption_events` (global cursor →
no overlap). If you ever build caption events by hand instead of via `vh`,
enforce the same: sort by start, clamp each event's start to the previous
event's end.

## 3 — Chapters + title cards (optional; library, not the CLI)

Not part of `vh run`. Read the transcript / `words.json`, **author the
`Chapter(start, title)` list yourself** (Claude-in-the-loop — this is the
point), then compose:

```python
import json
from vh.steps import titlecards as T, chapters as C
from vh.steps.transcribe import Word

words = [Word(**w) for w in json.load(open("out/<stem>/<stem>.words.json"))]
chs = [C.Chapter(0.0, "인트로"), C.Chapter(63.0, "설치"), C.Chapter(140.0, "데모")]

print(C.youtube_chapters(chs))          # "0:00 인트로 / 1:03 설치 …" description block
T.build_with_interstitials(             # splice full-frame cards + re-time captions
    "out/<stem>/<stem>.final.mp4", "out/<stem>/final_chaptered.mp4",
    chs, words, card_dur=1.8, style="word", max_words=5)
```

(`C.detect_chapters(words)` gives an LLM first pass, but you deciding the
boundaries from the transcript beats it.)

`build_with_interstitials` **auto-snaps each `Chapter.start` to the nearest
speech pause** (widest word-gap within ±3.5 s, else nearest word end), so a
card never cuts a word mid-utterance — approximate boundary times are fine; you
don't need frame-perfect starts.

## 3b — A Short FROM a long recording: highlight / summary / promo

Cutting a highlight, a summary or a promo out of a long recording is its own
procedure — choosing the moments, the hook, the cut list — in
`references/short-from-long.md`. Read it when the source is a long recording
and the target is a Short.

## 3c — Synthesized shorts: beat-driven assembly (`vh.steps.beats`)

A Short built from a script — narration, beats, stills or generated visuals —
is assembled beat by beat. The whole procedure, including the rule for what
is SPOKEN against what is shown on screen (numbers and abbreviations are
written out for the TTS), is `references/beats.md`. `/news-short` and
`/science-short` point here for it.

## 4 — Register in the Video tab

```
mcp__scivo__add_video(
  title="<clip title>",
  local_path="<…final.mp4>",          # or final_chaptered.mp4
  aspect_ratio="16:9" | "9:16",        # from the preset (screencast/talkinghead/slides→16:9; shorts*→9:16)
  fps=<fps>, duration_s=<Result.duration_out>,
  srt_local_path="<…srt>", ass_local_path="<…ass>",
)
```

If the video was built **chunk by chunk** (rows in the Video tab), the joined
file goes on THAT video — `mcp__scivo__join_video_chunks(video_id)`, or the
`add_video` above with the same `video_id` and `overwrite=True`. Not a new
video: the rows are the provenance, and deleting the chunked one takes them.

Then hand the user the **YouTube chapter block** from `youtube_chapters()`
for the description, and tell them to leave timecode comments in the Video
tab (→ act on them later with **`/video-revision`**).

## Config — all via env (`vh/config.py`)

`VH_FFMPEG` / `VH_FFPROBE` (binaries) · `VH_VENC` (`h264_nvenc` default |
`libx264`) · `VH_ASR_BACKEND` (**`auto`** default | `remote` | `gpu` | `cpu`)
· `VH_WHISPER_MODEL` (`small` … `large-v3`) · `VH_CAPTION_FONT` /
`VH_CAPTION_FONTSDIR` (Noto Sans CJK KR for Korean) · `VH_GPU_PYTHON` (local
GPU worker interpreter).

## Remote render-host offload — decision tree

Set a render host and the **whole heavy pipeline auto-offloads to it** —
handy when the local GPU is busy (e.g. an LLM server saturating VRAM) or on
aarch64 (GB10) where faster-whisper has no CUDA wheel.

- Turn it on with env vars: `VH_RENDER_HOST` (ssh target, e.g. `user@host`),
  `VH_RENDER_PORT` (optional ssh port), `VH_RENDER_PYTHON` (host interpreter
  with faster-whisper+CUDA, for transcription), `VH_RENDER_FFMPEG` (host
  ffmpeg, default `ffmpeg`), `VH_RENDER_FONTSDIR` (host fonts, for burned
  captions), `VH_RENDER_TMP` (default `/tmp`), `VH_RENDER_CACHE` (persistent
  input cache dir, default `<VH_RENDER_TMP>/vh_cache`).
- **Transcription:** `VH_ASR_BACKEND=auto` (default) → remote if
  `VH_RENDER_HOST` is set, else local (`gpu` → `VH_GPU_PYTHON`, else `cpu`
  int8). Force with `remote` / `gpu` / `cpu`. (wav → scp → remote
  faster-whisper → pull `words.json`.)
- **Encoding (now remote too):** every ffmpeg/NVENC stage — caption burn,
  boxed compose, interstitial title cards, reframe — routes through
  `remote.ffmpeg_run`: when a host is set it ships the inputs (+ `.ass`, card
  clips, fonts), rewrites paths inside the filtergraph (subtitles / fontsdir),
  runs remote ffmpeg, pulls the output back; else runs locally.
- **Net:** one `VH_RENDER_HOST` → **transcription AND encoding remote**; unset
  → everything local. `vh.remote.check()` probes the host's reachability +
  faster-whisper/ffmpeg/CUDA.
- **Input caching (large sources):** remote inputs go through a **persistent
  cache** on the host (keyed by size+mtime+name), so a large source uploads
  **once** and is reused across every ffmpeg call and re-render — no repeated
  re-upload even for multi-stage renders (caption + compose + interstitials).
  Cache dir = `VH_RENDER_CACHE` (default `<VH_RENDER_TMP>/vh_cache`);
  `vh.remote.clear_cache()` empties it. Only per-call job scratch is cleaned;
  the cached inputs persist.

**Security:** the render host lives **only in the user's env**. Never
hardcode or store any host / SSH / IP address in a skill, doc, code, log, or
feedback. No default; if `VH_RENDER_HOST` is unset, everything runs locally.

## Platform notes
- **NVENC** (`h264_nvenc`) for fast 1080p60. **aarch64 (GB10)**: auto-editor
  won't run (x86_64) → native silencedetect; faster-whisper has no CUDA wheel
  → transformers-Whisper on GPU (`VH_ASR_BACKEND=gpu` + `VH_GPU_PYTHON`) or CPU.

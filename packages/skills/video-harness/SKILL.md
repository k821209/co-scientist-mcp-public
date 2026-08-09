---
name: video-harness
description: Turn a raw screen/talking-head recording into a publish-ready video — YouTube 16:9 long-form, 9:16 Shorts, or a boxed vertical — with silence trimming, aspect reframe, word-level captions, and NVENC encode, then register the result in the project's Video tab. Use when the user says "edit this recording," "make a Short from this," "caption and cut this video," "prep this for YouTube."
---

# /video-harness

> **Video tools missing?** The video/YouTube tool family registers only on
> machines that do video work (a YouTube token exists, or
> `CO_SCIENTIST_ENABLE_VIDEO=1` in the MCP env). If `mcp__co_scientist__add_video`
> / `youtube_*` are absent, add that env var to `.mcp.json` and restart the
> session — needed once per fresh machine; after `youtube_connect` the token file
> auto-enables it.

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
| Short (framed 3-zone) | `shorts_boxed` | 9:16 | word-pop | **boxed** |
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

When the source is long-form and the user wants a Short, pick a **mode**:

- **highlight** — one self-contained window. Fastest: run the base pipeline on
  the chosen span (`--preset shorts_boxed`) / `compose.compose_boxed`; keep the
  in/out on sentence boundaries so it doesn't start or end mid-thought.
- **promo** — an ad-style 15–25 s Short around ONE pain/feature: a hook header
  → that feature's footage → soft CTA, with a **rewritten promo voiceover**
  (not the original audio). Flow: (a) pick one footage window `[s,e]` + write a
  short promo VO script (LLM); (b) `dub.tts_segments([vo])` → VO audio + word
  timestamps (remote Kokoro); (c) trim the source to `[s, s+vo_dur]`;
  (d) `compose_boxed(..., video_title=<hook>, caption_words=<vo words>)` with
  the zoom/focus/pan knobs below; (e) `dub.mux_audio(video, vo_wav, final)` to
  swap in the VO. Then `add_video(..., aspect_ratio="9:16")` → `/video-publish`.
- **summary** (recommended default for long-form) — stitch several key moments
  into one montage. **You** read the full transcript and choose 3–5
  `(start, end)` windows (LLM judgment — that's the point), targeting the user's
  length (default ~60 s, ≤180 s), then:
  ```python
  import json
  from vh.steps.compose import compose_summary
  from vh.steps.transcribe import Word
  words = [Word(**w) for w in json.load(open("out/<stem>/<stem>.words.json"))]
  segments = [(12.0, 28.0), (95.0, 110.0), (300.0, 318.0)]   # you choose these
  compose_summary("<src.mp4>", "out/<stem>/summary.mp4", segments, words,
                  header="<title>", style="word", max_words=4)
  ```
  Each window **auto-snaps to sentence boundaries** (word ending in .?!… or a
  ≥0.45 s pause, within ±5 s; else nearest word), windows sort chronologically,
  then box to 9:16 with captions re-timed onto the concatenated timeline — one
  ffmpeg pass, remote-offloaded + cached. Register the result with
  `add_video(..., aspect_ratio="9:16")`. (Pass `caption_words=` to burn
  alternate captions instead of the original transcript — e.g. a translated
  track; see `/video-dub`. `build_with_interstitials` takes the same param.)

**Boxed readability knobs** (`compose_boxed(..., zoom, focus_x, focus_y,
pan_x, duration)`) — a full 16:9 screencast squeezed into a 1080-wide band has
tiny, unreadable text; punch in instead:
- `zoom` > 1 — crop `1/zoom` of the source (punch-in) so on-screen text reads.
- `focus_x` / `focus_y` (0–1) — crop center; push toward off-center content so
  it isn't cut (e.g. a right-side comment/review panel → `focus_x≈0.75`).
- `pan_x=(f0, f1)` + `duration` — time-based horizontal pan: hold `f0` for the
  first third, glide to `f1`, hold — follow a moving pointer (e.g. DOCX left
  page → right page).

## 3c — Synthesized shorts: beat-driven assembly (`vh.steps.beats`)

For a Short with **no source recording** (news, product review, person feature),
the unit is a *beat*: one narration sentence-group plus the picture that carries
it. Beats mix freely — a quoted broadcast clip, a self-drawn card, a CC photo —
which `news.build_short` (stills only) and `news.build_clip_short` (clips only)
cannot do. That mixing is why episodes used to carry a hand-written 120-line
`assemble.py`; use the library instead:

```python
from vh.steps.beats import build_beat_short
BEATS = [                      # (id, kind, VO text, visual, in_point, caption, credit)
  ("b0", "clip", "훅 문장…",  "keynote", 11.0, "폴드7의 후속이 아니다", "영상 · 제조사 공식"),
  ("b1", "gfx",  "본문…",     "g_lineup", 0.0, None, None),
  ("b2", "photo","본문…",     "img/x.jpg", 0.0, "캡션", "사진 · …/Wikimedia (CC BY-SA)"),
]
build_beat_short(BEATS, "out/ep.mp4", workdir="wd",
                 clips={"keynote": "clips/keynote.mp4"}, gfx_dir=".",
                 precrop={"keynote": "crop=iw:ih*0.90:0:0,"},   # burned-in subs/banner
                 outro="outro.png", bgm="bgm.wav")
```

What the function encodes so you don't re-derive it per episode:

- **Audio-led timing** — each beat's VO is synthesized separately and *its*
  length sets the segment length. Never one long VO cut to fit pictures.
- **Blur-pad, never side-crop** — a 16:9 source is width-fitted over a blurred
  copy of itself; cover-cropping to 9:16 throws away ~44% of the width.
- **`precrop` per source** — broadcast clips carry burned-in captions and station
  banners; the ratio differs per source, so measure it per source.
- **Credit on every quoted frame**, `eyecatch` punch text on the cold open.
- **Length assertions** — a clip too short for its beat fails the build instead
  of silently freezing on its last frame.

**Cards: draw them with `vh.cardkit`.** A divider line placed at a guessed offset
(`y + 30`) runs straight through big glyphs; the render still succeeds, so it
ships unless someone opens a frame. `Card.text()` records each glyph bbox and
`Card.rule()` raises if the line would cross one — position accents off
`Card.bottom(...) + margin`, never off a guessed offset. Size panels from the
type, not from constants: `Card.ink(text, font)` measures the real glyph box and
`Card.stack_height(rows, pad=, gap=)` gives the height that leaves equal inner
margins (`Card.fit_font` for auto-shrink).

**Every card needs a headline. Ask: is the biggest text on this card what the
card is trying to say?** If not, the headline is missing — an eyebrow plus a
table reads as an untitled table even when the layout is perfect. Use the named
pair `Card.kicker(y, "기상청 53년 분석")` + `Card.headline(y, "여름은 실제로
길어졌다", rule_gap=26)`; `save()` prints a soft warning when a card has a kicker
and nothing much bigger (a big figure like "71만 5천 명" legitimately IS the
headline, so it's a warning, not an error — `check_hierarchy=False` to silence).
For list rows use `Card.row(y, left, right, sub=...)`: it keeps the parts as one
left-anchored group instead of splitting them to opposite margins, which reads as
three scattered fragments.

**Quote a clip INSIDE the card, not as a separate cut.** `Card.window(name, x, y,
w, h)` reserves a framed rectangle (saved to `<card>.windows.json`), then
`build_beat_short(..., ref_video={name: (clip, in_point)})` plays the clip there
for the whole beat. A separate `kind="clip"` beat needs a filler line ("here's
that video") purely to give the cut a duration; the window doesn't — one real
episode went 138s → 122s with MORE quotes and no empty narration, and the cold
open reads better because the first frame already moves. Rules that cost real
time to learn:
- Window x/y/w/h must be **even** (h264_nvenc rejects odd dimensions with a
  useless exit 234) — `window()` snaps down and says so.
- **Do NOT precrop a clip inside a window** — the opposite of the full-screen
  rule. Nothing collides with our layout in there, a half-cropped caption band
  looks worse, and cropping kills the broadcaster logo that shows where the
  quote came from. The clip is fitted whole (`decrease` + pad).
- Grab **~75s** of source: the assembler asserts the in-point leaves enough
  material for the beat, and you want room to pick a good passage.
- Pick in-points off a `contact_sheet` of the source, and start a cold-open
  window on **motion** (a still frame wastes the eyecatch).

**Then actually check the output** (`vh.qc`): `contact_sheet()` tiles the whole
video into one PNG — **read it**; `narration_match(video, script)` transcribes the
finished file and diffs it against the script (≥0.93 is normal for Korean TTS;
a sudden drop means a beat's audio never made it in). Pick clip in-points from a
contact sheet of the *source* too — a guessed in-point lands on a panel reaction
or a cutaway often enough to matter.

**Get the length before you render** — `build_beat_short(..., dry_run=True)`
synthesizes only the VO and returns `{total, beats:[{bid, vo, seg, lint}]}`. A
beat is as long as edge-tts takes to read it, which is hard to guess (a "+10s"
edit came out +34s and blew the 3-minute Shorts ceiling), and every correction
otherwise costs a full rebuild — `final_encode="copy"` still renders every
segment. Fit the ceiling by editing the SCRIPT first, then build once. The
per-beat `seg` values are also the length a **generated diagram** must be timed
to: a diagram rendered at a fixed framerate that runs longer than its beat shows
only its head, so its final conclusion never reaches the screen (the assembler
now warns when a window uses less than half its source).

**Put the source line in ONE place.** A beat's `credit` overlay is pinned to the
screen while a gfx card drifts under the Ken Burns zoom, so a card that draws its
own source line ends up colliding with it mid-beat. Draw it on the card with
`Card.source(...)` (recorded in the sidecar — the assembler then skips its own
credit and says so) *or* pass `credit=`, not both.

**Lint the VO script BEFORE synthesizing it** — `qc.lint_vo(text)`, run
automatically per beat by `build_beat_short` (`lint_script=False` to silence).
`narration_match` is an after-the-fact net with holes: whisper normalises what it
hears, so a line read with the wrong number word transcribes back to the digits
you wrote and passes. Three real traps, each with its own fix:
- Arabic numerals get chopped (`13조` → "일 ,삼조") → spell them in Hangul.
- digits + a counter take the NATIVE reading (`7번` → "일곱 번", which
  transcribes as "7번" and looks fine) → write `칠 번`.
- `십일일`/`이십일일` are mis-**heard** however you spell them (11일 sounds like
  12일) → drop the day from the VO, keep it on the card.

**If any stage REGENERATES the voice** — a generative lip-sync (LTX and
friends), a voice conversion, a re-dub — it may change the WORDS, not just the
timbre: a real episode shipped-to-review had "7월 14일" come back as
"10월 14일" (wrong date), "핵 역량" as "핵 영향", in 3 of 7 clips.
`narration_match` can't see this (a mismatch there looks like whisper
mis-hearing). Use `narration_drift(reference_audio, output)` — it transcribes
BOTH with the same model so the ASR's own errors cancel, and reports the
differing spans. Run it **per clip before assembly** (re-rendering one clip beats
redoing the episode). If a figure must be spoken, **write it in Hangul** — the
same date re-rendered as "칠월 십사일" came back correct where "7월 14일" had
drifted, so the digit tokens are the weak spot; treat that as *less risky*, not
safe (generation is non-deterministic), and keep the two-way check. Otherwise keep
**dates, figures, and proper nouns out of the
spoken line** entirely — put them on the card, where a generator can't rewrite
them. (Same reason abbreviations get spelled out: a TTS read "AIVO" as "aewo".)

## 4 — Register in the Video tab

```
mcp__co_scientist__add_video(
  title="<clip title>",
  local_path="<…final.mp4>",          # or final_chaptered.mp4
  aspect_ratio="16:9" | "9:16",        # from the preset (screencast/talkinghead/slides→16:9; shorts*→9:16)
  fps=<fps>, duration_s=<Result.duration_out>,
  srt_local_path="<…srt>", ass_local_path="<…ass>",
)
```

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

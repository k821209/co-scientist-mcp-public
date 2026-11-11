# A Short from a long recording

_Part of `/video-harness`. Read from `SKILL.md` when the task is a highlight, a summary or a promo cut FROM an existing long recording._

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

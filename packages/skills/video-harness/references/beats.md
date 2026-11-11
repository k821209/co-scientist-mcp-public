# Synthesized shorts: beat-driven assembly

_Part of `/video-harness`, and the shared reference for `/news-short` and `/science-short`. Read it when a Short is assembled from a script, narration and generated or still visuals rather than cut from a recording._

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
or a cutaway often enough to matter. Reading that sheet is `/visual-review`'s
loop — the whole set before any one frame, fix, re-render, look again, stop
when a full pass finds nothing — and a re-cut you have not re-read a sheet of
is not checked.

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

**Read the whole script too** — `qc.lint_copy(beats)`, also run by
`build_beat_short`. `lint_vo` reads HOW a line is spoken and `narration_match`
compares SOUNDS; **neither asks whether the sentence makes sense**, and two
episodes shipped that passed both. A listener asked "proposed to WHOM?" — the
person had been compressed out of the script — and then "reconciled with whom,
everyone's dead?". The same mistake twice: a counterpart deleted while
tightening.
- `no_counterpart` — 청혼/화해/맹약/복수 and friends with nobody named in this
  sentence or the one before.
- `no_antecedent` — 그들/그것/거기 with no noun to point back at.
- `money_scale_mix` — a lone 만-원 figure in a script otherwise counted in
  억/조. "삼만 육천구백 원" came back as `36,900억 원`: not a mis-pronunciation,
  a mis-HEARING dragged by the earlier beats. **This one needs the whole
  script** — the figure and the beats that dragged it were in different beats,
  so `lint_vo` cannot see it however good its rules get. Prescription is the
  same as `ambiguous_day`: take the precise number out of the VO, leave it on
  the card. One real episode went 0.9638 → 0.9909 that way with nothing lost,
  because the card already had the exact figure.

A hit is a place to re-read, not a verdict — a correct `28만 1500원` gets
flagged, and should.

The two word lists are guarded from OPPOSITE ends, and it is not an accident.
A missed person (친아버지) makes the check noisy; a missed relation word makes it
SILENT. So person words are guarded at the head — 신 must not match inside
정신 — and relation words at the tail — 계약 must not match inside 자유계약선수,
while 재계약을 and 청혼자 still must. If you extend either list, extend it in
the same direction.

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

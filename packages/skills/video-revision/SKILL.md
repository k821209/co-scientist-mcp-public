---
name: video-revision
description: Address open timecode comments left on a video in the dashboard's Video tab — re-cut, re-caption, reframe, or re-chapter as needed, re-render with video-harness, re-register, and resolve each comment. Use when the SessionStart banner reports open video comments, or the user says "handle the video comments," "apply the video feedback."
---

# /video-revision

> **Video tools missing?** The video/YouTube tool family registers only on
> machines that do video work (a YouTube token exists, or
> `CO_SCIENTIST_ENABLE_VIDEO=1` in the MCP env). If `mcp__scivo__add_video`
> / `youtube_*` are absent, add that env var to `.mcp.json` and restart the
> session — needed once per fresh machine; after `youtube_connect` the token file
> auto-enables it.

**Triggers:** "address the video comments," "apply the video feedback,"
"handle the timecode notes," or a report of open video comments. The video
analogue of `/paper-revision`, on top of `/video-harness`.

## Flow

1. **Pull the work list**
   ```
   mcp__scivo__list_video_comments(video_id, status="open")
   # omit video_id → open comments across ALL videos
   ```
   Each carries `t_seconds` (+ `frame` when fps known) and `text`.

2. **Map each comment → what to change.** `vh run` is one-shot by preset,
   so most fixes are a re-run with adjusted inputs; chapter/card edits use
   the library step:

   | comment | fix |
   |---|---|
   | caption typo / restyle / wrong language | re-run `vh run` with a different `--preset` (word↔line) or `--lang`; Korean → check `VH_CAPTION_FONTSDIR` |
   | too much dead air / cut here | re-run `vh run` (tune the preset's silence threshold in `vh/config.py`) |
   | wrong aspect / blur bars / crop | switch preset (`shorts` ↔ `shorts_boxed`, or a 16:9 preset) and re-run |
   | add/rename/move a chapter or title card | re-author the `Chapter(start,title)` list → `chapters.youtube_chapters()` + `titlecards.build_with_interstitials()` (see `/video-harness` §3) |
   | quality / encoder | set `VH_VENC` (`h264_nvenc`/`libx264`) and re-run |

   Batch comments that hit the same re-run into one pass. Keep it timing-
   preserving — captions re-derive from the new timeline, so nothing drifts.

3. **Re-register the new cut** (overwrite in place, same id):
   ```
   mcp__scivo__add_video(
       title=..., video_id="<same id>", overwrite=True,
       local_path="<new final.mp4>", aspect_ratio=...,
       srt_local_path=..., ass_local_path=...)
   ```

4. **Resolve each comment**, recording what changed:
   ```
   mcp__scivo__resolve_video_comment(
       video_id, comment_id, status="accepted", response="<what changed>")
   ```
   Decline one you won't act on with `status="rejected"` + a reason — don't
   leave it silently open.

5. **Confirm done:** `count_open_video_comments()` should reach 0 (every
   comment resolved or rejected-with-reason) before telling the user the pass
   is complete. Editing the video never auto-resolves its comments.

## Notes
- Same **render-host policy** as `/video-harness`: when `VH_RENDER_HOST` is
  set, both transcription and every ffmpeg/NVENC re-encode auto-offload to it;
  unset → everything local. Never hardcode an address — it lives only in the
  user's env.

## Chunked videos — one row per shot

A generated scene is made, judged and remade one chunk at a time. When the
video has chunks (`list_video_chunks(video_id)`), a comment carrying `chunk`
is a note on THAT row — "redo this shot", "the dissolve at the end is
wrong" — not a timecode in the joined file:

- `list_video_comments(video_id, chunk=n)` is one row's to-do list; mark the
  row `update_video_chunk(video_id, n, status="regenerate")` while you work.
- Regenerate = `add_video_chunk` again for the same `n` with the new file
  (version + 1; the old file is kept, so the joined result can still say what
  it holds). Record what your checks measured in `metrics` and the seed.
- **Boundaries before chunks.** A keyframe takes 30 s; a chunk 4–5 minutes
  and one to three tries. Register `first_image` / `last_image` first (no
  file), wait for the user to turn GO (`render`) on in the tab — or ask —
  and generate only rows whose `render` is true. A "redo this boundary"
  note means remake the keyframe, not the chunk.
- Then `resolve_video_comment` as usual. **Do not join.** The joined file is
  rebuilt only when the user asks: the tab's "Request join" sets
  `join_requested` on the video (`list_videos` shows it), and
  `join_video_chunks` does the concatenation here (ffmpeg). Until then the tab
  shows the joined result as behind, which is correct.

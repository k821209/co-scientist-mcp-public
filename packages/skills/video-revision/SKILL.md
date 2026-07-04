---
name: video-revision
description: Address open timecode comments left on a video in the dashboard's Video tab — re-cut, re-caption, reframe, or re-chapter as needed, re-render with video-harness, re-register, and resolve each comment. Use when the SessionStart banner reports open video comments, or the user says "handle the video comments," "apply the video feedback."
---

# /video-revision

**Triggers:** "address the video comments," "apply the video feedback,"
"handle the timecode notes," or a report of open video comments. The video
analogue of `/paper-revision`, on top of `/video-harness`.

## Flow

1. **Pull the work list**
   ```
   mcp__co_scientist__list_video_comments(video_id, status="open")
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
   mcp__co_scientist__add_video(
       title=..., video_id="<same id>", overwrite=True,
       local_path="<new final.mp4>", aspect_ratio=...,
       srt_local_path=..., ass_local_path=...)
   ```

4. **Resolve each comment**, recording what changed:
   ```
   mcp__co_scientist__resolve_video_comment(
       video_id, comment_id, status="accepted", response="<what changed>")
   ```
   Decline one you won't act on with `status="rejected"` + a reason — don't
   leave it silently open.

5. **Confirm done:** `count_open_video_comments()` should reach 0 (every
   comment resolved or rejected-with-reason) before telling the user the pass
   is complete. Editing the video never auto-resolves its comments.

## Notes
- Same **render-host policy** as `/video-harness`: heavy re-encode/re-
  transcribe use only the user's `VH_*`-configured host; never hardcode an
  address.

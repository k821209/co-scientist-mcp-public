---
name: video-revision
description: Address open timecode comments left on a video in the dashboard's Video tab — re-cut, re-caption, reframe, or re-chapter only the spots that need it, re-render, re-register, and resolve each comment. Use when the SessionStart banner reports open video comments, or the user says "handle the video comments," "apply the video feedback."
---

# /video-revision

**Triggers:** "address the video comments," "apply the video feedback,"
"handle the timecode notes," or a SessionStart report of open video
comments. The video analogue of `/paper-revision`.

## What it does

Users scrub a video in the **Video tab** and pin comments to a timecode
(open/resolved, like inline paper comments). This skill pulls the open
ones, maps each timecode to the pipeline stage that fixes it, re-renders,
re-registers, and resolves the comment — closing the loop so the
dashboard's open state matches the delivered cut.

## Flow

1. **Pull the work list**
   ```
   mcp__co_scientist__list_video_comments(video_id, status="open")
   # video_id omitted → open comments across ALL videos
   ```
   Each carries `t_seconds` (and `frame` when fps is known) + `text`.

2. **Map each comment → stage** (from `/video-harness`):
   - "cut / trim / dead air here" → **clean** (re-detect around that span).
   - "caption wrong / typo / restyle / wrong language" → **captions**
     (re-burn; word-pop vs line; fix the CJK fontsdir if Korean).
   - "wrong aspect / blur bars / crop" → **reframe** / **boxed**.
   - "add a section / rename chapter / move the boundary" → **chapters**
     (re-read the transcript, update the `Chapter(start,title)` list) +
     **interstitials** if title cards are on.
   - "re-encode / quality" → **encode**.

3. **Re-run only what changed.** Keep it timing-preserving — re-derive
   caption timecodes after any cut/insert so nothing drifts. Batch
   comments that hit the same stage into one re-render.

4. **Re-register the new cut** (overwrite in place, keeps the video id):
   ```
   mcp__co_scientist__add_video(title=..., video_id="<same id>",
       local_path="<new .mp4>", aspect_ratio=..., overwrite=True,
       srt_local_path=..., ass_local_path=...)
   ```

5. **Resolve each comment**, recording what changed:
   ```
   mcp__co_scientist__resolve_video_comment(
       video_id, comment_id, status="accepted", response="<what changed>")
   ```
   Decline a comment you won't act on with `status="rejected"` + a reason
   in `response` — don't leave it silently open.

6. **Confirm done**: `count_open_video_comments()` should reach 0 (every
   comment resolved or rejected-with-reason) before you tell the user the
   pass is complete.

## Notes

- Same **render-host policy** as `/video-harness`: heavy re-encode/re-
  transcribe use only the user's `VH_*`-configured host; never hardcode an
  address.
- Editing the video never auto-resolves its comments — drive `ai_open`/
  open count to 0 yourself.

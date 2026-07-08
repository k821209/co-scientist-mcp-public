---
name: video-publish
description: Publish a Video-tab deliverable to YouTube (long-form or Shorts) — assemble title/description + chapter block, upload from the local mp4, and save the URL back on the video. Use when the user says "upload this to YouTube," "publish the video," "put it on my channel."
---

# /video-publish

**Triggers:** "upload to YouTube," "publish the video," "put this on my
channel," "make it a Short on YouTube." The video counterpart of
`/paper-export` — but it produces a **live URL**, not a file.

## Prerequisites (one-time)

- A rendered video registered in the Video tab (via `/video-harness` →
  `add_video`).
- A Google OAuth client with the **YouTube Data API v3** enabled, supplied as
  `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` (env) — the user's own client.

## Note: brand-new Google accounts

Google's automated abuse detection is aggressive about **freshly-created**
accounts and can flag or suspend one regardless of what you do — more so when a
brand-new account is authorized from a datacenter/lab IP. This isn't caused by
this skill, and if it happens the only recourse is Google's appeal flow. To
avoid the false positive, prefer connecting an **established** account (some real
usage, phone-verified) and approve the device-flow code from a normal browser.

## Flow

0. **Pre-flight:** run `youtube_check()` FIRST — it verifies the token is valid
   and the account actually has a channel (returns `channel_title` / `channel_id`
   / `uploads_ok`). This catches a revoked token (`invalid_grant`) or a
   channel-less account before you render or upload anything.

1. **Check / establish connection** (two-step device flow):
   - `youtube_status(video_id)` → if `connected` is false, call
     `youtube_connect()`. It returns `{verification_url, user_code}` — **relay
     both to the user**: "open <verification_url> and enter <user_code>."
   - After they authorize, call `youtube_complete_connect()`. It returns
     `{connected: true}`, or `{pending: true}` if they haven't finished yet —
     wait and call it again. The refresh token is stored locally on this
     machine (never in the repo).

2. **Assemble metadata:**
   - **title** — the video's title (or ask).
   - **description** — the user's blurb **plus the YouTube chapter block** from
     `/video-harness` (`chapters.youtube_chapters()` — the `0:00 Title` lines
     let YouTube auto-populate chapters). 
   - **tags**, **category_id** (default `22` People & Blogs), **language**
     (`ko` default for Korean).

3. **Confirm privacy — this is an outward-facing action.** Default is
   **`unlisted`**. **Never publish public automatically.** Only pass
   `privacy="public"` after the user explicitly says to make it public; offer
   `unlisted` (share by link) or `private` (schedule with `publish_at`) as the
   safe default.

4. **Upload:**
   ```
   mcp__co_scientist__youtube_upload(
     video_id, title=…, description=<blurb + chapter block>,
     privacy="unlisted", language="ko",
     local_path="<the rendered .mp4>",   # optional; else pulled from Storage
   )
   ```
   A 9:16 video ≤3 min is auto-tagged `#Shorts`. Upload runs **on this machine
   from the local mp4** (best for large long-form; the user's bandwidth). The
   YouTube id/URL are saved on the Video doc.

5. **Report** the returned `youtube_url`. Re-running is **idempotent** — if the
   video is already uploaded it **updates the metadata** (title/description/
   privacy) instead of re-uploading, unless you pass `force=True`.

## Notes
- Captions: the burned-in captions ship in the mp4. (A separate soft-caption
  track upload can be added later.)
- Quota: `videos.insert` has a daily quota; surface a clear message on quota
  errors and let the user retry tomorrow.
- Idempotency + safety are the whole point: **unlisted by default, explicit
  confirm for public, URL stored so we never double-upload.**

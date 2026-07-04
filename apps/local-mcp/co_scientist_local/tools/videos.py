"""Project-level video deliverables + timestamp-anchored comments.

Some projects ship VIDEO (edited recordings, captioned long-form + 9:16 Shorts)
rather than papers. A video lives at ``projects/{pid}/videos/{video_id}`` with
an mp4 blob (optional .srt/.ass sidecars). From the dashboard's Video tab a user
leaves comments pinned to a timecode (``source='user'``); the agent reads the
open ones with :func:`list_video_comments`, re-cuts / re-captions, then resolves
them — the same review loop decks and papers use, but keyed on ``t_seconds``.

Videos are project-scoped (not under a paper), since a video project may have no
papers at all.
"""
from __future__ import annotations

import pathlib

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso, slugify

_VALID_ASPECT = {"16:9", "9:16", "1:1", "4:3"}
_VALID_COMMENT_STATUS = {"open", "resolved", "rejected"}


def _videos_path(state: State) -> str:
    return state.project_path("videos")


def _video_path(state: State, video_id: str) -> str:
    return state.project_path("videos", video_id)


def _comments_path(state: State, video_id: str) -> str:
    return state.project_path("videos", video_id, "comments")


def _comment_path(state: State, video_id: str, comment_id: str) -> str:
    return state.project_path("videos", video_id, "comments", comment_id)


def _blob_path(state: State, video_id: str, ext: str) -> str:
    return state.project_path("videos", f"{video_id}.{ext}")


def add_video(
    state: State,
    *,
    title: str,
    video_id: str | None = None,
    local_path: str | None = None,
    blob_path: str | None = None,
    aspect_ratio: str = "16:9",
    fps: float | None = None,
    duration_s: float | None = None,
    description: str | None = None,
    srt_local_path: str | None = None,
    ass_local_path: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Register a video deliverable.

    Provide `local_path` to upload the mp4 (and optional `srt_local_path` /
    `ass_local_path` caption sidecars) to Storage, or `blob_path` to reference an
    already-uploaded blob. `aspect_ratio` drives the dashboard player shape
    (16:9 long-form, 9:16 Shorts). Returns the video doc.
    """
    if not title or not title.strip():
        raise ValueError("title is required")
    if aspect_ratio not in _VALID_ASPECT:
        raise ValueError(f"aspect_ratio must be one of {sorted(_VALID_ASPECT)}")

    vid = video_id or slugify(title) or f"video-{new_id()[:8]}"
    path = _video_path(state, vid)
    existing = state.backend.get_doc(path)
    if existing is not None and not overwrite:
        raise ValueError(f"video already exists: {vid!r} (pass overwrite=True to replace)")

    mp4_blob = blob_path
    if local_path:
        p = pathlib.Path(local_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"video file not found: {local_path}")
        mp4_blob = _blob_path(state, vid, p.suffix.lstrip(".") or "mp4")
        state.backend.put_blob(mp4_blob, p.read_bytes())

    def _sidecar(local: str | None, ext: str, keep: str | None) -> str | None:
        if not local:
            return keep
        sp = pathlib.Path(local).expanduser()
        if not sp.is_file():
            return keep
        bp = _blob_path(state, vid, ext)
        state.backend.put_blob(bp, sp.read_bytes())
        return bp

    now = now_iso()
    doc = {
        "video_id": vid,
        "title": title.strip(),
        "description": description,
        "blob_path": mp4_blob if mp4_blob is not None
        else (existing.get("blob_path") if existing else None),
        "srt_blob_path": _sidecar(srt_local_path, "srt",
                                  existing.get("srt_blob_path") if existing else None),
        "ass_blob_path": _sidecar(ass_local_path, "ass",
                                  existing.get("ass_blob_path") if existing else None),
        "aspect_ratio": aspect_ratio,
        "fps": fps,
        "duration_s": duration_s,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def list_videos(state: State) -> list[dict]:
    """All videos in the project, newest first."""
    pairs = state.backend.list_collection(_videos_path(state))
    vids = [{**data, "video_id": data.get("video_id", vid)} for vid, data in pairs]
    vids.sort(key=lambda v: v.get("created_at") or "", reverse=True)
    return vids


def get_video(state: State, video_id: str) -> dict:
    doc = state.backend.get_doc(_video_path(state, video_id))
    if doc is None:
        raise NotFound(f"video not found: {video_id!r}")
    return doc


def update_video(state: State, video_id: str, **fields) -> dict:
    path = _video_path(state, video_id)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"video not found: {video_id!r}")
    allowed = {k: v for k, v in fields.items()
               if k in {"title", "description", "aspect_ratio", "fps", "duration_s"}}
    if "aspect_ratio" in allowed and allowed["aspect_ratio"] not in _VALID_ASPECT:
        raise ValueError(f"aspect_ratio must be one of {sorted(_VALID_ASPECT)}")
    allowed["updated_at"] = now_iso()
    state.backend.update_doc(path, allowed)
    return state.backend.get_doc(path)


def delete_video(state: State, video_id: str) -> bool:
    path = _video_path(state, video_id)
    if state.backend.get_doc(path) is None:
        return False
    for cid, _ in state.backend.list_collection(_comments_path(state, video_id)):
        state.backend.delete_doc(_comment_path(state, video_id, cid))
    state.backend.delete_doc(path)
    return True


# ─── timecode comments ───────────────────────────────────────────────────────


def add_video_comment(
    state: State, video_id: str, *, text: str, t_seconds: float,
    frame: int | None = None, author: str | None = None, source: str = "user",
) -> dict:
    """Pin a comment to a timecode (seconds; optional frame number)."""
    if state.backend.get_doc(_video_path(state, video_id)) is None:
        raise NotFound(f"video not found: {video_id!r}")
    if not text or not text.strip():
        raise ValueError("text is required")
    cid = new_id()
    now = now_iso()
    doc = {
        "text": text.strip(),
        "t_seconds": float(t_seconds),
        "frame": frame,
        "author": author,
        "source": source,
        "status": "open",
        "created_at": now,
    }
    state.backend.set_doc(_comment_path(state, video_id, cid), doc)
    return {"comment_id": cid, "video_id": video_id, **doc}


def list_video_comments(
    state: State, video_id: str | None = None, *, status: str | None = "open",
) -> list[dict]:
    """Timecode comments, sorted by (video, t_seconds).

    `video_id=None` spans every video in the project. `status='open'` (default)
    is the agent's to-do list; pass status=None for all.
    """
    vids = [video_id] if video_id else [v["video_id"] for v in list_videos(state)]
    out: list[dict] = []
    for vid in vids:
        for cid, c in state.backend.list_collection(_comments_path(state, vid)):
            if status is not None and c.get("status") != status:
                continue
            out.append({"comment_id": cid, "video_id": vid, **c})
    out.sort(key=lambda c: (c.get("video_id") or "", c.get("t_seconds") or 0.0))
    return out


def resolve_video_comment(
    state: State, video_id: str, comment_id: str, *,
    status: str = "resolved", response: str | None = None,
) -> dict:
    """Mark a comment `resolved` / `rejected` (or `open` to reopen)."""
    if status not in _VALID_COMMENT_STATUS:
        raise ValueError(f"status must be one of {sorted(_VALID_COMMENT_STATUS)}")
    path = _comment_path(state, video_id, comment_id)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"comment not found: {comment_id!r}")
    fields: dict = {
        "status": status,
        "resolved_at": now_iso() if status != "open" else None,
    }
    if response is not None:
        fields["response"] = response
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def count_open_video_comments(state: State) -> int:
    """Open, human-authored timecode comments across the project (excludes
    source='ai'). Parallel to count_open_user_comments for papers."""
    return sum(
        1 for c in list_video_comments(state, status="open")
        if c.get("source") != "ai"
    )

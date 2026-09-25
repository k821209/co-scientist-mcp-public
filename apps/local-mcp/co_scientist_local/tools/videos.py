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
    vids = []
    for vid, data in pairs:
        row = {**data, "video_id": data.get("video_id", vid)}
        chunks = [d for _, d in state.backend.list_collection(_chunks_path(state, vid))]
        if chunks:
            row["chunks"] = len(chunks)
            row["join"] = join_state(row, chunks)
            row["join_requested"] = bool(row.get("join_requested_at"))
            row["render_requested"] = bool(row.get("render_requested_at"))
            row["render_go"] = sorted(int(c["n"]) for c in chunks if c.get("render"))
        vids.append(row)
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
    for n, _ in state.backend.list_collection(_chunks_path(state, video_id)):
        state.backend.delete_doc(f"{_chunks_path(state, video_id)}/{n}")
    state.backend.delete_doc(path)
    return True


# ─── timecode comments ───────────────────────────────────────────────────────


def add_video_comment(
    state: State, video_id: str, *, text: str, t_seconds: float,
    frame: int | None = None, author: str | None = None, source: str = "user",
    image_blob_path: str | None = None, chunk: int | None = None,
) -> dict:
    """Pin a comment to a timecode (seconds; optional frame number). A reviewer
    can attach a reference image (Storage blob path) — read it with get_blob."""
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
        "image_blob_path": image_blob_path,
        # A comment on one CHUNK — "redo this shot" — rather than a timecode
        # in the joined file. The row it belongs to shows it.
        "chunk": int(chunk) if chunk is not None else None,
        "created_at": now,
    }
    state.backend.set_doc(_comment_path(state, video_id, cid), doc)
    return {"comment_id": cid, "video_id": video_id, **doc}


def list_video_comments(
    state: State, video_id: str | None = None, *, status: str | None = "open",
    chunk: int | None = None,
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
            if chunk is not None and c.get("chunk") != int(chunk):
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


# ─── chunks: a video as a list of shots (feedback aa48c224fb82) ───────────────
#
# Generated video is made, judged and remade one chunk at a time: forty-plus
# chunks for one scene, each regenerated one to three times, the verdicts
# taken in conversation and lost with the session. The Video tab held one
# finished file, so chunks were uploaded as separate videos with "which
# video, which chunk" written into titles, the prompt buried in a description,
# and the whole scene re-joined and re-uploaded for every single replacement.
# A video now owns chunks: prompt + file + continuity + metrics + comments
# per row, and joining only when asked, with the joined result knowing which
# chunk versions it was made from — stale the moment one changes.

_VALID_CHUNK_STATUS = {"ok", "regenerate", "draft"}


def _chunks_path(state: State, video_id: str) -> str:
    return state.project_path("videos", video_id, "chunks")


def _chunk_path(state: State, video_id: str, n: int) -> str:
    return state.project_path("videos", video_id, "chunks", f"{int(n):03d}")


def _chunk_blob_path(state: State, video_id: str, n: int, version: int, ext: str) -> str:
    return state.project_path("videos", video_id, "chunks", f"{int(n):03d}.v{version}.{ext}")


def _boundary_blob_path(state: State, video_id: str, n: int, which: str, ext: str) -> str:
    # Version-free: a keyframe is remade in 30 s and simply replaces the last
    # one; the chunk's video file is what carries a version.
    return state.project_path("videos", video_id, "chunks", f"{int(n):03d}.{which}.{ext}")


def _upload_image(state: State, video_id: str, n: int, which: str, local: str | None) -> str | None:
    if not local:
        return None
    p = pathlib.Path(local).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"{which} image not found: {local}")
    blob = _boundary_blob_path(state, video_id, n, which, p.suffix.lstrip(".") or "png")
    state.backend.put_blob(blob, p.read_bytes())
    return blob


def add_video_chunk(
    state: State, video_id: str, n: int, *, prompt: str,
    local_path: str | None = None, continuous: bool = True,
    metrics: dict | None = None, seed: int | None = None, notes: str | None = None,
    status: str = "ok", first_image: str | None = None, last_image: str | None = None,
    render: bool | None = None,
) -> dict:
    """Register (or regenerate) chunk `n` of a video. A new VIDEO FILE
    (`local_path`) gets `version + 1` and a new blob — the old file stays
    until the chunk is deleted, so a joined result can still say which
    version it holds. `continuous`: this chunk continues from the previous
    one's last frame (off = a cut). `metrics` is free-form (what the
    automatic checks measured).

    Boundary images come first: a keyframe takes 30 s, a chunk 4–5 minutes
    and one to three tries, and twice a wrong keyframe was only seen after
    the chunk had been generated (feedback 94ebb383267d). Register
    `first_image` / `last_image` with no `local_path`, let the user judge
    them in the tab, and generate only the rows whose `render` (GO) is on.
    A continuous chunk needs only `last_image`: its first frame IS the
    previous chunk's last."""
    if state.backend.get_doc(_video_path(state, video_id)) is None:
        raise NotFound(f"video not found: {video_id!r}")
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required — it is what the chunk row is for")
    if status not in _VALID_CHUNK_STATUS:
        raise ValueError(f"status must be one of {sorted(_VALID_CHUNK_STATUS)}")
    n = int(n)
    if n < 1:
        raise ValueError("chunk numbers start at 1")
    path = _chunk_path(state, video_id, n)
    existing = state.backend.get_doc(path)
    # The version counts VIDEO files: registering keyframes for a row, or
    # remaking them, does not make the joined result stale.
    version = (existing.get("version", 0) if existing else 0) + (1 if local_path else 0)
    if version == 0:
        version = 1 if local_path else 0
    blob = existing.get("blob_path") if existing else None
    if local_path:
        p = pathlib.Path(local_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"chunk file not found: {local_path}")
        blob = _chunk_blob_path(state, video_id, n, version, p.suffix.lstrip(".") or "mp4")
        state.backend.put_blob(blob, p.read_bytes())
    first_blob = _upload_image(state, video_id, n, "first", first_image) \
        or (existing.get("first_image_blob") if existing else None)
    last_blob = _upload_image(state, video_id, n, "last", last_image) \
        or (existing.get("last_image_blob") if existing else None)
    now = now_iso()
    doc = {
        "n": n,
        "prompt": prompt.strip(),
        "blob_path": blob,
        "continuous": bool(continuous),
        "status": status,
        "metrics": metrics or None,
        "seed": seed,
        "notes": notes,
        "version": version,
        "first_image_blob": first_blob,
        "last_image_blob": last_blob,
        # GO: generate this row on the next render. Off until the user turns
        # it on in the tab (or the caller says so); a row registered with its
        # video already made keeps whatever it had.
        "render": (bool(render) if render is not None
                   else (existing.get("render", False) if existing else False)),
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    video = state.backend.get_doc(_video_path(state, video_id)) or {}
    return {"video_id": video_id, **doc, "join": join_state(video, list_video_chunks(state, video_id))}


def update_video_chunk(state: State, video_id: str, n: int, **fields) -> dict:
    """Patch a chunk's prompt, continuity, status, metrics, seed or notes
    without touching its file."""
    path = _chunk_path(state, video_id, int(n))
    if state.backend.get_doc(path) is None:
        raise NotFound(f"chunk {n} not found for video {video_id!r}")
    allowed = {k: v for k, v in fields.items()
               if k in {"prompt", "continuous", "status", "metrics", "seed", "notes", "render"} and v is not None}
    if "render" in allowed:
        allowed["render"] = bool(allowed["render"])
    if "status" in allowed and allowed["status"] not in _VALID_CHUNK_STATUS:
        raise ValueError(f"status must be one of {sorted(_VALID_CHUNK_STATUS)}")
    if "continuous" in allowed:
        allowed["continuous"] = bool(allowed["continuous"])
    allowed["updated_at"] = now_iso()
    state.backend.update_doc(path, allowed)
    return state.backend.get_doc(path)


def delete_video_chunk(state: State, video_id: str, n: int) -> bool:
    path = _chunk_path(state, video_id, int(n))
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True


def list_video_chunks(state: State, video_id: str) -> list[dict]:
    """The video's chunks in order, each with its open-comment count."""
    if state.backend.get_doc(_video_path(state, video_id)) is None:
        raise NotFound(f"video not found: {video_id!r}")
    open_by_chunk: dict[int, int] = {}
    for _, c in state.backend.list_collection(_comments_path(state, video_id)):
        if c.get("chunk") is not None and (c.get("status") or "open") == "open":
            open_by_chunk[int(c["chunk"])] = open_by_chunk.get(int(c["chunk"]), 0) + 1
    rows = [{**d, "open_comments": open_by_chunk.get(int(d.get("n", 0)), 0)}
            for _, d in state.backend.list_collection(_chunks_path(state, video_id))]
    rows.sort(key=lambda r: int(r.get("n", 0)))
    # A continuous row's first frame is the previous row's last: say which
    # file that is, so the generator has both boundaries without guessing.
    prev_last = None
    for r in rows:
        own_first = r.get("first_image_blob")
        r["first_image_effective"] = (prev_last if (r.get("continuous", True) and not own_first) else own_first)
        prev_last = r.get("last_image_blob") or prev_last
    return rows


def join_state(video: dict, chunks: list[dict]) -> dict:
    """Is the joined file current for these chunks? `joined_from` on the
    video records the (n, version) pairs the join was built from; any chunk
    added, removed or regenerated since makes it stale — the Video-tab
    analogue of a figure going stale under its analysis."""
    joined = video.get("joined_from")
    chunks = [c for c in chunks if c.get("blob_path")]   # keyframe-only rows are not joinable yet
    if not chunks:
        return {"joined": bool(joined), "stale": False, "reason": None}
    have = {(int(c["n"]), int(c.get("version", 1))) for c in chunks}
    if not joined:
        return {"joined": False, "stale": True, "reason": "never joined"}
    was = {(int(j["n"]), int(j["version"])) for j in joined}
    if was == have:
        return {"joined": True, "stale": False, "reason": None,
                "joined_at": video.get("joined_at")}
    changed = sorted({n for n, _ in have ^ was})
    return {"joined": True, "stale": True,
            "reason": f"chunks changed since the join: {changed}",
            "joined_at": video.get("joined_at")}


def join_video_chunks(
    state: State, video_id: str, *, output_path: str | None = None,
    reencode: bool = False, _runner=None,
) -> dict:
    """Concatenate the chunk files, in order, into the video's own file —
    only when asked. Needs ffmpeg on this machine. Copies streams by default
    (chunks from one generator share a codec); `reencode=True` transcodes,
    which is also the automatic fallback when a copy-join fails."""
    import shutil
    import subprocess
    import tempfile

    video = get_video(state, video_id)
    chunks = [c for c in list_video_chunks(state, video_id) if c.get("blob_path")]
    if not chunks:
        raise ValueError("no chunks with files to join")
    missing = [c["n"] for c in list_video_chunks(state, video_id) if not c.get("blob_path")]
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None and _runner is None:
        return {"error": "ffmpeg is not on PATH on this machine — install it "
                         "(Debian/Ubuntu: sudo apt install -y ffmpeg · macOS: brew install ffmpeg)"}

    def run(cmd: list[str]) -> tuple[int, str]:
        if _runner is not None:
            return _runner(cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        return proc.returncode, (proc.stderr or proc.stdout or "")[-600:]

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = pathlib.Path(tmp)
        listing = []
        for c in chunks:
            data = state.backend.get_blob(c["blob_path"])
            if data is None:
                raise NotFound(f"chunk {c['n']} file missing in storage: {c['blob_path']}")
            f = tmpd / f"chunk-{int(c['n']):03d}.mp4"
            f.write_bytes(data)
            listing.append(f"file '{f}'")
        (tmpd / "list.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")
        out = tmpd / "joined.mp4"
        base = [ffmpeg or "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmpd / "list.txt")]
        attempts = []
        if not reencode:
            code, log = run(base + ["-c", "copy", str(out)])
            attempts.append(("copy", code))
        if reencode or attempts[-1][1] != 0 or not out.is_file():
            code, log = run(base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                                    "-c:a", "aac", "-movflags", "+faststart", str(out)])
            attempts.append(("reencode", code))
        if code != 0 or not out.is_file():
            return {"error": f"ffmpeg failed ({attempts}): {log}"}
        data = out.read_bytes()
        if output_path:
            dest = pathlib.Path(output_path).expanduser()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    blob = _blob_path(state, video_id, "mp4")
    state.backend.put_blob(blob, data)
    joined_from = [{"n": int(c["n"]), "version": int(c.get("version", 1))} for c in chunks]
    fields = {
        "blob_path": blob,
        "joined_from": joined_from,
        "joined_at": now_iso(),
        "join_requested_at": None,
        "updated_at": now_iso(),
    }
    state.backend.update_doc(_video_path(state, video_id), fields)
    return {
        "video_id": video_id, "blob_path": blob, "chunks": len(chunks),
        "joined_from": joined_from, "how": attempts[-1][0], "bytes": len(data),
        "skipped_without_file": missing,
        "local_path": output_path,
    }

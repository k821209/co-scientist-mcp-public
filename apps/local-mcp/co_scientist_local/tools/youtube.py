"""Publish a project's Video-tab deliverables to YouTube (MCP-local upload).

Runs on the user's machine (where the rendered mp4 already lives), so large
long-form uploads go straight from disk over the user's bandwidth — no Storage
round-trip. Auth is a per-user Google OAuth (YouTube Data API v3) via the
**device flow** (works on a headless box); the refresh token is stored locally
in the user's config dir, never in the repo.

Security posture: uploads default to `privacy="unlisted"` — publishing is an
outward-facing act, so going `public` must be an explicit, confirmed choice.
Idempotent: the YouTube video id is saved on the Video doc; a second call
updates metadata instead of re-uploading.

Only stdlib (urllib) — no new dependencies. The user supplies their own OAuth
client (YouTube Data API enabled) via env `YOUTUBE_CLIENT_ID` /
`YOUTUBE_CLIENT_SECRET` (or passed to youtube_connect).
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from ..state import State
from ..util import now_iso
from . import videos as _videos

_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
# Device flow REJECTS youtube.force-ssl (invalid_scope) — that scope is only
# needed for captions.insert (Phase 2). Request upload + manage (both are
# device-flow-allowed): upload covers videos.insert, manage covers the
# idempotent videos.update / thumbnails.set path.
_SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"

_SHORTS_MAX_SECONDS = 180


# ── token storage (local, user config dir) ───────────────────────────────────

def _token_path() -> pathlib.Path:
    p = os.environ.get("CO_SCIENTIST_YOUTUBE_TOKEN")
    if p:
        return pathlib.Path(p).expanduser()
    return pathlib.Path.home() / ".co-scientist" / "youtube_token.json"


def _pending_path() -> pathlib.Path:
    return _token_path().with_name("youtube_pending.json")


def _load_token() -> dict | None:
    path = _token_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_token(data: dict) -> None:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(path, 0o600)   # it holds a refresh token
    except OSError:
        pass


def _save_pending(data: dict) -> None:
    path = _pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_pending() -> dict | None:
    path = _pending_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _clear_pending() -> None:
    _pending_path().unlink(missing_ok=True)


def _client_creds(client_id: str | None, client_secret: str | None) -> tuple[str, str]:
    cid = client_id or os.environ.get("YOUTUBE_CLIENT_ID")
    csec = client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not cid or not csec:
        raise ValueError(
            "no OAuth client — set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET "
            "(create an OAuth client with the YouTube Data API v3 enabled) or "
            "pass client_id/client_secret to youtube_connect()"
        )
    return cid, csec


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)   # OAuth errors are JSON (e.g. authorization_pending)
        except Exception:
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from None


def _access_token() -> str:
    tok = _load_token()
    if not tok or not tok.get("refresh_token"):
        raise ValueError("not connected to YouTube — run youtube_connect() first")
    resp = _post_form(_TOKEN_URL, {
        "client_id": tok["client_id"],
        "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    })
    at = resp.get("access_token")
    if not at:
        err = resp.get("error") or "unknown_error"
        desc = resp.get("error_description") or ""
        # Google returns a useless "Bad Request" in error_description; the real
        # signal is the `error` field. Surface BOTH, and explain invalid_grant.
        if err == "invalid_grant":
            raise RuntimeError(
                "token refresh failed: invalid_grant — the refresh token was "
                "revoked or expired. Re-authorize with youtube_connect(); if that "
                "also fails, check the Google account/channel status (a suspended "
                "or deleted Google account revokes all grants)."
            )
        raise RuntimeError(f"token refresh failed: {err}" + (f" ({desc})" if desc else ""))
    return at


# ── auth (device flow) ────────────────────────────────────────────────────────

def youtube_connect(
    state: State, *, client_id: str | None = None, client_secret: str | None = None,
) -> dict:
    """STEP 1 of connecting to YouTube (OAuth device flow).

    Requests a device code and returns `{verification_url, user_code,
    expires_in}` IMMEDIATELY — it does NOT block. Tell the user to open the URL
    and enter the code; once they've authorized, call `youtube_complete_connect()`
    to finish. Needs a YouTube Data API OAuth client (installed/TV type) via
    YOUTUBE_CLIENT_ID/SECRET or the args."""
    cid, csec = _client_creds(client_id, client_secret)
    dev = _post_form(_DEVICE_CODE_URL, {"client_id": cid, "scope": _SCOPE})
    if "device_code" not in dev:
        raise RuntimeError(f"device-code request failed: {dev}")
    url = dev.get("verification_url") or dev.get("verification_uri")
    _save_pending({
        "device_code": dev["device_code"],
        "client_id": cid, "client_secret": csec,
        "interval": int(dev.get("interval", 5)),
        "verification_url": url,
    })
    return {
        "verification_url": url,
        "user_code": dev.get("user_code"),
        "expires_in": dev.get("expires_in"),
        "next": "have the user open verification_url and enter user_code, then call youtube_complete_connect()",
    }


def youtube_complete_connect(state: State, timeout_s: int = 120) -> dict:
    """STEP 2 — finish the device-flow connection started by `youtube_connect`.

    Polls (up to `timeout_s`) for the user's authorization, then stores the
    refresh token locally. If the user hasn't authorized yet, returns
    `{pending: true}` — call again after they finish in the browser."""
    pend = _load_pending()
    if not pend:
        raise ValueError("no pending connection — run youtube_connect() first")
    interval = max(2, int(pend.get("interval", 5)))
    deadline = time.monotonic() + max(5, timeout_s)
    while time.monotonic() < deadline:
        resp = _post_form(_TOKEN_URL, {
            "client_id": pend["client_id"], "client_secret": pend["client_secret"],
            "device_code": pend["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        err = resp.get("error")
        if err == "slow_down":
            interval += 2
        elif err == "authorization_pending":
            pass
        elif err in ("expired_token", "access_denied"):
            _clear_pending()
            raise RuntimeError(
                "authorization " + ("expired — run youtube_connect() again"
                                    if err == "expired_token" else "was denied"))
        elif err:
            raise RuntimeError(f"authorization failed: {resp.get('error_description') or err}")
        elif resp.get("refresh_token"):
            _save_token({
                "refresh_token": resp["refresh_token"],
                "client_id": pend["client_id"], "client_secret": pend["client_secret"],
                "scope": _SCOPE,
            })
            _clear_pending()
            return {"connected": True}
        time.sleep(interval)
    return {"pending": True,
            "verification_url": pend.get("verification_url"),
            "message": "not authorized yet — finish in the browser, then call youtube_complete_connect() again"}


def youtube_disconnect(state: State) -> dict:
    """Forget the stored YouTube credentials on this machine."""
    path = _token_path()
    existed = path.is_file()
    if existed:
        path.unlink()
    _clear_pending()
    return {"disconnected": existed}


# ── metadata (pure, testable) ─────────────────────────────────────────────────

def _is_short(aspect_ratio: str | None, duration_s: float | None) -> bool:
    return (aspect_ratio == "9:16") and (duration_s is not None and duration_s <= _SHORTS_MAX_SECONDS)


def _apply_shorts_tag(title: str, description: str, is_short: bool) -> tuple[str, str]:
    """YouTube infers Shorts from a 9:16, <=3min video with #Shorts in the
    title/description — add it if missing."""
    if not is_short:
        return title, description
    if "#shorts" in (title + " " + description).lower():
        return title, description
    return title, (description.rstrip() + "\n\n#Shorts").strip()


def _snippet_status(
    *, title: str, description: str, tags: list[str] | None, category_id: str,
    privacy: str, made_for_kids: bool, publish_at: str | None, default_lang: str | None,
) -> dict:
    snippet: dict = {"title": title, "description": description, "categoryId": category_id}
    if tags:
        snippet["tags"] = tags
    if default_lang:
        snippet["defaultLanguage"] = default_lang
    status: dict = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
    if publish_at:
        status["publishAt"] = publish_at
        status["privacyStatus"] = "private"   # scheduled uploads must start private
    return {"snippet": snippet, "status": status}


# ── upload ────────────────────────────────────────────────────────────────────

_VALID_PRIVACY = {"public", "unlisted", "private"}


def _resolve_source(state: State, video: dict, local_path: str | None) -> tuple[pathlib.Path, bool]:
    """Return (path, is_temp). Prefer a local file; else download the Video's
    Storage blob to a temp file."""
    if local_path:
        p = pathlib.Path(local_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"video file not found: {local_path}")
        return p, False
    bp = video.get("blob_path")
    if not bp:
        raise ValueError("video has no local_path and no stored blob_path to upload")
    data = state.backend.get_blob(bp)
    if data is None:
        raise ValueError(f"could not read video blob: {bp}")
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return pathlib.Path(tmp), True


def _resumable_upload(access_token: str, path: pathlib.Path, meta: dict) -> str:
    """Start a resumable session and PUT the file; return the new video id."""
    body = json.dumps(meta).encode()
    size = path.stat().st_size
    init = urllib.request.Request(
        f"{_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        data=body, method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
            "X-Upload-Content-Length": str(size),
        },
    )
    with urllib.request.urlopen(init, timeout=60) as r:
        session = r.headers.get("Location")
    if not session:
        raise RuntimeError("no resumable session URL returned")
    with path.open("rb") as fh:
        put = urllib.request.Request(
            session, data=fh, method="PUT",
            headers={"Content-Type": "video/*", "Content-Length": str(size)},
        )
        with urllib.request.urlopen(put, timeout=None) as r:
            out = json.loads(r.read().decode())
    vid = out.get("id")
    if not vid:
        raise RuntimeError(f"upload returned no video id: {str(out)[:200]}")
    return vid


def _update_metadata(access_token: str, yt_id: str, meta: dict) -> None:
    payload = json.dumps({"id": yt_id, **meta}).encode()
    req = urllib.request.Request(
        f"{_VIDEOS_URL}?part=snippet,status", data=payload, method="PUT",
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json; charset=UTF-8"},
    )
    urllib.request.urlopen(req, timeout=60).read()


def youtube_upload(
    state: State, video_id: str, *,
    title: str | None = None, description: str = "", tags: list[str] | None = None,
    category_id: str = "22", privacy: str = "unlisted", made_for_kids: bool = False,
    publish_at: str | None = None, language: str | None = "ko",
    local_path: str | None = None, force: bool = False,
) -> dict:
    """Upload a Video-tab item to YouTube (or update its metadata if already
    uploaded). Defaults to **unlisted** — pass privacy='public' explicitly, and
    only after the user confirms. 9:16 videos ≤3 min get a #Shorts tag. The
    YouTube id/URL are saved on the Video doc (idempotent; re-run updates
    metadata unless force=True re-uploads)."""
    if privacy not in _VALID_PRIVACY:
        raise ValueError(f"privacy must be one of {sorted(_VALID_PRIVACY)}")
    video = _videos.get_video(state, video_id)   # raises NotFound
    title = (title or video.get("title") or video_id).strip()
    is_short = _is_short(video.get("aspect_ratio"), video.get("duration_s"))
    title, description = _apply_shorts_tag(title, description, is_short)
    meta = _snippet_status(
        title=title, description=description, tags=tags, category_id=category_id,
        privacy=privacy, made_for_kids=made_for_kids, publish_at=publish_at,
        default_lang=language,
    )
    at = _access_token()

    existing = video.get("youtube_video_id")
    if not existing:
        # Pre-flight before sending bytes: a revoked token or a channel-less
        # account should fail HERE, not after uploading (or re-encoding) an mp4.
        chans = _channels_mine(at)
        if not chans:
            raise RuntimeError(
                "the connected Google account has no YouTube channel — create a "
                "channel (or reconnect with the channel-owning account) first. "
                "Run youtube_check() to inspect the connection."
            )

    if existing and not force:
        _update_metadata(at, existing, meta)
        yt_id, action = existing, "updated"
    else:
        src, is_temp = _resolve_source(state, video, local_path)
        try:
            yt_id = _resumable_upload(at, src, meta)
        finally:
            if is_temp:
                src.unlink(missing_ok=True)
        action = "uploaded"

    url = f"https://youtu.be/{yt_id}"
    # Persist directly (update_video's allowlist excludes youtube_* on purpose).
    state.backend.update_doc(_videos._video_path(state, video_id), {
        "youtube_video_id": yt_id,
        "youtube_url": url,
        "youtube_privacy": meta["status"]["privacyStatus"],
        "youtube_uploaded_at": now_iso(),
        "updated_at": now_iso(),
    })
    return {"action": action, "video_id": video_id, "youtube_video_id": yt_id,
            "youtube_url": url, "privacy": meta["status"]["privacyStatus"],
            "shorts": is_short}


def youtube_status(state: State, video_id: str) -> dict:
    """Return the stored YouTube publish state for a Video item."""
    v = _videos.get_video(state, video_id)
    return {
        "video_id": video_id,
        "youtube_video_id": v.get("youtube_video_id"),
        "youtube_url": v.get("youtube_url"),
        "youtube_privacy": v.get("youtube_privacy"),
        "connected": bool(_load_token()),
    }


def _channels_mine(access_token: str) -> list[dict]:
    """channels.list?mine=true — the target channel(s) for this token."""
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels"
        "?part=snippet,status,contentDetails&mine=true",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("items", []) or []


def youtube_check(state: State) -> dict:
    """Pre-flight the YouTube connection WITHOUT uploading (no video_id needed).
    Refreshes the token and calls channels.list?mine=true so you catch a revoked
    token or a channel-less account BEFORE spending time on a render/upload.
    Returns {connected, has_channel, channel_title, channel_id, uploads_ok, …}
    or a clear error."""
    if not _load_token():
        return {"connected": False, "error": "not connected — run youtube_connect()"}
    try:
        at = _access_token()
    except Exception as e:
        return {"connected": False, "error": str(e)}
    try:
        items = _channels_mine(at)
    except Exception as e:
        return {"connected": True, "has_channel": None, "error": f"channels.list failed: {e}"}
    if not items:
        return {
            "connected": True, "has_channel": False,
            "error": "the connected Google account has NO YouTube channel — "
                     "create a channel (or reconnect with the channel-owning "
                     "account) before uploading.",
        }
    ch = items[0]
    return {
        "connected": True, "has_channel": True,
        "channel_id": ch.get("id"),
        "channel_title": (ch.get("snippet") or {}).get("title"),
        "uploads_ok": (ch.get("status") or {}).get("longUploadsStatus"),
    }

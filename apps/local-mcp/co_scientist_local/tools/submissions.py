"""The file the journal actually received.

    doc:  projects/{pid}/papers/{slug}/submissions/{submission_id}
    blob: projects/{pid}/papers/{slug}/submissions/{submission_id}__{filename}

Nothing else in the structured data records this, and it cannot be derived. The
manuscript keeps moving after submission; the exports directory fills with
newer renders; and the newest export is the classic trap, because it sorts
first and looks the most authoritative. A marked-up copy built against the
wrong baseline passes every validation check and diffs against a document
nobody read — that shipped once, against a package that was prepared and then
superseded before it was ever sent.

Three properties, each of which is the point:

**The bytes are COPIED, never referenced.** Pointing at an export's blob would
mean the next `/paper-export` silently changes what "submitted" means. The
whole feature is a snapshot; a snapshot that can be rewritten from underneath
is not one.

**A submission is immutable.** There is no update. Sending a revised manuscript
is a NEW submission, and the earlier one stays — the history of what was sent
when IS the record.

**The user is the authority.** The agent may register what the user confirms
and must not infer it from filenames or dates. `submitted_on` and `venue` are
required precisely because only a person knows them.
"""
from __future__ import annotations

import hashlib
import pathlib
import re

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def _safe(name: str) -> str:
    base = pathlib.PurePosixPath(name).name or "submission"
    return (_UNSAFE.sub("_", base).strip("._") or "submission")[:120]


def _col(state: State, slug: str) -> str:
    return state.project_path("papers", slug, "submissions")


def _path(state: State, slug: str, sid: str) -> str:
    return state.project_path("papers", slug, "submissions", sid)


def _require_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r}")


def register_submission(
    state: State,
    slug: str,
    *,
    venue: str,
    submitted_on: str,
    export_id: str | None = None,
    local_path: str | None = None,
    label: str | None = None,
    note: str | None = None,
) -> dict:
    """Archive the file that was sent, from an export or from disk.

    Exactly one of `export_id` (an entry in this paper's exports) or
    `local_path`. The upload path exists because the user may have edited the
    export before sending it — which is the ordinary case, and the reason this
    cannot be inferred from our own records at all.
    """
    _require_paper(state, slug)
    if not (venue or "").strip():
        raise ValueError("venue is required — which journal received it")
    if not _DATE_RX.match((submitted_on or "").strip()):
        raise ValueError("submitted_on must be YYYY-MM-DD (the date it was SENT, "
                         "which is not necessarily today)")
    if bool(export_id) == bool(local_path):
        raise ValueError("give exactly one of export_id= or local_path=")

    if export_id:
        exp = state.backend.get_doc(
            state.project_path("papers", slug, "exports", export_id))
        if exp is None:
            raise NotFound(f"export {export_id!r} not found for {slug!r}")
        data = state.backend.get_blob(exp.get("blob_path") or "")
        if data is None:
            raise NotFound(f"export {export_id!r} has no stored file")
        filename = exp.get("filename") or f"{slug}.bin"
        content_type = exp.get("content_type")
    else:
        p = pathlib.Path(local_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"file not found: {local_path}")
        data = p.read_bytes()
        filename = p.name
        content_type = None

    sid = new_id()
    blob_path = _path(state, slug, f"{sid}__{_safe(filename)}")
    # Copied, not referenced: a later export must not be able to change what
    # this says was submitted.
    state.backend.put_blob(blob_path, data)

    doc = {
        "submission_id": sid,
        "slug": slug,
        "venue": venue.strip(),
        "submitted_on": submitted_on.strip(),
        "label": (label or "").strip() or None,
        "note": (note or "").strip() or None,
        "filename": filename,
        "content_type": content_type,
        "blob_path": blob_path,
        "size_bytes": len(data),
        # So the copy can be PROVEN to be the copy. Without it "this is the
        # submitted file" is a claim; with it, it is checkable.
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": "export" if export_id else "upload",
        "source_export_id": export_id,
        "created_at": now_iso(),
    }
    state.backend.set_doc(_path(state, slug, sid), doc)
    return {**doc, "dashboard_url": state.dashboard_url("papers", slug)}


def list_submissions(state: State, slug: str) -> list[dict]:
    """Everything sent for this paper, most recent submission first.

    The first entry is the CURRENT baseline. Earlier ones are kept: what was
    sent, and when, is the record."""
    _require_paper(state, slug)
    rows = [d for _, d in state.backend.list_collection(_col(state, slug))]
    rows.sort(key=lambda r: (r.get("submitted_on") or "",
                             r.get("created_at") or ""), reverse=True)
    return rows


def get_submission(
    state: State,
    slug: str,
    submission_id: str | None = None,
    *,
    dest_dir: str = ".",
    dest_path: str | None = None,
) -> dict:
    """Download a submitted file. Omit `submission_id` for the latest.

    The sha256 is re-computed and compared. A mismatch means the stored bytes
    are not the bytes that were registered, and that is worth failing over:
    the entire value of this record is that it can be trusted without being
    re-read.
    """
    subs = list_submissions(state, slug)
    if not subs:
        raise NotFound(
            f"no submission registered for {slug!r} — ask the user which file "
            "was sent and register it; do NOT substitute the current manuscript"
        )
    if submission_id:
        doc = next((s for s in subs if s.get("submission_id") == submission_id), None)
        if doc is None:
            raise NotFound(f"submission {submission_id!r} not found for {slug!r}")
    else:
        doc = subs[0]

    data = state.backend.get_blob(doc["blob_path"])
    if data is None:
        raise NotFound(f"submission blob missing at {doc['blob_path']}")
    got = hashlib.sha256(data).hexdigest()
    if doc.get("sha256") and got != doc["sha256"]:
        raise OSError(
            f"submission {doc['submission_id']} does not match its recorded "
            f"checksum — the stored file is not what was registered"
        )

    out = (pathlib.Path(dest_path).expanduser() if dest_path
           else pathlib.Path(dest_dir).expanduser() / doc["filename"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return {**doc, "path": str(out.resolve())}


def delete_submission(state: State, slug: str, submission_id: str) -> bool:
    """Remove a registration made in error.

    Deliberately the ONLY way to change one: there is no edit. A submission
    that could be amended would stop being a record of what was sent."""
    doc = state.backend.get_doc(_path(state, slug, submission_id))
    if doc is None:
        return False
    if doc.get("blob_path"):
        state.backend.delete_blob(doc["blob_path"])
    state.backend.delete_doc(_path(state, slug, submission_id))
    return True

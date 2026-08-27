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

**The user is the authority on WHICH FILE.** The agent may register what the
user confirms and must not infer the file from filenames or dates. The
surrounding facts are not worth the same friction: the journal comes from the
paper's own record, and the date defaults to today — a submission is normally
registered when it is sent, and both are editable when it is not.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import tempfile

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso
from . import imports

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
    venue: str | None = None,
    submitted_on: str | None = None,
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
    paper = state.backend.get_doc(state.project_path("papers", slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r}")
    # The journal is already recorded on the paper; asking again is a second
    # place for it to be wrong. Given explicitly, the argument wins — a paper
    # can be re-submitted elsewhere without its `journal` having been updated
    # yet.
    venue = (venue or "").strip() or (paper.get("journal") or "").strip() or None
    # Today, because a submission is normally registered when it is sent.
    # Editable for when it is not, and validated when given.
    submitted_on = (submitted_on or "").strip() or now_iso()[:10]
    if not _DATE_RX.match(submitted_on):
        raise ValueError("submitted_on must be YYYY-MM-DD (the date it was SENT)")
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
        # Denormalized for the Papers list's collectionGroup query — the
        # security rule matches on it, so a submission written without it is
        # invisible there.
        "project_id": state.project_id,
        "venue": venue,
        "submitted_on": submitted_on,
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

    # Record that nobody has yet checked this file against the sections.
    #
    # The file the journal received is USUALLY hand-edited on its way out — the
    # guide says so, and the user says so. Which means the sections are not what
    # was sent, and every revision built on them starts from a document that
    # does not exist anywhere: not the sent copy, not the reviewers' copy.
    #
    # This is a state bit, not a guess. Nothing here compares the bytes to the
    # prose; claiming "in sync" from a timestamp would be exactly the kind of
    # check that passes without looking. It says only that the comparison has
    # not been made, which is true at this moment and stays true until someone
    # makes it (`diff_submission`, then `acknowledge_submission_sync`).
    #
    # A submission built from an EXPORT came out of these sections, so there is
    # no hand-edit to reconcile unless the sections moved afterwards.
    state.backend.update_doc(
        state.project_path("papers", slug),
        {
            "submission_sync": {
                "submission_id": sid,
                "filename": filename,
                "registered_at": doc["created_at"],
                "source": doc["source"],
                "state": "from_export" if export_id else "unreconciled",
                "note": None,
                "reconciled_at": None,
            },
            "updated_at": now_iso(),
        },
    )
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


# ── reconciling the sections with what was actually sent ────────────────────

_PARA_MIN = 40   # chars; below this a "paragraph" is a heading or a stray line


def _paras(text: str) -> list[str]:
    """Paragraphs, normalized for comparison.

    Whitespace and case are collapsed because a docx round-trip changes both
    without changing a word — comparing raw text would report every paragraph
    as different and the report would be worth nothing.
    """
    out = []
    for block in re.split(r"\n\s*\n", text or ""):
        norm = re.sub(r"\s+", " ", block).strip().lower()
        # Markdown emphasis and heading marks survive the conversion unevenly.
        norm = re.sub(r"[*_`#>\[\]()]", "", norm)
        if len(norm) >= _PARA_MIN:
            out.append((norm, re.sub(r"\s+", " ", block).strip()))
    return out


def diff_submission(
    state: State,
    slug: str,
    submission_id: str | None = None,
) -> dict:
    """Compare the sections against the file that was actually SENT.

    Read-only. Writes nothing, changes nothing — the point is to give the user
    something to decide from, because the decision is theirs: the sent file is
    usually the one they hand-edited, so its wording is the authority, but only
    they know which differences were deliberate.

    Reports BOTH directions, because only one of them is obvious:
      - `missing_from_sections` — paragraphs in the sent file that appear in no
        section. These are the hand-edits. This is the direction that matters
        and the one a one-way "is the manuscript current?" check never asks.
      - `not_in_submission` — section paragraphs absent from the sent file, i.e.
        written after submission, or cut before it went.

    Paragraph containment rather than a similarity score: "8 of 9 paragraphs
    match, here is the one that does not" is something a person can act on,
    where "0.94 similar" is not.
    """
    _require_paper(state, slug)
    got = get_submission(state, slug, submission_id, dest_dir=tempfile.mkdtemp())
    local = got["path"]
    suffix = pathlib.Path(local).suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        # Already text. import_document would send it through pandoc, which
        # converts markdown to markdown and makes the comparison depend on a
        # binary it does not need — so a project that submitted a .md could not
        # be diffed on a machine without pandoc, for no reason.
        conv = {
            "markdown": pathlib.Path(local).read_text(encoding="utf-8", errors="replace"),
            "source_format": suffix.lstrip("."),
            "warnings": [],
        }
    else:
        try:
            conv = imports.import_document(state, local_path=local)
        except Exception as exc:                               # noqa: BLE001
            raise ValueError(
                f"could not read the submitted {suffix or 'file'}: {exc}. "
                f"Download it with get_submission and compare by hand."
            ) from exc

    sub_paras = _paras(conv.get("markdown") or "")
    sub_norm = {n for n, _ in sub_paras}

    sections = [
        data for _, data in state.backend.list_collection(
            state.project_path("papers", slug, "sections"))
    ]
    sections.sort(key=lambda s: s.get("sort_order", 999))

    per_section, sec_norm = [], set()
    for sec in sections:
        paras = _paras(sec.get("body") or "")
        sec_norm.update(n for n, _ in paras)
        absent = [raw for n, raw in paras if n not in sub_norm]
        per_section.append({
            "key": sec.get("key"),
            "title": sec.get("title"),
            "paragraphs": len(paras),
            "matched": len(paras) - len(absent),
            "not_in_submission": [_clip(r) for r in absent[:5]],
            "not_in_submission_total": len(absent),
        })

    missing = [raw for n, raw in sub_paras if n not in sec_norm]
    return {
        "slug": slug,
        "submission_id": got["submission_id"],
        "filename": got.get("filename"),
        "submitted_on": got.get("submitted_on"),
        "source_format": conv.get("source_format"),
        "warnings": conv.get("warnings") or [],
        "submission_paragraphs": len(sub_paras),
        "sections": per_section,
        # The hand-edits: what the journal has and this project does not.
        "missing_from_sections": [_clip(r) for r in missing[:20]],
        "missing_from_sections_total": len(missing),
        "identical": not missing and all(
            s["not_in_submission_total"] == 0 for s in per_section),
        "local_path": local,
    }


def _clip(text: str, n: int = 300) -> str:
    return text if len(text) <= n else f"{text[:n]}…"


def acknowledge_submission_sync(
    state: State,
    slug: str,
    *,
    note: str | None = None,
) -> dict:
    """Mark the sections as reconciled with the submitted file.

    Call this once the differences have been dealt with — either applied to the
    sections or looked at and deliberately left. The flag exists so the question
    is asked once rather than every session; clearing it without looking puts it
    back to being asked by nobody.
    """
    _require_paper(state, slug)
    path = state.project_path("papers", slug)
    paper = state.backend.get_doc(path)
    sync = dict((paper or {}).get("submission_sync") or {})
    if not sync:
        raise NotFound(f"no registered submission to reconcile for {slug!r}")
    sync.update({
        "state": "reconciled",
        "reconciled_at": now_iso(),
        "note": (note or "").strip() or None,
    })
    state.backend.update_doc(path, {"submission_sync": sync, "updated_at": now_iso()})
    return sync

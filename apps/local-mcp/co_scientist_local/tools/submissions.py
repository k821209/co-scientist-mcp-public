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

import difflib
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
    sections = [
        data for _, data in state.backend.list_collection(
            state.project_path("papers", slug, "sections"))
    ]
    sections.sort(key=lambda s: s.get("sort_order", 999))
    sec_norm_all = {n for sec in sections for n, _ in _paras(sec.get("body") or "")}

    # Which file is the baseline. With no id, "the latest" picked a
    # supplementary file registered after the main text and compared the
    # manuscript against its tables — matched 0 everywhere, read as "the
    # whole manuscript diverged" (feedback 493c71de0e75). So: the latest,
    # unless nothing in it matches a section, in which case every registered
    # file is read and the one sharing the most paragraphs with the
    # sections wins. The result says which was chosen and why.
    baseline_reason = "submission_id given"
    if submission_id is None:
        rows = list_submissions(state, slug)
        if not rows:
            raise NotFound(f"no submission registered for {slug!r}")
        got, conv = _read_submission(state, slug, rows[0]["submission_id"])
        overlap = sum(1 for n, _ in _paras(conv.get("markdown") or "") if n in sec_norm_all)
        baseline_reason = f"the latest submission ({got.get('filename')})"
        if overlap == 0 and len(rows) > 1:
            best = (0, got, conv, rows[0])
            for r in rows[1:]:
                g2, c2 = _read_submission(state, slug, r["submission_id"])
                o2 = sum(1 for n, _ in _paras(c2.get("markdown") or "") if n in sec_norm_all)
                if o2 > best[0]:
                    best = (o2, g2, c2, r)
            if best[0] > 0:
                got, conv = best[1], best[2]
                baseline_reason = (f"{got.get('filename')} — the latest ({rows[0].get('filename')}) "
                                   f"shares no paragraph with the sections, this one shares {best[0]}; "
                                   "the latest is probably a supplementary file")
    else:
        got, conv = _read_submission(state, slug, submission_id)
    local = got["path"]

    sub_paras = _paras(conv.get("markdown") or "")
    sub_norm = {n for n, _ in sub_paras}

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

    # A paragraph that shows up on BOTH sides is one paragraph rendered twice,
    # not a difference. Citation keys become numbers (`[@lam2024]` → `[6]`),
    # em-dashes become `---`, a bullet becomes `1.`, a phrase picks up italics —
    # none of which a person needs to look at, and all of which drown the ones
    # they do. A real run reported 70 and 39 when six passages had actually
    # changed.
    rendering_only, missing, per_section = _fold_rerenderings(missing, per_section)

    warnings = list(conv.get("warnings") or [])
    if per_section and all(s["matched"] == 0 for s in per_section):
        warnings.append(
            "no section paragraph matches the baseline — far more often the wrong "
            "file (a supplementary, a cover letter) than a manuscript rewritten "
            "end to end; check `filename`, or pass submission_id")

    # What changed INSIDE each paragraph, word by word — the question a
    # revision author has, which containment cannot answer: 4 of 39 matched
    # is "35 paragraphs differ by a clause or a number", not 35 rewrites.
    # Stored per section so the Paper tab shows it beside the text
    # (feedback 493c71de0e75); the manuscript itself is untouched.
    word_diff = _word_diff_sections(sections, sub_paras)
    # The report is the valuable part and is already computed; a rejected
    # cache write must not take it down.
    stored = True
    try:
        _store_diff(state, slug, got, word_diff)
    except Exception as exc:                                # noqa: BLE001
        stored = False
        warnings.append(f"the word-level diff could not be stored for the Paper tab: {exc}")

    return {
        "slug": slug,
        "submission_id": got["submission_id"],
        "baseline_reason": baseline_reason,
        "filename": got.get("filename"),
        "submitted_on": got.get("submitted_on"),
        "source_format": conv.get("source_format"),
        "warnings": warnings,
        "word_diff": {
            "sections": [{"key": d["key"], "changed": d["changed"], "added": d["added"],
                          "removed": d["removed"], "words_inserted": d["words_inserted"],
                          "words_deleted": d["words_deleted"]} for d in word_diff],
            "stored": stored,
            "where": "Paper tab → Manuscript → 'vs submission'",
        },
        "submission_paragraphs": len(sub_paras),
        "sections": per_section,
        # The hand-edits: what the journal has and this project does not.
        "missing_from_sections": [_clip(r) for r in missing[:20]],
        "missing_from_sections_total": len(missing),
        # Paired paragraphs whose WORDS match — kept, because "we set 43 aside
        # as formatting" is checkable and "43 differences vanished" is not.
        "rendering_only": [{"submission": _clip(a), "sections": _clip(b)}
                           for a, b in rendering_only[:10]],
        "rendering_only_total": len(rendering_only),
        # Formatting is not a difference in wording, so it does not stop this
        # being "the same manuscript".
        "identical": not missing and all(
            s["not_in_submission_total"] == 0 for s in per_section),
        "local_path": local,
    }


def _clip(text: str, n: int = 300) -> str:
    return text if len(text) <= n else f"{text[:n]}…"


def _read_submission(state: State, slug: str, submission_id: str) -> tuple[dict, dict]:
    got = get_submission(state, slug, submission_id, dest_dir=tempfile.mkdtemp())
    local = got["path"]
    suffix = pathlib.Path(local).suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        # Already text. import_document would send it through pandoc, which
        # converts markdown to markdown and makes the comparison depend on a
        # binary it does not need — so a project that submitted a .md could not
        # be diffed on a machine without pandoc, for no reason.
        return got, {
            "markdown": pathlib.Path(local).read_text(encoding="utf-8", errors="replace"),
            "source_format": suffix.lstrip("."),
            "warnings": [],
        }
    try:
        return got, imports.import_document(state, local_path=local)
    except Exception as exc:                               # noqa: BLE001
        raise ValueError(
            f"could not read the submitted {suffix or 'file'}: {exc}. "
            f"Download it with get_submission and compare by hand."
        ) from exc


_PAIR_MIN = 0.45          # below this a paragraph is new, not a revision of another
_WORD = re.compile(r"\S+|\s+")


def _word_ops(old: str, new: str) -> list[dict]:
    """[{k, t}, …] over whitespace-split tokens: k = 'same' / 'del' / 'ins'.

    Maps, not pairs: Firestore refuses an array nested in an array at any
    depth, and the first stored section killed the whole call — report
    included (feedback 89fd51d43181)."""
    a, b = _WORD.findall(old), _WORD.findall(new)
    ops: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"k": "same", "t": "".join(a[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"k": "del", "t": "".join(a[i1:i2])})
            if j2 > j1:
                ops.append({"k": "ins", "t": "".join(b[j1:j2])})
    return ops


def _word_diff_sections(sections: list[dict], sub_paras: list[tuple[str, str]]) -> list[dict]:
    """Per section: its paragraphs paired with the submission's (each used
    once, best similarity first, pairings in order), with word ops."""
    sub_norms = [n for n, _ in sub_paras]
    sub_raw = [r for _, r in sub_paras]
    used: set[int] = set()
    out = []
    for sec in sections:
        paras = _paras(sec.get("body") or "")
        items: list[dict] = []
        changed = added = w_ins = w_del = 0
        for norm, raw in paras:
            if norm in sub_norms and sub_norms.index(norm) not in used:
                j = sub_norms.index(norm); used.add(j)
                items.append({"kind": "same", "text": raw}); continue
            best, bj = 0.0, -1
            for j, sn in enumerate(sub_norms):
                if j in used:
                    continue
                m = difflib.SequenceMatcher(None, norm, sn, autojunk=False)
                if m.quick_ratio() < _PAIR_MIN:
                    continue
                r = m.ratio()
                if r > best:
                    best, bj = r, j
            if bj >= 0 and best >= _PAIR_MIN:
                used.add(bj)
                ops = _word_ops(sub_raw[bj], raw)
                w_ins += sum(len(o["t"].split()) for o in ops if o["k"] == "ins")
                w_del += sum(len(o["t"].split()) for o in ops if o["k"] == "del")
                items.append({"kind": "changed", "text": raw, "old": sub_raw[bj], "ops": ops})
                changed += 1
            else:
                items.append({"kind": "added", "text": raw}); added += 1
                w_ins += len(raw.split())
        out.append({"key": sec.get("key"), "title": sec.get("title"), "items": items,
                    "changed": changed, "added": added, "removed": 0,
                    "words_inserted": w_ins, "words_deleted": w_del})
    # Submission paragraphs no section claimed: removed in the revision (or
    # front matter / tables the sections never held). Listed under a
    # trailing pseudo-section so nothing the reviewers read is dropped from
    # view; the tab shows it last.
    left = [sub_raw[j] for j in range(len(sub_raw)) if j not in used]
    if left:
        out.append({"key": "_unmatched", "title": "In the submission, not in any section",
                    "items": [{"kind": "removed", "text": t} for t in left],
                    "changed": 0, "added": 0, "removed": len(left),
                    "words_inserted": 0, "words_deleted": sum(len(t.split()) for t in left)})
    return out


def _store_diff(state: State, slug: str, got: dict, word_diff: list[dict]) -> None:
    col = state.project_path("papers", slug, "submission_diffs")
    for d, _ in list(state.backend.list_collection(col)):
        state.backend.delete_doc(f"{col}/{d}")
    now = now_iso()
    for d in word_diff:
        state.backend.set_doc(f"{col}/{d['key']}", {**d, "computed_at": now})
    state.backend.set_doc(f"{col}/_meta", {
        "submission_id": got["submission_id"], "filename": got.get("filename"),
        "submitted_on": got.get("submitted_on"), "computed_at": now,
        "sections": [d["key"] for d in word_diff],
    })


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
        # The stamp only exists for submissions registered after the flag was
        # added, and the people it fails are exactly the ones who need this:
        # they submitted, then went to reconcile. Derive it from the submission
        # itself rather than making them re-register, which would leave two
        # baseline records for one file — a worse state than the missing flag.
        sync = _derive_sync(state, slug)
    if not sync:
        raise NotFound(f"no registered submission to reconcile for {slug!r}")
    sync.update({
        "state": "reconciled",
        "reconciled_at": now_iso(),
        "note": (note or "").strip() or None,
    })
    state.backend.update_doc(path, {"submission_sync": sync, "updated_at": now_iso()})
    return sync


def _derive_sync(state: State, slug: str) -> dict:
    """The `submission_sync` a paper WOULD have if its submission were
    registered today. Empty dict when nothing has been submitted.

    Read-only, and derived rather than backfilled on write: a migration would
    have to guess, for every paper in every project, whether someone had already
    reconciled by hand — and stamping `unreconciled` over that would raise a
    question the user already answered.
    """
    subs = list_submissions(state, slug)
    if not subs:
        return {}
    latest = subs[0]
    return {
        "submission_id": latest.get("submission_id"),
        "filename": latest.get("filename"),
        "registered_at": latest.get("created_at"),
        "source": latest.get("source"),
        "state": "from_export" if latest.get("source") == "export" else "unreconciled",
        "note": None,
        "reconciled_at": None,
        # So a reader can tell "nobody has looked" from "this predates the
        # flag" — the two mean the same thing here, but only one of them is
        # something the user did.
        "derived": True,
    }


# A bullet that became "1." is formatting, and its number is not a number the
# reader cares about — left in, it would block every folded list item.
_LIST_MARK = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+", re.M)


def _words(text: str) -> str:
    """Letters and digits only — what survives a round-trip through Word.

    Citation markers go too: the sections store `{doi:…}` / `[@key]` and the
    rendered document has `[6]`, so leaving digits attached to brackets would
    make every cited paragraph differ.
    """
    stripped = re.sub(r"\[[^\]]{0,40}\]|\{[^}]{0,80}\}", " ", _LIST_MARK.sub("", text))
    return re.sub(r"[^0-9a-z가-힣]+", "", stripped.lower())


def _nums(text: str) -> list[str]:
    """The numbers a reader would care about, citation markers excluded.

    Formatting never changes a number. 44.7 becoming 61.2 is a result changing,
    and it is a four-character edit inside a long paragraph — close enough on
    wording alone to fold, which is the one thing that must never happen here.
    Brackets go first because `[@lam2024]` renders as `[6]` and that IS
    formatting.
    """
    return re.findall(
        r"\d+(?:[.,]\d+)*",
        re.sub(r"\[[^\]]{0,40}\]|\{[^}]{0,80}\}", " ", _LIST_MARK.sub("", text)))


def _fold_rerenderings(
    missing: list[str], per_section: list[dict],
) -> tuple[list[tuple[str, str]], list[str], list[dict]]:
    """Pair each submission-only paragraph with a section-only one that says the
    same thing, and take both out of the difference lists.

    Matched on words alone, at 0.92 — high enough that a real edit (a changed
    number, an added clause) stays a difference, low enough to absorb what
    formatting does. The pairs are RETURNED, not dropped: a tool that quietly
    decides 43 of your 70 findings were noise has to show its work.
    """
    from difflib import SequenceMatcher
    pool = []
    for sec in per_section:
        for raw in sec["not_in_submission"]:
            pool.append((sec, raw, _words(raw)))

    pairs, kept, used = [], [], set()
    for raw in missing:
        w = _words(raw)
        best, best_ratio = None, 0.0
        for i, (sec, other_raw, other_w) in enumerate(pool):
            if i in used or not w or not other_w:
                continue
            # Cheap reject before the expensive compare.
            if abs(len(w) - len(other_w)) > 0.25 * max(len(w), len(other_w)):
                continue
            ratio = SequenceMatcher(None, w, other_w).ratio()
            if ratio > best_ratio:
                best, best_ratio, best_i = (sec, other_raw), ratio, i
        # Same numbers is a HARD condition, not part of the score: a changed
        # figure is a few characters inside a long paragraph and scores as a
        # re-rendering on wording alone.
        if best and best_ratio >= 0.92 and _nums(raw) == _nums(best[1]):
            used.add(best_i)
            pairs.append((raw, best[1]))
            sec = best[0]
            sec["not_in_submission"] = [r for r in sec["not_in_submission"]
                                        if r != best[1]]
            sec["not_in_submission_total"] -= 1
            sec["matched"] += 1
        else:
            kept.append(raw)
    return pairs, kept, per_section

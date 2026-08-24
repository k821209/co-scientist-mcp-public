"""Study documents — explainers written to be READ.

    doc:  projects/{pid}/studies/{study_id}
    blob: projects/{pid}/studies/{study_id}/page.html

Distinct from materials, and the one-line reason is the reporter's: a material
is what the PAPER refers to; a study is what a PERSON reads. The first needs
accuracy and traceability, the second needs readability and freshness, and one
drawer does not serve both — an HTML explainer filed as a material could only be
read by downloading it, so it ended up published twice, in two places, drifting.

There are TWO signals here and they are deliberately not the same word.

`stale` means something this document CITED has moved — strong, specific, and
the document is probably wrong.

`decisions_since` means something NEW was decided after this was written that
the document does not cite — weak, and it may well be irrelevant. It exists
because the first signal only catches "what I quoted changed" and not "what was
decided next overturns what I wrote". A study's tables can stay perfectly
correct while the way to read them reverses (feedback 47c76a000302).

Crucially it is DERIVED, like the first one. Being told which studies a decision
affects would work only when someone remembers to say so, and this whole feature
exists to not depend on that.

The load-bearing part is `sources`. An explainer carries tables of measured
values and those values move; the failure worth preventing is quoting one after
it changed. So a study records what it drew numbers from and when it last
looked, and staleness is DERIVED from that. It is never a flag someone sets:
a "mark as stale" button is the same memory that already failed.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

# What a document CLAIMS about itself. "Stale" is deliberately absent — it is
# computed, and a state you must remember to set is a state that lies.
STATUSES = {
    "confirmed": "the numbers and claims here are settled",
    "provisional": "written down, but something in it is not yet established",
}
DEFAULT_STATUS = "provisional"

SOURCE_KINDS = ("analysis", "decision", "graph", "paper", "run")


def _studies_col(state: State) -> str:
    return state.project_path("studies")


def _study_path(state: State, study_id: str) -> str:
    return state.project_path("studies", study_id)


def _require(state: State, study_id: str) -> dict:
    doc = state.backend.get_doc(_study_path(state, study_id))
    if doc is None:
        raise NotFound(f"study {study_id!r} not found")
    return doc


def _check_status(status: str | None) -> str:
    s = (status or DEFAULT_STATUS).strip().lower()
    if s not in STATUSES:
        raise ValueError(
            f"unknown status {status!r}. One of: "
            + ", ".join(f"{k} ({v})" for k, v in STATUSES.items())
            + ". 'stale' is not a status — it is computed from `sources`."
        )
    return s


def _norm_sources(state: State, sources: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for i, raw in enumerate(sources or []):
        if not isinstance(raw, dict):
            raise ValueError(f"source #{i + 1} is not an object: {raw!r}")
        kind = str(raw.get("kind") or "").strip().lower()
        ref = str(raw.get("ref") or "").strip()
        if kind not in SOURCE_KINDS:
            raise ValueError(
                f"source #{i + 1}: unknown kind {raw.get('kind')!r}. "
                f"One of: {', '.join(SOURCE_KINDS)}"
            )
        if not ref:
            raise ValueError(f"source #{i + 1}: ref is required")
        out.append({
            "kind": kind,
            "ref": ref,
            "label": (raw.get("label") or "").strip() or None,
            # Stamped now: recording a source means "I have just read it".
            "seen_at": raw.get("seen_at") or now_iso(),
        })
    return out


def write_study(
    state: State,
    *,
    title: str,
    html: str,
    summary: str | None = None,
    status: str | None = None,
    sources: list[dict] | None = None,
    follows: str | None = None,
) -> dict:
    """Publish an explainer that reads inline in the dashboard's Study tab.

    `summary` is for the READER — one or two sentences saying what this explains,
    shown in the list. It is not the place for your own caveats and reasoning;
    that is what a material's `ai_note` is for, and mixing them is why the two
    exist separately.

    `sources` is what the numbers came from:
    `[{"kind": "analysis", "ref": "mlm-eval", "label": "bits/bp"}]`. Recording
    one stamps "read now"; when that analysis is next updated the document shows
    as out of date, WITHOUT anyone having to remember.

    `follows` is the study this one continues, making a series that is listed in
    reading order.
    """
    if not (title or "").strip():
        raise ValueError("title is required")
    if not (html or "").strip():
        raise ValueError("html is required — a study is a document to read")
    st = _check_status(status)
    srcs = _norm_sources(state, sources)
    if follows:
        _require(state, follows)

    study_id = new_id()
    now = now_iso()
    blob_path = state.project_path("studies", study_id, "page.html")
    state.backend.put_blob(blob_path, html.encode("utf-8"))
    doc = {
        "study_id": study_id,
        "title": title.strip(),
        "summary": (summary or "").strip() or None,
        "status": st,
        "sources": srcs,
        "follows": follows or None,
        "blob_path": blob_path,
        "size_bytes": len(html.encode("utf-8")),
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(_study_path(state, study_id), doc)
    return {**doc, "dashboard_url": state.dashboard_url("study")}


def update_study(
    state: State,
    study_id: str,
    *,
    html: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    status: str | None = None,
    sources: list[dict] | None = None,
    follows: str | None = None,
) -> dict:
    """Amend a study. Passing `html` REPLACES the document and re-stamps every
    source as read now — rewriting the tables is exactly the act that makes them
    current again, so it would be wrong to leave the document flagged stale
    afterwards, and worse to make someone clear it by hand."""
    doc = _require(state, study_id)
    fields: dict = {"updated_at": now_iso()}
    if title is not None:
        fields["title"] = title.strip()
    if summary is not None:
        fields["summary"] = summary.strip() or None
    if status is not None:
        fields["status"] = _check_status(status)
    if follows is not None:
        if follows:
            _require(state, follows)
            if follows == study_id:
                raise ValueError("a study cannot follow itself")
        fields["follows"] = follows or None
    if sources is not None:
        fields["sources"] = _norm_sources(state, sources)
    if html is not None:
        state.backend.put_blob(doc["blob_path"], html.encode("utf-8"))
        fields["size_bytes"] = len(html.encode("utf-8"))
        if sources is None:
            now = now_iso()
            fields["sources"] = [{**s, "seen_at": now} for s in (doc.get("sources") or [])]
    state.backend.update_doc(_study_path(state, study_id), fields)
    return {**doc, **fields, "dashboard_url": state.dashboard_url("study")}


def _source_clock(state: State) -> dict[str, str]:
    """When each referable thing last moved, keyed "<kind>:<ref>".

    Best-effort per kind: a lookup that fails leaves that source UNKNOWN rather
    than stale, because crying wolf on every document is how a freshness signal
    stops being read."""
    clock: dict[str, str] = {}

    def stamp(kind: str, ref: str, when) -> None:
        if ref and when:
            clock[f"{kind}:{ref}"] = str(when)

    try:
        for _, d in state.backend.list_collection(state.project_path("decisions")):
            # A REVERSED decision is a changed decision. `decided_at` does not
            # move when one is superseded, so a document citing it would have
            # stayed fresh while the thing it cites had been overturned — the
            # exact failure this is meant to catch, one level down.
            stamp("decision", d.get("decision_id", ""),
                  max(str(d.get("decided_at") or ""),
                      str(d.get("superseded_at") or "")) or None)
    except Exception:
        pass
    try:
        for _, d in state.backend.list_collection(state.project_path("materials")):
            stamp("graph", d.get("material_id", ""), d.get("updated_at"))
    except Exception:
        pass
    try:
        from . import papers as _papers
        for _, paper in state.backend.list_collection(state.project_path("papers")):
            slug = paper.get("slug")
            if not slug:
                continue
            stamp("paper", slug, paper.get("updated_at"))
            for _, a in state.backend.list_collection(
                    state.project_path("papers", slug, "analyses")):
                stamp("analysis", a.get("name", ""), a.get("updated_at"))
        del _papers
    except Exception:
        pass
    return clock


def _moved(study: dict, clock: dict[str, str]) -> list[dict]:
    out = []
    for s in study.get("sources") or []:
        now = clock.get(f"{s.get('kind')}:{s.get('ref')}")
        if not now:
            continue                       # unknown, not stale
        # No seen_at means it was never read; that is not the same as current.
        if not s.get("seen_at") or now > s["seen_at"]:
            out.append({**s, "source_updated_at": now})
    return out


def _decisions_since(state: State, study: dict, decisions: list[dict]) -> list[dict]:
    """Decisions recorded after this was written that it does not cite.

    Not staleness — a prompt to look. The document may be untouched by any of
    them, and that judgement is a person's. What it removes is having to
    remember that anything happened at all."""
    written = study.get("updated_at") or study.get("created_at") or ""
    cited = {s.get("ref") for s in (study.get("sources") or [])
             if s.get("kind") == "decision"}
    out = []
    for d in decisions:
        did = d.get("decision_id")
        when = d.get("decided_at") or ""
        if not did or did in cited or not when or when <= written:
            continue
        out.append({"decision_id": did, "text": d.get("text"),
                    "decided_at": when,
                    "supersedes": d.get("supersedes")})
    out.sort(key=lambda x: x["decided_at"], reverse=True)
    return out


def list_studies(state: State) -> list[dict]:
    """Every study, with two DIFFERENT signals — do not read them as one.

    `stale` — something this document CITED has moved. Strong: the numbers in
    it probably no longer say what the source says. Read it before quoting.

    `decisions_since` — decisions recorded after this was written that it does
    not cite. Weak, and often irrelevant: a prompt to re-read, not a verdict.
    It is here because `stale` only catches "what I quoted changed" and misses
    "what was decided next reversed how to read it" — the tables stay correct
    while the interpretation inverts."""
    clock = _source_clock(state)
    try:
        decisions = [d for _, d in state.backend.list_collection(
            state.project_path("decisions"))]
    except Exception:
        decisions = []
    rows = [d for _, d in state.backend.list_collection(_studies_col(state))]
    rows.sort(key=lambda r: r.get("created_at") or "")
    out = []
    for r in rows:
        moved = _moved(r, clock)
        since = _decisions_since(state, r, decisions)
        out.append({
            **{k: v for k, v in r.items() if k != "blob_path"},
            "stale": bool(moved),
            "stale_sources": moved,
            "decisions_since": since,
            "decisions_since_count": len(since),
            "url": f"{state.dashboard_url('study')}?doc={r.get('study_id')}",
        })
    return out


def read_study(state: State, study_id: str) -> dict:
    """A study's metadata and its HTML."""
    doc = _require(state, study_id)
    blob = state.backend.get_blob(doc.get("blob_path") or "")
    moved = _moved(doc, _source_clock(state))
    try:
        decisions = [d for _, d in state.backend.list_collection(
            state.project_path("decisions"))]
    except Exception:
        decisions = []
    since = _decisions_since(state, doc, decisions)
    return {
        **{k: v for k, v in doc.items() if k != "blob_path"},
        "html": blob.decode("utf-8", errors="replace") if blob else "",
        "stale": bool(moved),
        "stale_sources": moved,
        "decisions_since": since,
        "decisions_since_count": len(since),
    }


def delete_study(state: State, study_id: str) -> bool:
    doc = state.backend.get_doc(_study_path(state, study_id))
    if doc is None:
        return False
    if doc.get("blob_path"):
        state.backend.delete_blob(doc["blob_path"])
    state.backend.delete_doc(_study_path(state, study_id))
    return True

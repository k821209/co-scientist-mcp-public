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

import re

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

# Who the agent is, when it answers or asks. Same string discussion.py uses.
AGENT_NAME = "Claude Code"

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


_CDATA_OPEN = "<![CDATA["
_CDATA_CLOSE = "]]>"


def _unwrap_cdata(html: str) -> str:
    """A `<![CDATA[ … ]]>` wrapper around the whole document is stripped.

    An HTML parser reads `<!` as a bogus comment that swallows up to the
    first `>` — the closing bracket of the `<style>` that follows — so the
    stylesheet spills onto the page as text and `]]>` is left at the end,
    while the write reports success (feedback 160481377be0). The intent is
    unambiguous and the recovery lossless, so it is unwrapped rather than
    refused."""
    s = html.strip()
    if s.startswith(_CDATA_OPEN) and s.endswith(_CDATA_CLOSE):
        return s[len(_CDATA_OPEN):-len(_CDATA_CLOSE)].strip()
    return html


def static_checks(html: str) -> list[str]:
    """What a browser would show wrong, found without one: the checks that
    stand in for the screenshot when no headless browser is installed."""
    problems: list[str] = []
    s = html.strip()
    if _CDATA_OPEN in s or _CDATA_CLOSE in s:
        problems.append("a CDATA marker is in the document — HTML parsers read <! as a comment "
                        "that swallows the next tag; the stylesheet will print as text")
    if "&lt;" in s and s.count("&lt;") > s.count("<") // 2:
        problems.append("escaped tags (&lt;…&gt;) outnumber real ones — the markup renders as visible text")
    opens, closes = len(re.findall(r"<style\b", s, re.I)), len(re.findall(r"</style>", s, re.I))
    if opens != closes:
        problems.append(f"<style> open/close mismatch ({opens} open, {closes} close) — CSS will print as text or styles will not apply")
    opens, closes = len(re.findall(r"<script\b", s, re.I)), len(re.findall(r"</script>", s, re.I))
    if opens != closes:
        problems.append(f"<script> open/close mismatch ({opens} open, {closes} close)")
    if re.search(r"<!--(?:(?!-->).)*$", s, re.S):
        problems.append("an HTML comment is opened and never closed — everything after it is hidden")
    return problems


def write_study(
    state: State,
    *,
    title: str,
    html: str,
    summary: str | None = None,
    status: str | None = None,
    sources: list[dict] | None = None,
    follows: str | None = None,
    study_id: str | None = None,
) -> dict:
    """Publish an explainer that reads inline in the dashboard's Study tab.

    Pass `study_id` to REPLACE an existing study in place. Without it, fixing a
    typo meant writing a new document and deleting the old one, which broke any
    `follows` chain pointing at it and changed its URL.

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
    # Double-escaped HTML is accepted silently and renders as visible tags. It
    # is only ever noticed by a human opening the tab, so it is refused here.
    html = _unwrap_cdata(html)
    if "&lt;" in html and "<" not in html:
        raise ValueError(
            "html looks HTML-escaped: it contains '&lt;' and no '<', so the "
            "tags would render as visible text. Pass the markup itself.")
    st = _check_status(status)
    srcs = _norm_sources(state, sources)
    if follows:
        _require(state, follows)

    existing = _require(state, study_id) if study_id else None
    study_id = study_id or new_id()
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
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
        # When the DOCUMENT last changed, as opposed to any field on it — the
        # clock a derived copy (published_as) is measured against.
        "html_updated_at": now,
        "published_as": (existing or {}).get("published_as"),
    }
    state.backend.set_doc(_study_path(state, study_id), doc)
    out = {**doc, "dashboard_url": state.dashboard_url("study")}
    _warn_published_behind(out)
    return out


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
        html = _unwrap_cdata(html)
        state.backend.put_blob(doc["blob_path"], html.encode("utf-8"))
        fields["size_bytes"] = len(html.encode("utf-8"))
        fields["html_updated_at"] = fields["updated_at"]
        if sources is None:
            now = now_iso()
            fields["sources"] = [{**s, "seen_at": now} for s in (doc.get("sources") or [])]
    state.backend.update_doc(_study_path(state, study_id), fields)
    out = {**doc, **fields, "dashboard_url": state.dashboard_url("study")}
    _warn_published_behind(out)
    return out


def published_behind(doc: dict) -> bool:
    """A derived copy (a standalone page) recorded on this study is older than the
    document's html. The staleness machinery used to stop at the study's own
    edge: the copy the skill told the agent to publish got none of it, and a
    study rewritten twice in an hour left a published copy saying things the study
    no longer said, with nothing anywhere recording that (feedback
    f4d8b5471e13)."""
    pub = doc.get("published_as") or {}
    at = pub.get("at")
    html_at = doc.get("html_updated_at") or doc.get("updated_at")
    return bool(pub.get("url")) and bool(at) and bool(html_at) and html_at > at


def _warn_published_behind(out: dict) -> None:
    if published_behind(out):
        pub = out["published_as"]
        out.setdefault("warnings", []).append(
            f"this study has a published copy ({pub['url']}, recorded {pub['at']}) "
            f"that is now BEHIND the document. Republish it and record the new "
            f"copy with mark_study_published, or unlink it — a reader following "
            f"the link gets the superseded version.")


def mark_study_published(state: State, study_id: str, url: str | None) -> dict:
    """Record (or, with url=None, forget) the standalone copy of this study —
    a publish_page URL or any host's page. From then on, a write to the study that leaves the copy
    behind says so, and list_studies shows it."""
    doc = _require(state, study_id)
    fields: dict = {"updated_at": now_iso()}
    if url:
        fields["published_as"] = {"url": url.strip(), "at": fields["updated_at"]}
    else:
        fields["published_as"] = None
    state.backend.update_doc(_study_path(state, study_id), fields)
    return {**doc, **fields, "published_behind": False}


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
            "published_behind": published_behind(r),
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
        "published_behind": published_behind(doc),
    }


def delete_study(state: State, study_id: str) -> bool:
    doc = state.backend.get_doc(_study_path(state, study_id))
    if doc is None:
        return False
    if doc.get("blob_path"):
        state.backend.delete_blob(doc["blob_path"])
    state.backend.delete_doc(_study_path(state, study_id))
    return True


# ── questions on a study ─────────────────────────────────────────────────────
# A paper gets COMMENTS: each one is a defect with a fix, and the loop closes
# when the prose changes. A study is written to be READ, and what a reader
# leaves on it is a QUESTION — "why does this hold?", "where is this number
# from?" — whose answer may not change the document at all (user, 2026-10-29).
# Resolving it like a comment would force every answer to look like an edit.
#
# So: question → answer, with `changed_study` saying whether the document moved.
# An answer that did not change it is a complete answer; one that should have is
# the thing a reader can now see.
#
# Both directions, because the asymmetry is the point on this surface: the
# reader asks what the explainer did not explain, and the agent asks what it
# could not settle — the uncertainty belongs beside the passage, not in a
# session that has ended.

QUESTION_SOURCES = ("user", "ai")


def _questions_col(state: State, study_id: str) -> str:
    return state.project_path("studies", study_id, "questions")


def _question_path(state: State, study_id: str, question_id: str) -> str:
    return state.project_path("studies", study_id, "questions", question_id)


def _refresh_open_count(state: State, study_id: str) -> int:
    """Stamp the study doc with how many questions are open, and return it.

    Denormalised ON PURPOSE, and RECOMPUTED rather than incremented: the
    dashboard lists studies from one collection and needs the badge without a
    collection-group query (which needs an explicit index — the kind whose
    absence once hid 148 open runs), and a counter that is added to drifts the
    first time a write is retried.
    """
    rows = state.backend.list_collection(_questions_col(state, study_id))
    n = sum(1 for _, q in rows if (q.get("status") or "open") == "open")
    try:
        state.backend.update_doc(_study_path(state, study_id), {"open_questions": n})
    except NotFound:
        pass
    return n


def ask_study_question(
    state: State,
    study_id: str,
    *,
    question: str,
    quote: str | None = None,
    block_index: int | None = None,
    source: str = "ai",
    asked_by: str | None = None,
) -> dict:
    """Ask a question about a study — the agent's own, by default.

    `quote` is the passage it is about. The study renders in a sandboxed frame
    with no same-origin, deliberately, so the dashboard cannot read a selection
    out of it; the reader picks a paragraph instead and `quote` carries its
    text. Keep the quote SHORT (a sentence): it is an anchor, and the agent
    answering reads the document anyway.
    """
    _require(state, study_id)
    text = (question or "").strip()
    if not text:
        raise ValueError("question is required")
    if source not in QUESTION_SOURCES:
        raise ValueError(f"source must be one of {QUESTION_SOURCES}")
    qid = new_id()
    doc = {
        "question_id": qid,
        "study_id": study_id,
        "question": text,
        "quote": (quote or "").strip() or None,
        "block_index": block_index,
        "source": source,
        "asked_by": (asked_by or "").strip() or (AGENT_NAME if source == "ai" else "User"),
        "status": "open",
        "answer": None,
        "answered_at": None,
        "answered_by": None,
        "changed_study": None,
        "created_at": now_iso(),
    }
    state.backend.set_doc(_question_path(state, study_id, qid), doc)
    doc["open_questions"] = _refresh_open_count(state, study_id)
    return doc


def list_study_questions(
    state: State,
    study_id: str | None = None,
    *,
    status: str | None = "open",
) -> list[dict]:
    """Questions on one study, or on every study in the project.

    Newest first, each carrying the study's title — a question read without
    knowing which document it is about sends you to the wrong one. `status`
    None returns answered ones too.
    """
    if status not in (None, "open", "answered"):
        raise ValueError("status must be 'open', 'answered' or None")
    ids = ([study_id] if study_id
           else [sid for sid, _ in state.backend.list_collection(_studies_col(state))])
    out: list[dict] = []
    for sid in ids:
        study = state.backend.get_doc(_study_path(state, sid))
        if study is None:
            if study_id:
                raise NotFound(f"study {sid!r} not found")
            continue
        for _, q in state.backend.list_collection(_questions_col(state, sid)):
            if status and (q.get("status") or "open") != status:
                continue
            out.append({**q, "study_title": study.get("title")})
    out.sort(key=lambda q: q.get("created_at") or "", reverse=True)
    return out


def answer_study_question(
    state: State,
    study_id: str,
    question_id: str,
    *,
    answer: str,
    changed_study: bool = False,
) -> dict:
    """Answer a question, and say whether the document itself moved.

    `changed_study=False` is a real answer, not a lesser one: a reader asking
    "where is this number from?" is owed the provenance, and the study may be
    right as written. But say so — the reader cannot tell from the answer alone
    whether the explainer still needs reading again. If the answer reveals the
    explainer WAS unclear, revise it with `update_study` and pass True.
    """
    path = _question_path(state, study_id, question_id)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(
            f"question {question_id!r} not found on study {study_id!r} — "
            "list_study_questions(study_id) shows the open ones")
    body = (answer or "").strip()
    if not body:
        raise ValueError(
            "answer is required — an empty answer closes the question without "
            "answering it, which is the one outcome the reader cannot see")
    now = now_iso()
    fields = {
        "answer": body,
        "status": "answered",
        "answered_at": now,
        "answered_by": AGENT_NAME,
        "changed_study": bool(changed_study),
    }
    state.backend.update_doc(path, fields)
    out = {**existing, **fields,
           "open_questions": _refresh_open_count(state, study_id)}
    if not changed_study:
        out["note"] = ("answered without changing the study — if the question "
                       "exposed an unclear passage, revise it with update_study "
                       "and answer again with changed_study=True")
    return out


def count_open_study_questions(state: State) -> dict:
    """Open questions, split by who asked. Mirrors count_open_user_comments for
    the session-start protocol.

    Split because the two mean different things: a reader's question is work
    waiting for the agent, and the agent's own question is work waiting for the
    reader. One number would have the session nag itself.
    """
    rows = list_study_questions(state, status="open")
    return {
        "from_reader": sum(1 for q in rows if q.get("source") != "ai"),
        "from_agent": sum(1 for q in rows if q.get("source") == "ai"),
        "total": len(rows),
        "studies": sorted({q["study_id"] for q in rows}),
    }

"""Discussion: comments on a drawn graph, and the decisions that came out.

    doc: projects/{pid}/discussion_comments/{comment_id}
    doc: projects/{pid}/decisions/{decision_id}

The loop this exists for is: draw the thing, argue about it, write down what was
settled. The agent is a participant, not a spectator — it reads the graph, it
can answer a question in the thread, and it can record what the discussion
decided.

Two shapes, deliberately different:

  comments  attach to ONE graph. They are about the drawing in front of you and
            they stop mattering once the question is settled.
  decisions attach to the PROJECT, with a pointer back to the graph that
            produced them. A decision outlives the diagram that occasioned it;
            filing it under the drawing would bury it there.

A superseded decision is never deleted. The dangerous entry in a record of
decisions is not a wrong one — it is one everybody still believes.
"""
from __future__ import annotations

import re

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

AGENT_NAME = "Claude Code"

# Words that appear in every decision and tell you nothing about which prose it
# governs. Deliberately short: a stopword list that grows starts deciding which
# decisions are important.
_STOP = {
    "that", "this", "with", "from", "have", "will", "shall", "should", "would",
    "about", "there", "their", "which", "where", "while", "than", "then",
    "paper", "section", "sections", "make", "makes", "made", "keep", "keeps",
    "only", "also", "into", "onto", "over", "under", "between", "because",
    "does", "doing", "done", "been", "being", "must", "could", "같은", "대한",
    "그리고", "하지만", "때문에", "한다", "하는", "있는", "없는",
    # Korean grammar that the word pattern picks up as words of its own when
    # it follows code or Latin text ("`settings.json`에서"): particles and
    # auxiliaries, not subjects. Every section of every Korean document has
    # them, and with these in the terms a decision about a harness setting
    # "matched" five sections of a paper about refunds (feedback 7714d8f63c2e).
    "에서", "으로", "에게", "까지", "부터", "이다", "있다", "없다", "된다", "않는",
    "않는다", "없이", "또는", "것은", "것이", "위해", "대해", "통해", "따라",
    "경우", "때문", "그대로",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\uac00-\ud7a3]{2,}")
# A noun and the particle stuck to it are one word in Korean: "파일에",
# "파일을", "파일의". Left whole, the decision's "파일에" does not find the
# section's "파일을". Cut back to the stem when at least two syllables remain.
_PARTICLES = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "하고", "하며",
              "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만")


def _stem(word: str) -> str:
    if not ("\uac00" <= word[-1] <= "\ud7a3"):
        return word
    for particle in _PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def decision_terms(*parts: str | None) -> set[str]:
    """The distinctive words of a decision — what to look for in the prose.

    Latin words of four characters or more and Hangul runs of two or more; the
    rest of a sentence is grammar. Lowercased, so the match is case-blind.
    """
    out: set[str] = set()
    for part in parts:
        for word in _WORD_RE.findall(part or ""):
            low = word.lower()
            if low in _STOP:
                continue
            stem = _stem(low)
            if stem not in _STOP:
                out.add(stem)
    return out


def _section_hits(body: str, terms: set[str]) -> list[str]:
    low = (body or "").lower()
    return sorted(t for t in terms if t in low)


# A section "discusses" a decision when it shares at least this many of the
# words of the decision ITSELF — not of its rationale, which is a paragraph of
# explanation and shares a word or two with anything.
_MIN_SHARED = 2
# …and a word that most of the sections under comparison contain says nothing
# about any one of them. Judged only when there are enough sections to judge.
_COMMON_SHARE = 1 / 3
_COMMON_FLOOR = 6


def sections_discussing(bodies: dict, *, text: str, rationale: str | None = None) -> dict:
    """Which of `bodies` ({key: text}) talk about what a decision is about.

    Returns {key: [the shared words, the decision's own first]} for the ones
    that do. One shared word used to be enough, and the words were whatever
    the pattern caught: every section came back, which is the same as none.
    """
    own = decision_terms(text)
    wider = decision_terms(rationale) - own
    if not own:
        return {}
    lowered = {key: (body or "").lower() for key, body in bodies.items()}
    if len(lowered) >= _COMMON_FLOOR:
        ceiling = len(lowered) * _COMMON_SHARE
        common = {t for t in own | wider
                  if sum(1 for low in lowered.values() if t in low) > ceiling}
        own, wider = own - common, wider - common
    need = min(_MIN_SHARED, len(own))
    if not need:
        return {}
    out = {}
    for key, low in lowered.items():
        shared = sorted(t for t in own if t in low)
        if len(shared) >= need:
            out[key] = shared + sorted(t for t in wider if t in low)
    return out


# A decision is about the paper you are writing, so the scan starts at the most
# recently touched papers rather than every paper in the project — the cost of
# this reply has to stay flat as a project accumulates papers.
_SCAN_PAPERS = 3
_SCAN_SECTIONS = 200


def sections_to_review(
    state: State,
    *,
    text: str,
    rationale: str | None = None,
    decided_at: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Sections that talk about what was just decided and predate the decision.

    `record_decision` already returns `studies_to_review`, and `list_studies`
    computes `decisions_since`, because a decision is not self-enforcing — the
    system has to re-surface it against the artifacts it might now contradict.
    The manuscript, the artifact decisions are overwhelmingly ABOUT, got none
    of that: no sections_to_review, no decisions_since on a section, no check
    in any lint. So a decision could be recorded and prose contradicting it
    written twenty minutes later, in the same session, and every tool returned
    success (feedback 0408a9a45b3b).

    What this can and cannot do: no regex sees that a sentence is "a
    performance claim from transformer training". Naming the paragraphs that
    discuss the decision's own subject is enough — the agent can then read
    them, which is the step that was never prompted.
    """
    if not decision_terms(text):
        return []
    rows: list[dict] = []
    try:
        from . import papers as _papers
        from . import sections as _sections
        paper_list = _papers.list_papers(state)[:_SCAN_PAPERS]
        seen = 0
        found: dict[tuple, dict] = {}
        bodies: dict[tuple, str] = {}
        for paper in paper_list:
            slug = paper.get("slug")
            if not slug:
                continue
            for sec in _sections.list_sections(state, slug):
                seen += 1
                if seen > _SCAN_SECTIONS:
                    break
                if not (sec.get("word_count") or 0):
                    continue
                body = sec.get("body")
                if body is None:
                    full = _sections.get_section(state, slug, sec.get("key", ""))
                    body = (full or {}).get("body") or ""
                found[(slug, sec.get("key"))] = sec
                bodies[(slug, sec.get("key"))] = body
        # Judged together: which words are common is a fact about all of them.
        for (slug, key), hits in sections_discussing(bodies, text=text, rationale=rationale).items():
            sec = found[(slug, key)]
            updated = sec.get("updated_at") or ""
            rows.append({
                "paper": slug,
                "section": key,
                "title": sec.get("title"),
                "word_count": sec.get("word_count"),
                "updated_at": updated or None,
                # False only when the section was edited AFTER the decision
                # — then somebody has already had the chance to apply it.
                "written_before_this_decision": bool(
                    decided_at and updated and updated < decided_at),
                "mentions": hits[:6],
            })
    except Exception:
        return []
    rows.sort(key=lambda r: (-len(r["mentions"]), r.get("updated_at") or ""))
    return rows[:limit]



def _comments_col(state: State) -> str:
    return state.project_path("discussion_comments")


def _comment_path(state: State, cid: str) -> str:
    return state.project_path("discussion_comments", cid)


def _decisions_col(state: State) -> str:
    return state.project_path("decisions")


def _decision_path(state: State, did: str) -> str:
    return state.project_path("decisions", did)


# ─────────────────────────── comments ───────────────────────────


def list_discussion(state: State, graph_id: str | None = None) -> list[dict]:
    """Comments, oldest first. Pass `graph_id` for one graph's thread."""
    rows = [d for _, d in state.backend.list_collection(_comments_col(state))]
    if graph_id:
        rows = [r for r in rows if r.get("graph_id") == graph_id]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return rows


def post_comment(
    state: State, *, graph_id: str, body: str, parent_id: str | None = None,
) -> dict:
    """Add a comment, or a reply when `parent_id` is given."""
    text = (body or "").strip()
    if not text:
        raise ValueError("body is required")
    if not (graph_id or "").strip():
        raise ValueError("graph_id is required — a comment is about a graph")
    if parent_id and state.backend.get_doc(_comment_path(state, parent_id)) is None:
        # Refused rather than silently promoted to a top-level comment: a reply
        # that lost its question reads as a statement nobody asked for.
        raise NotFound(f"comment {parent_id!r} not found — cannot reply to it")
    cid = new_id()
    doc = {
        "comment_id": cid,
        "graph_id": graph_id,
        "parent_id": parent_id or None,
        "body": text,
        "author_name": AGENT_NAME,
        "author_kind": "agent",
        "created_at": now_iso(),
    }
    state.backend.set_doc(_comment_path(state, cid), doc)
    return {**doc, "dashboard_url": state.dashboard_url("discussion")}


# ─────────────────────────── decisions ───────────────────────────


def list_decisions(state: State, *, include_superseded: bool = False) -> list[dict]:
    """Decisions that still hold, newest first.

    `include_superseded=True` adds the reversed ones, each carrying
    `superseded_by`. Read this at session start: it is the standing record of
    what the project has already settled, and re-opening a settled question is
    the most expensive thing an agent can do here."""
    rows = [d for _, d in state.backend.list_collection(_decisions_col(state))]
    if not include_superseded:
        rows = [r for r in rows if not r.get("superseded_by")]
    rows.sort(key=lambda r: r.get("decided_at") or "", reverse=True)
    return rows


def record_decision(
    state: State,
    *,
    text: str,
    rationale: str | None = None,
    from_graph: str | None = None,
    supersedes: str | None = None,
) -> dict:
    """Write down what was decided.

    `rationale` is the one line that is worth having in a year — the decision
    says WHAT, the rationale says why the alternatives lost.

    `supersedes` reverses an earlier decision. The old one is kept and marked,
    never deleted: a bulletin that can quietly lose an entry is a bulletin
    nobody can rely on."""
    body = (text or "").strip()
    if not body:
        raise ValueError("text is required")
    old = None
    if supersedes:
        old = state.backend.get_doc(_decision_path(state, supersedes))
        if old is None:
            raise NotFound(f"decision {supersedes!r} not found")
        if old.get("superseded_by"):
            raise ValueError(
                f"decision {supersedes!r} was already superseded by "
                f"{old['superseded_by']!r} — supersede that one instead, so the "
                "chain stays followable"
            )
    did = new_id()
    now = now_iso()
    doc = {
        "decision_id": did,
        "text": body,
        "rationale": (rationale or "").strip() or None,
        "from_graph": from_graph or None,
        "supersedes": supersedes or None,
        "superseded_by": None,
        "superseded_at": None,
        "decided_by": AGENT_NAME,
        "decided_at": now,
    }
    state.backend.set_doc(_decision_path(state, did), doc)
    if old is not None:
        state.backend.update_doc(_decision_path(state, supersedes), {
            "superseded_by": did, "superseded_at": now,
        })
    # Reversing a decision makes every study that cited it out of date. That
    # already shows up in `list_studies`, but saying it HERE puts it in front of
    # whoever just did the reversing, which is the one moment they can act on
    # it without being told twice.
    affected = []
    try:
        from . import studies as _studies
        for st in _studies.list_studies(state):
            if st.get("stale") or st.get("decisions_since_count"):
                affected.append({
                    "study_id": st.get("study_id"), "title": st.get("title"),
                    "stale": bool(st.get("stale")),
                    "decisions_since_count": st.get("decisions_since_count", 0),
                })
    except Exception:
        affected = []
    # The same idea as studies_to_review, for the surface that had nothing: the
    # paragraphs this decision governs, named at the one moment the person is
    # thinking about it.
    try:
        sections = sections_to_review(state, text=body, rationale=rationale,
                                      decided_at=now)
    except Exception:
        sections = []
    return {**doc, "studies_to_review": affected,
            "sections_to_review": sections,
            "sections_to_review_note": (
                "sections that discuss what this decision is about and were "
                "written before it — read them against the decision now; "
                "nothing checks the prose for you"
            ) if sections else None,
            "dashboard_url": state.dashboard_url("discussion")}


def get_decision(state: State, decision_id: str) -> dict:
    doc = state.backend.get_doc(_decision_path(state, decision_id))
    if doc is None:
        raise NotFound(f"decision {decision_id!r} not found")
    return doc

"""References: bibliographic records + CrossRef DOI verification.

Paths:
    doc: projects/{pid}/papers/{slug}/references/{citation_key}

`citation_key` is the natural key (e.g. "smith2024"). DOI resolution uses
CrossRef's public API (no auth, generous rate limit). Calls are made from
the local MCP — the cloud has nothing to do with them.

Two purposes for the CrossRef integration:
1. **Auto-populate** (`add_reference_by_doi`): pull title/authors/journal/
   year from CrossRef so the agent doesn't have to invent them.
2. **Hallucination check** (`verify_doi`, `validate_references`): catch
   fake DOIs the LLM made up. If CrossRef returns 404, the citation is
   suspect.
"""
from __future__ import annotations

import json as _json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from .papers import _paper_path

_CROSSREF_BASE = "https://api.crossref.org/works/"
_CROSSREF_SEARCH = "https://api.crossref.org/works"
_CROSSREF_UA = "co-scientist-local/0.1 (mailto:dev@co-scientist.example)"


class DoiNotFound(Exception):
    """Raised when CrossRef cannot resolve a DOI (likely hallucinated)."""
    def __init__(self, doi: str) -> None:
        self.doi = doi
        super().__init__(f"CrossRef returned 404 for {doi!r} — likely a hallucinated DOI")


def search_works(
    state: State,
    *,
    query: str,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict]:
    """Search CrossRef for works matching `query`.

    Returns normalized metadata using the same shape as `verify_doi`
    (title / abstract / subjects / authors / year / journal / url / doi).
    Up to `limit` results, optionally filtered by publication year range.
    Pure read — no Firestore writes. Use this from /literature-review to
    get candidates the agent can then `add_reference_by_doi` after the
    user picks.
    """
    del state  # network-only — no state needed, but keep signature symmetric
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(limit, 50))
    params: list[tuple[str, str]] = [
        ("query", query.strip()),
        ("rows", str(limit)),
        ("select", "DOI,title,author,container-title,issued,subject,abstract,URL,type"),
    ]
    filters: list[str] = []
    if year_from:
        filters.append(f"from-pub-date:{int(year_from)}")
    if year_to:
        filters.append(f"until-pub-date:{int(year_to)}")
    if filters:
        params.append(("filter", ",".join(filters)))
    url = _CROSSREF_SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _CROSSREF_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise RuntimeError(
            f"CrossRef HTTP {e.code} {e.reason or ''} for search {query!r}"
            + (f" — {body}" if body else "")
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"CrossRef network error: {e.reason}") from e
    items = (payload.get("message") or {}).get("items") or []
    return [_normalize_crossref(it, (it.get("DOI") or "")) for it in items]


def _fetch_crossref(doi: str, *, timeout: int = 15) -> dict:
    """Fetch CrossRef metadata for a DOI. Raises DoiNotFound on 404."""
    doi = (doi or "").strip().lstrip("/")
    # Strip a leading https://doi.org/ if the agent passes a URL.
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    if not doi:
        raise ValueError("doi is required")
    url = _CROSSREF_BASE + urllib.parse.quote(doi, safe="/")
    req = urllib.request.Request(url, headers={"User-Agent": _CROSSREF_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise DoiNotFound(doi) from None
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise RuntimeError(
            f"CrossRef HTTP {e.code} {e.reason or ''} for {doi!r}"
            + (f" — {body}" if body else "")
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"CrossRef network error for {doi!r}: {e.reason}") from e
    except TimeoutError as e:
        raise RuntimeError(f"CrossRef timeout ({timeout}s) for {doi!r}") from e
    msg = payload.get("message", {})
    return _normalize_crossref(msg, doi)


def _normalize_crossref(msg: dict, doi: str) -> dict:
    """Flatten CrossRef's response. Includes abstract + subjects so the
    agent can judge citation context without an extra round-trip."""
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else ""
    container = msg.get("container-title") or []
    journal = container[0] if container else None
    issued = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = issued[0][0] if issued and issued[0] else None
    authors = []
    for a in msg.get("author") or []:
        given = a.get("given") or ""
        family = a.get("family") or ""
        full = (given + " " + family).strip() or a.get("name") or ""
        if full:
            authors.append(full)
    abstract = msg.get("abstract") or ""
    # CrossRef abstracts arrive as JATS XML — strip tags so the agent sees plain text.
    if abstract:
        abstract = re.sub(r"<[^>]+>", " ", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip()
    return {
        "doi": (msg.get("DOI") or doi).lower(),
        "title": title,
        "abstract": abstract,
        "subjects": list(msg.get("subject") or []),
        "authors": authors,
        "journal": journal,
        "year": year,
        "url": msg.get("URL"),
        "type": msg.get("type"),
    }


def _derive_citation_key(meta: dict) -> str:
    """smith2024 from first-author surname + year. Fallback to last DOI segment."""
    authors = meta.get("authors") or []
    year = meta.get("year")
    if authors and year:
        surname = authors[0].split()[-1].lower()
        # Keep only letters (handle Korean/Cyrillic by falling back to ascii subset)
        surname_ascii = re.sub(r"[^a-z]", "", surname)
        if surname_ascii:
            return f"{surname_ascii}{year}"
    # Fallback: last DOI segment with non-alnum stripped
    doi = (meta.get("doi") or "").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", doi.lower()) or "ref"


def _ref_path(state: State, slug: str, citation_key: str) -> str:
    return state.project_path("papers", slug, "references", citation_key)


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


def add_reference(
    state: State,
    slug: str,
    *,
    citation_key: str,
    title: str,
    authors: list[str] | str | None = None,
    journal: str | None = None,
    year: int | None = None,
    doi: str | None = None,
    pmid: str | None = None,
    bibtex: str | None = None,
    cited_in: list[str] | None = None,
) -> dict:
    _ensure_paper(state, slug)
    if not citation_key or not citation_key.strip():
        raise ValueError("citation_key is required")
    path = _ref_path(state, slug, citation_key)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"reference {citation_key!r} already exists for {slug!r}")
    now = now_iso()
    doc = {
        "citation_key": citation_key,
        "title": title,
        "authors": list(authors) if isinstance(authors, list) else authors,
        "journal": journal,
        "year": year,
        "doi": doi,
        "pmid": pmid,
        "bibtex": bibtex,
        "cited_in": list(cited_in or []),
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def update_reference(
    state: State,
    slug: str,
    citation_key: str,
    *,
    title: str | None = None,
    authors: list[str] | str | None = None,
    journal: str | None = None,
    year: int | None = None,
    doi: str | None = None,
    pmid: str | None = None,
    bibtex: str | None = None,
    cited_in: list[str] | None = None,
) -> dict:
    _ensure_paper(state, slug)
    path = _ref_path(state, slug, citation_key)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"reference {citation_key!r} not found for {slug!r}")
    fields: dict = {"updated_at": now_iso()}
    if title is not None: fields["title"] = title
    if authors is not None: fields["authors"] = list(authors) if isinstance(authors, list) else authors
    if journal is not None: fields["journal"] = journal
    if year is not None: fields["year"] = year
    if doi is not None: fields["doi"] = doi
    if pmid is not None: fields["pmid"] = pmid
    if bibtex is not None: fields["bibtex"] = bibtex
    if cited_in is not None: fields["cited_in"] = list(cited_in)
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_reference(state: State, slug: str, citation_key: str) -> dict:
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_ref_path(state, slug, citation_key))
    if doc is None:
        raise NotFound(f"reference {citation_key!r} not found for {slug!r}")
    return doc


def list_references(state: State, slug: str) -> list[dict]:
    """List references ordered by citation_key (lexicographic — natural for bib lists)."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "references"))
    refs = [data for _, data in pairs]
    refs.sort(key=lambda r: r.get("citation_key", ""))
    return refs


def search_references(
    state: State,
    slug: str,
    *,
    doi: str | None = None,
    pmid: str | None = None,
    year: int | None = None,
    title_contains: str | None = None,
) -> list[dict]:
    """Field-equality + substring search. v0 scans all references (small N)."""
    refs = list_references(state, slug)
    if doi is not None:
        refs = [r for r in refs if r.get("doi") == doi]
    if pmid is not None:
        refs = [r for r in refs if r.get("pmid") == pmid]
    if year is not None:
        refs = [r for r in refs if r.get("year") == year]
    if title_contains:
        needle = title_contains.lower()
        refs = [r for r in refs if needle in (r.get("title", "") or "").lower()]
    return refs


def delete_reference(state: State, slug: str, citation_key: str) -> bool:
    """Delete a reference + cascade its verification finding (if any).

    The finding doc is keyed by DOI, so we read the reference's DOI before
    deleting the ref. Prevents zombie findings that survive the citation
    they were about and clutter the dashboard's ribbon UI.
    """
    _ensure_paper(state, slug)
    path = _ref_path(state, slug, citation_key)
    cur = state.backend.get_doc(path)
    if cur is None:
        return False
    doi = (cur.get("doi") or "").strip().lower()
    state.backend.delete_doc(path)
    if doi:
        from . import verification as _verification
        finding_path = _verification._finding_doc_path(
            state, slug, _verification._doi_safe_id(doi),
        )
        # Best-effort — silently skip if the finding doesn't exist.
        state.backend.delete_doc(finding_path)
    return True


# ─── CrossRef-backed DOI tools ───────────────────────────────────────────────


def verify_doi(state: State, doi: str) -> dict:
    """Resolve a DOI against CrossRef. Returns metadata if real, raises
    DoiNotFound if CrossRef has no record of it (likely hallucinated).

    No Firestore writes. Use this to spot-check a single citation before
    inserting it into a manuscript.
    """
    return _fetch_crossref(doi)


def add_reference_by_doi(
    state: State,
    slug: str,
    *,
    doi: str,
    citation_key: str | None = None,
    cited_in: list[str] | None = None,
) -> dict:
    """Fetch CrossRef metadata for `doi` and add the reference. Auto-derives
    citation_key from first-author surname + year if not given. Raises
    DoiNotFound if CrossRef returns 404 — refuse to store hallucinated DOIs.
    """
    _ensure_paper(state, slug)
    meta = _fetch_crossref(doi)
    key = citation_key or _derive_citation_key(meta)
    # If the derived key collides, append a letter (smith2024 → smith2024a, b, …).
    if state.backend.get_doc(_ref_path(state, slug, key)) is not None:
        for suffix in "abcdefghijklmnopqrstuvwxyz":
            cand = f"{key}{suffix}"
            if state.backend.get_doc(_ref_path(state, slug, cand)) is None:
                key = cand
                break
        else:
            raise ValueError(f"citation_key {key!r} exhausted (a–z all taken)")
    return add_reference(
        state, slug,
        citation_key=key,
        title=meta["title"],
        authors=meta["authors"],
        journal=meta["journal"],
        year=meta["year"],
        doi=meta["doi"],
        cited_in=cited_in,
    )


def enrich_reference_from_doi(state: State, slug: str, citation_key: str) -> dict:
    """For an existing reference that has a DOI but lacks metadata, fetch
    CrossRef and fill in missing fields (title, authors, journal, year).
    Does not overwrite existing non-empty fields.
    """
    _ensure_paper(state, slug)
    path = _ref_path(state, slug, citation_key)
    cur = state.backend.get_doc(path)
    if cur is None:
        raise NotFound(f"reference {citation_key!r} not found for {slug!r}")
    doi = cur.get("doi")
    if not doi:
        raise ValueError(f"reference {citation_key!r} has no DOI to enrich from")
    meta = _fetch_crossref(doi)
    fields: dict = {"updated_at": now_iso()}
    # Fill only blanks — never overwrite user-edited values.
    if not cur.get("title") and meta.get("title"):
        fields["title"] = meta["title"]
    if not cur.get("authors") and meta.get("authors"):
        fields["authors"] = meta["authors"]
    if not cur.get("journal") and meta.get("journal"):
        fields["journal"] = meta["journal"]
    if not cur.get("year") and meta.get("year"):
        fields["year"] = meta["year"]
    if len(fields) == 1:
        return cur  # nothing to add
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


_CONTEXT_WINDOW = 240  # chars before/after marker — enough to convey intent


def _extract_doi_contexts(state: State, slug: str) -> dict[str, list[dict]]:
    """For each {doi:X} marker in this paper's section bodies, capture
    enough surrounding text for the AGENT to judge citation correctness.

    Returns {doi_lower: [{
        "section": "<section_key>",
        "sentence": "<full surrounding sentence>",
        "context_before": "<up to 240 chars before the marker>",
        "context_after":  "<up to 240 chars after the marker>",
        "stacked_with": ["<other doi>", ...],  # DOIs in the same citation chunk
    }]}.

    The MCP doesn't decide whether the context fits the cited paper —
    that's the LLM agent's job. We just hand over the raw text the agent
    needs to read.
    """
    from . import sections as _sections
    contexts: dict[str, list[dict]] = {}
    secs = _sections.list_sections(state, slug)
    pattern = re.compile(r"\{doi:([^}\s]+)\}", re.IGNORECASE)
    for sec in secs:
        body = sec.get("body") or ""
        if not body:
            continue
        matches = list(pattern.finditer(body))
        for i, m in enumerate(matches):
            doi = m.group(1).lower()
            sentence = _sentence_around(body, m.start(), m.end())
            before = body[max(0, m.start() - _CONTEXT_WINDOW):m.start()]
            after = body[m.end():m.end() + _CONTEXT_WINDOW]
            stacked = _adjacent_dois(matches, i, body)
            contexts.setdefault(doi, []).append({
                "section": sec.get("key", ""),
                "sentence": sentence,
                "context_before": before,
                "context_after": after,
                "stacked_with": stacked,
            })
    return contexts


def _sentence_around(body: str, start: int, end: int) -> str:
    """Extract the sentence containing positions [start, end)."""
    s = start
    while s > 0 and body[s - 1] not in ".!?\n":
        s -= 1
    e = end
    while e < len(body) and body[e] not in ".!?\n":
        e += 1
    return body[s:e].strip()


_STACK_MAX_GAP = 80  # chars between adjacent stacked markers


def _adjacent_dois(matches: list[re.Match], i: int, body: str) -> list[str]:
    """Return DOIs of {doi:X} markers in the same 'stacked citation' as
    matches[i]. Two markers are stacked if no sentence-ending punctuation
    (.!?) sits between them AND the gap is short (≤80 chars). Captures
    'In humans {doi:A}, maize {doi:B}, and rice {doi:C}' as one chunk.
    """
    out: list[str] = []
    self_doi = matches[i].group(1).lower()

    def _gap_is_stacked(a_end: int, b_start: int) -> bool:
        gap = body[a_end:b_start]
        if len(gap) > _STACK_MAX_GAP:
            return False
        return not any(c in ".!?" for c in gap)

    # Walk backward
    j = i - 1
    while j >= 0 and _gap_is_stacked(matches[j].end(), matches[j + 1].start()):
        out.append(matches[j].group(1).lower())
        j -= 1
    # Walk forward
    j = i + 1
    while j < len(matches) and _gap_is_stacked(matches[j - 1].end(), matches[j].start()):
        out.append(matches[j].group(1).lower())
        j += 1
    return [d for d in out if d != self_doi]


def validate_references(state: State, slug: str) -> dict:
    """Gather everything the AGENT needs to judge whether each citation
    is correct. The MCP itself does NOT decide context fit — word-overlap
    is a bad proxy for "does this DOI belong to the claim". The agent has
    the manuscript + writing intent loaded; let it judge.

    Server emits only deterministic categories:
      - `missing_doi`  — reference doc with no DOI field at all
      - `unresolved`   — CrossRef returns 404 (almost surely hallucinated)
      - `errors`       — transient lookup failure

    Plus a `results` list, one entry per DOI (registered or inline-only),
    containing the full facts pack the agent needs:

      {
        "doi", "citation_key" (or None for inline-only),
        "doi_verified": True,
        "crossref": {title, abstract, subjects[], authors[], year, journal, type, url},
        "manuscript_contexts": [
          {section, sentence, context_before, context_after, stacked_with[]}, ...
        ],
        "signals": {                # raw numbers — agent decides what to do
          "stored_title": str|None,
          "title_overlap_words": int|None,        # stored vs crossref
          "best_context_overlap_words": int|None, # any inline ctx vs crossref title
          "context_count": int,
        }
      }

    The agent should call `acknowledge_finding(slug, doi, note="...")`
    on each DOI it has judged so the dashboard's ribbons update.
    """
    from . import verification as _verification

    contexts = _extract_doi_contexts(state, slug)
    refs = list_references(state, slug)
    results: list[dict] = []
    unresolved: list[dict] = []
    missing_doi: list[dict] = []
    errors: list[dict] = []
    now = now_iso()
    inline_only = set(contexts.keys())

    def _resolve(doi: str, *, registered: bool, key: str | None = None,
                 stored_title: str | None = None) -> None:
        source = "registered_ref" if registered else "inline"
        try:
            meta = _fetch_crossref(doi)
        except DoiNotFound:
            unresolved.append({"citation_key": key, "doi": doi, "stored_title": stored_title})
            _write_finding(
                state, slug, doi=doi, kind="unresolved", source=source,
                ref_citation_key=key, stored_title=stored_title,
                doi_verified=False, now=now, verification=_verification,
            )
            return
        except Exception as e:
            errors.append({"citation_key": key, "doi": doi, "error": str(e)})
            _write_finding(
                state, slug, doi=doi, kind="error", source=source,
                ref_citation_key=key, message=str(e),
                now=now, verification=_verification,
            )
            return

        crossref_title = meta.get("title") or ""
        shared_title = (
            _shared_words((stored_title or "").lower(), crossref_title.lower())
            if (registered and stored_title and stored_title.strip())
            else None
        )
        ctxs = contexts.get(doi, [])
        ctx_overlaps = [
            _shared_words(c["sentence"].lower(), crossref_title.lower())
            for c in ctxs
        ]
        best_ctx = max(ctx_overlaps) if ctx_overlaps else None

        entry = {
            "doi": doi,
            "citation_key": key,
            "doi_verified": True,
            "crossref": {
                k: v for k, v in meta.items() if k != "crossref_raw"
            },
            "manuscript_contexts": ctxs,
            "signals": {
                "stored_title": stored_title,
                "title_overlap_words": shared_title,
                "best_context_overlap_words": best_ctx,
                "context_count": len(ctxs),
            },
        }
        results.append(entry)
        _write_finding(
            state, slug, doi=doi, kind="doi_verified", source=source,
            ref_citation_key=key, stored_title=stored_title,
            crossref_title=crossref_title,
            shared_words=best_ctx if best_ctx is not None else shared_title,
            doi_verified=True,  # server-decidable
            # context_verified is left UNSET — agent's call, set via acknowledge_finding
            now=now, verification=_verification,
        )

    for r in refs:
        key = r.get("citation_key", "")
        doi = (r.get("doi") or "").strip().lower()
        if not doi:
            missing_doi.append({"citation_key": key, "title": r.get("title")})
            continue
        inline_only.discard(doi)
        _resolve(doi, registered=True, key=key, stored_title=r.get("title"))

    for doi in inline_only:
        _resolve(doi, registered=False)

    return {
        "total": len(refs) + len(inline_only),
        # deterministic categories the server owns:
        "unresolved": unresolved,   # CrossRef 404 — fake DOI
        "missing_doi": missing_doi, # ref has no DOI
        "errors": errors,
        # facts pack — agent reads this and decides per-DOI:
        "results": results,
    }


def _write_finding(
    state: State, slug: str, *,
    doi: str, kind: str, source: str,
    ref_citation_key: str | None = None,
    stored_title: str | None = None,
    crossref_title: str | None = None,
    shared_words: int | None = None,
    message: str | None = None,
    context_sentence: str | None = None,
    context_section: str | None = None,
    doi_verified: bool | None = None,
    context_verified: bool | None = None,
    now: str,
    verification,
) -> None:
    """Persist one verification verdict as a Firestore doc.

    Two independent axes (`doi_verified`, `context_verified`) get set in the
    same doc but tagged with who set them and when. set_doc uses merge=True
    so the browser's DOI-only sync and the MCP's context check coexist.
    """
    doc_id = verification._doi_safe_id(doi)
    payload = {
        "doi": doi.lower(),
        "kind": kind,
        "source": source,
        "detected_at": now,
        "acknowledged": False,
    }
    if ref_citation_key is not None:
        payload["ref_citation_key"] = ref_citation_key
    if stored_title is not None:
        payload["stored_title"] = stored_title
    if crossref_title is not None:
        payload["crossref_title"] = crossref_title
    if shared_words is not None:
        payload["shared_words"] = shared_words
    if message is not None:
        payload["message"] = message
    if context_sentence is not None:
        payload["context_sentence"] = context_sentence
    if context_section is not None:
        payload["context_section"] = context_section
    if doi_verified is not None:
        payload["doi_verified"] = doi_verified
        payload["doi_checked_at"] = now
        payload["doi_checked_by"] = "agent"
    if context_verified is not None:
        payload["context_verified"] = context_verified
        payload["context_checked_at"] = now
        payload["context_checked_by"] = "agent"
    state.backend.set_doc_merge(
        verification._finding_doc_path(state, slug, doc_id),
        payload,
    )


_STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "for", "to", "from",
    "with", "by", "is", "are", "was", "were", "be", "been", "as", "at",
    "this", "that", "these", "those", "we", "our", "their", "its",
}


def _shared_words(a: str, b: str) -> int:
    """Count substantive words shared between two titles (lowercased)."""
    def words(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z]+", s) if w not in _STOPWORDS and len(w) > 2}
    return len(words(a) & words(b))


def _substantive_word_count(s: str) -> int:
    """How many substantive (non-stopword, ≥3-char) ASCII words a string has.
    Used as a 'is this context even checkable?' gate."""
    return len({
        w for w in re.findall(r"[a-z]+", s.lower())
        if w not in _STOPWORDS and len(w) > 2
    })

"""Manuscript assembly: turn a list of section docs into a single markdown blob.

The blob is a derived artifact — the canonical content lives in the section
docs in Firestore. We regenerate the blob on every section write so the
dashboard / export pipeline can read a single file when they need to.

Format:
    # {paper title}

    ## Introduction
    {intro body}

    ## Methods
    {methods body}

    ...

Sections are emitted in `sort_order`. Empty sections still get their header
so the structure is visible to the user.
"""
from __future__ import annotations

import uuid

_AUTHOR_FIELDS = ("name", "affiliation", "email", "orcid")


def normalize_authors(authors) -> list[dict]:
    """Coerce a paper author list into `[{name, affiliation, email, orcid,
    corresponding?, affiliation_ids?}, ...]`. Legacy `list[str]` names become
    `{name, affiliation:""...}`. Entries without a name are dropped."""
    out: list[dict] = []
    for a in authors or []:
        if isinstance(a, str):
            entry = {"name": a.strip(), "affiliation": "", "email": "", "orcid": ""}
        elif isinstance(a, dict):
            entry = {f: str(a.get(f, "") or "").strip() for f in _AUTHOR_FIELDS}
            entry["name"] = str(a.get("name", "")).strip()
            if a.get("corresponding"):
                entry["corresponding"] = True
            ids = a.get("affiliation_ids")
            if isinstance(ids, list):
                clean = [str(x).strip() for x in ids if str(x).strip()]
                if clean:
                    entry["affiliation_ids"] = clean
        else:
            continue
        if entry["name"]:
            out.append(entry)
    return out


def normalize_affiliations(affiliations) -> list[dict]:
    """Coerce a paper's ordered affiliation list into `[{id, text}, ...]`,
    de-duplicated by text (first occurrence wins), order preserved."""
    out: list[dict] = []
    seen: set = set()
    for a in affiliations or []:
        if isinstance(a, str):
            text, aid = " ".join(a.split()), None
        elif isinstance(a, dict):
            text = " ".join(str(a.get("text", "") or "").split())
            aid = str(a.get("id", "") or "").strip() or None
        else:
            continue
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append({"id": aid or uuid.uuid4().hex[:12], "text": text})
    return out


def format_author_block(paper: dict) -> dict:
    """Render the standard journal author/affiliation block from a paper doc.

    Returns {names, affiliations, corresponding, markdown}. `names` carries
    superscript affiliation numbers + `*` for the corresponding author
    (pandoc superscripts `^n^`). Uses the paper's explicit `affiliations`
    list; falls back to authors' free-text `affiliation` (de-duplicated,
    first-seen order) so legacy papers still render a block."""
    authors = normalize_authors(paper.get("authors"))
    text_by_id = {a["id"]: a["text"] for a in normalize_affiliations(paper.get("affiliations"))}

    # Assign affiliation numbers by ORDER OF FIRST APPEARANCE while scanning the
    # ordered author list top-to-bottom (standard journal convention) — so the
    # first author's first affiliation is always ^1^, derived from author order
    # and never left stale by the stored affiliation-list order or a reorder.
    order: list[tuple] = []      # (key, text) in first-appearance order
    num: dict = {}               # key -> number
    per_author: list[list] = []

    def _reg(key, text):
        if key not in num:
            num[key] = len(order) + 1
            order.append((key, text))

    for au in authors:
        keys: list = []
        for aid in au.get("affiliation_ids", []):
            text = text_by_id.get(aid)
            if text is None:
                continue
            _reg(("id", aid), text)
            keys.append(("id", aid))
        if not keys:
            t = (au.get("affiliation") or "").strip()
            if t:
                _reg(("text", t.lower()), t)
                keys.append(("text", t.lower()))
        per_author.append(keys)

    name_parts: list[str] = []
    for au, keys in zip(authors, per_author):
        nums = sorted({num[k] for k in keys})
        sup = f"^{','.join(map(str, nums))}^" if nums else ""
        star = "*" if au.get("corresponding") else ""
        name_parts.append(f"{au['name']}{sup}{star}")

    aff_lines = [f"{i + 1}. {text}" for i, (_key, text) in enumerate(order)]
    corr = next((au for au in authors if au.get("corresponding")), None)
    corr_line = ""
    if corr:
        corr_line = "\\* Corresponding author" + (f": {corr['email']}" if corr.get("email") else "")

    names_line = ", ".join(name_parts)
    md = "\n\n".join(p for p in [names_line, "\n".join(aff_lines), corr_line] if p)
    return {"names": names_line, "affiliations": aff_lines,
            "corresponding": corr_line, "markdown": md}


def compile_manuscript(paper: dict, sections: list[dict]) -> str:
    """Assemble a markdown document from a paper doc + ordered section docs."""
    lines: list[str] = []
    title = (paper.get("title") or paper.get("slug") or "Untitled").strip()
    lines.append(f"# {title}")
    lines.append("")
    # Author / affiliation block (journal-style: names with superscripts + a
    # numbered de-duplicated affiliation list + corresponding author).
    block = format_author_block(paper)
    if block["markdown"]:
        lines.append(block["markdown"])
        lines.append("")
    for s in sorted(sections, key=lambda x: x.get("sort_order", 999)):
        section_title = (s.get("title") or s.get("key", "Section")).strip()
        body = (s.get("body") or "").rstrip()
        lines.append(f"## {section_title}")
        if body:
            lines.append("")
            lines.append(body)
        lines.append("")
    # Trim trailing blank lines but keep one newline at EOF
    while len(lines) > 1 and lines[-1] == "" and lines[-2] == "":
        lines.pop()
    if lines and lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


# Canonical section seeds for a new paper (subset of the original 12).
# Order is the conventional paper structure; sort_order matches the index.
DEFAULT_SECTIONS: list[tuple[str, str]] = [
    ("abstract", "Abstract"),
    ("introduction", "Introduction"),
    ("methods", "Methods"),
    ("results", "Results"),
    ("discussion", "Discussion"),
    ("conclusion", "Conclusion"),
]

# Document types. Only "paper" gets the canonical section scaffold; reports and
# other docs start empty so the author structures them freely.
DOC_TYPES = ("paper", "report", "other")


def sections_for_doc_type(doc_type: str) -> list[tuple[str, str]]:
    """Section seeds for a new document of the given type."""
    return DEFAULT_SECTIONS if doc_type == "paper" else []

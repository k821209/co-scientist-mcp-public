"""Numbered citations for the python-docx export path, which has no citeproc.

A report or proposal (`doc_type="report"` / `"other"`) renders .docx natively
so Hancom opens it and the author keeps a free structure — and until now that
path had no citation renderer at all: every `{doi:…}` marker went into the
.docx as the literal string, and the only notice was a warning that appeared
AFTER the file was written (feedback 6e3c8e85eb93: 29 markers, replaced by
hand, with a hand-numbered reference list to keep in step with them). The
registered references, CrossRef-verified, went unused.

Proposals and commissioned reports ask for a reference list at least as often
as journals do, so the answer is not "switch to doc_type=paper" (that trades
away the native engine) but a renderer that needs no style file: references
numbered in order of first appearance, runs of markers merged into one bracket
(`[1, 2]`), and a numbered list where the format wants it — at
`![](references)` if the author placed one, else at the end.

The same reference formatter serves every doc type; only the numbering and
placement are the native path's own. Markers inside code (a backtick span or a
fenced block) are never citations — a document that explains the marker
syntax must be able to show it.
"""
from __future__ import annotations

import re

# Same token grammar as exports.py (kept in one place there; imported lazily to
# avoid a cycle).
_CODE_SPLIT_RE = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.S)


def split_code(text: str) -> list[tuple[bool, str]]:
    """[(is_code, segment)] — fenced blocks and inline spans are code."""
    out: list[tuple[bool, str]] = []
    for i, seg in enumerate(_CODE_SPLIT_RE.split(text)):
        if seg:
            out.append((i % 2 == 1, seg))
    return out


def without_code(text: str) -> str:
    """The prose only, code replaced by a space so token positions stay apart."""
    return "".join(" " if is_code else seg for is_code, seg in split_code(text))


def format_reference(ref: dict) -> str:
    """One reference as a plain line: Authors. Title. Journal Year;Vol(Issue):Pages. doi.

    No style file, so one house form: what a reader needs to find the work.
    Authors as stored ("Given Family"); more than six become "et al.".
    """
    authors = ref.get("authors")
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"\s+and\s+|;", authors) if a.strip()]
    authors = [a for a in (authors or []) if a]
    if len(authors) > 6:
        author_s = ", ".join(authors[:6]) + ", et al."
    else:
        author_s = ", ".join(authors)
    parts: list[str] = []
    if author_s:
        parts.append(author_s.rstrip(".") + ".")
    title = (ref.get("title") or "").strip()
    if title:
        parts.append(title.rstrip(".") + ".")
    venue = (ref.get("journal") or ref.get("publisher") or "").strip()
    year = ref.get("year")
    vol = (str(ref.get("volume") or "")).strip()
    issue = (str(ref.get("issue") or "")).strip()
    pages = (str(ref.get("pages") or "")).strip().replace("--", "–").replace("-", "–")
    tail = venue
    if year:
        tail = f"{tail} {year}" if tail else str(year)
    if vol or pages:
        loc = vol + (f"({issue})" if issue else "")
        if pages:
            loc = f"{loc}:{pages}" if loc else pages
        tail = f"{tail};{loc}" if tail else loc
    if tail:
        parts.append(tail.rstrip(".") + ".")
    if ref.get("doi"):
        parts.append(f"https://doi.org/{str(ref['doi']).strip()}")
    elif ref.get("url"):
        parts.append(str(ref["url"]).strip())
    return " ".join(parts)


def render_numbered(text: str, refs: list[dict]) -> tuple[str, list[dict], list[str]]:
    """Replace citation runs with `[n]` / `[n, m]`; number by first appearance.

    Returns (text, cited_refs_in_order, unmatched). Unmatched tokens — a DOI
    with no registered reference, an unknown key — stay literal so the gap is
    visible in the output, exactly as on the pandoc path.
    """
    from . import exports as _exports  # token regexes live there

    key_by_doi = {(r.get("doi") or "").strip().lower(): r["citation_key"]
                  for r in refs if r.get("doi") and r.get("citation_key")}
    by_key = {r["citation_key"]: r for r in refs if r.get("citation_key")}
    order: list[str] = []
    unmatched: list[str] = []

    def number(key: str) -> int:
        if key not in order:
            order.append(key)
        return order.index(key) + 1

    def repl(m: re.Match) -> str:
        nums: list[int] = []
        leftover: list[str] = []
        for tm in re.finditer(_exports._CITE_TOKEN, m.group(0)):
            tok = tm.group(0)
            if tok.startswith("{doi:"):
                d = _exports._DOI_INLINE_RE.match(tok).group(1).strip()
                key = key_by_doi.get(d.lower())
                if key:
                    nums.append(number(key))
                else:
                    unmatched.append(d)
                    leftover.append("{doi:%s}" % d)
            elif tok.startswith("[@"):
                for k in _exports._RAW_CITE_RE.match(tok).group(1).split(";"):
                    k = k.strip().lstrip("@").strip()
                    if k in by_key:
                        nums.append(number(k))
                    elif k:
                        unmatched.append(k)
                        leftover.append("[@%s]" % k)
            else:
                k = _exports._CITE_KEY_RE.match(tok).group(1).strip()
                if k in by_key:
                    nums.append(number(k))
                else:
                    unmatched.append(k)
                    leftover.append(tok)
        seen: set[int] = set()
        nums = [n for n in nums if not (n in seen or seen.add(n))]
        cite = "[%s]" % ", ".join(str(n) for n in nums) if nums else ""
        return cite + "".join(leftover)

    out_segments: list[str] = []
    for is_code, seg in split_code(text):
        out_segments.append(seg if is_code else _exports._CITE_RUN_RE.sub(repl, seg))
    return "".join(out_segments), [by_key[k] for k in order], unmatched


def reference_list_markdown(cited: list[dict]) -> str:
    return "\n".join(f"{i}. {format_reference(r)}" for i, r in enumerate(cited, start=1))


_REFERENCES_EMBED_RE = re.compile(r"(?m)^[ \t]*!\[[^\]]*\]\(references\)[ \t]*$")


def place_reference_list(text: str, block: str, *, heading: str = "## References") -> str:
    """Put `block` where `![](references)` stands alone on a line; else append
    it under `heading`. The format decides where the list goes — a
    commissioned-report template can put "참고문헌" as item 10 of 12."""
    if _REFERENCES_EMBED_RE.search(text):
        return _REFERENCES_EMBED_RE.sub(lambda _m: block, text, count=1)
    return text.rstrip() + f"\n\n{heading}\n\n{block}\n"


def has_references_embed(text: str) -> bool:
    return bool(_REFERENCES_EMBED_RE.search(without_code(text)))

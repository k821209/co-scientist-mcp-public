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


def compile_manuscript(paper: dict, sections: list[dict]) -> str:
    """Assemble a markdown document from a paper doc + ordered section docs."""
    lines: list[str] = []
    title = (paper.get("title") or paper.get("slug") or "Untitled").strip()
    lines.append(f"# {title}")
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

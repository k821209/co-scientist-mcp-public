"""Journal + paper-type submission requirements.

Journals differ by paper type (Article, Short Communication, Letter,
Review, …) in more than citation style: abstract / main-text word
limits, figure & table caps, structured-abstract rules, required
sections, reference limits.

This module stores a structured `requirements` object on the paper and
deterministically measures the manuscript against it. The MCP only
counts and compares — a *signal provider*. Reading the journal's author
guidelines and filling the structured fields is the agent's job, driven
by the `/journal-requirements` skill.

Sync strategy: nothing is pre-archived. The agent reads the journal's
*live* guidelines when the paper is set up, so the spec is always
current. A stale spec is re-derived by re-running the skill.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..manuscript import DEFAULT_SECTIONS
from ..state import State
from ..util import now_iso
from . import figures as _figures
from . import papers as _papers
from . import references as _references
from . import tables as _tables

_CANON_SECTIONS = {key for key, _ in DEFAULT_SECTIONS}


def _paper_or_raise(state: State, slug: str) -> dict:
    paper = state.backend.get_doc(state.project_path("papers", slug))
    if paper is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    return paper


def set_paper_requirements(
    state: State,
    slug: str,
    *,
    paper_type: str,
    abstract_max_words: int | None = None,
    abstract_structured: bool | None = None,
    main_text_max_words: int | None = None,
    max_figures: int | None = None,
    max_tables: int | None = None,
    max_display_items: int | None = None,
    max_references: int | None = None,
    required_sections: list[str] | None = None,
    notes: str | None = None,
    source: str | None = None,
) -> dict:
    """Store the journal/paper-type submission spec on the paper.

    Only `paper_type` is required. Every limit left None means "the
    guidelines state no limit" — never invent one. `notes` carries rules
    that don't fit a structured field (e.g. "Methods at the end", "no
    subheadings in Results"). `source` is where the guidelines came from.
    """
    _paper_or_raise(state, slug)
    if not paper_type or not paper_type.strip():
        raise ValueError(
            "paper_type is required (e.g. 'Article', 'Short Communication')"
        )

    def _pos_int(v: int | None, name: str) -> int | None:
        if v is None:
            return None
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ValueError(f"{name} must be a positive integer or null")
        return v

    if required_sections is not None:
        unknown = [s for s in required_sections if s not in _CANON_SECTIONS]
        if unknown:
            raise ValueError(
                f"unknown section keys {unknown}; "
                f"valid: {sorted(_CANON_SECTIONS)}"
            )

    requirements = {
        "paper_type": paper_type.strip(),
        "abstract_max_words": _pos_int(abstract_max_words, "abstract_max_words"),
        "abstract_structured": abstract_structured,
        "main_text_max_words": _pos_int(main_text_max_words, "main_text_max_words"),
        "max_figures": _pos_int(max_figures, "max_figures"),
        "max_tables": _pos_int(max_tables, "max_tables"),
        "max_display_items": _pos_int(max_display_items, "max_display_items"),
        "max_references": _pos_int(max_references, "max_references"),
        "required_sections": list(required_sections) if required_sections else None,
        "notes": notes,
        "source": source,
        "set_at": now_iso(),
    }
    state.backend.update_doc(
        state.project_path("papers", slug),
        {"requirements": requirements, "updated_at": now_iso()},
    )
    return requirements


def get_paper_requirements(state: State, slug: str) -> dict | None:
    """Return the stored requirements object, or None if unset."""
    return _paper_or_raise(state, slug).get("requirements")


def check_requirements(state: State, slug: str) -> dict:
    """Measure the manuscript against the stored spec.

    Deterministic only — counts words, figures, tables, references and
    compares to the limits. Judgment calls (is the abstract genuinely
    structured? do the free-text `notes` hold?) are the agent's.

    Returns {configured, requirements, metrics, checks, violations, ok}.
    """
    paper = _paper_or_raise(state, slug)
    req = paper.get("requirements")
    if not req:
        return {
            "configured": False,
            "requirements": None,
            "message": "No journal requirements set for this paper. "
                       "Run /journal-requirements to set them.",
        }

    bundle = _papers.get_paper_state(state, slug)
    abstract_words = 0
    main_text_words = 0
    sections_with_content: list[str] = []
    for s in bundle["sections"]:
        wc = s.get("word_count") or 0
        if s.get("key") == "abstract":
            abstract_words = wc
        else:
            main_text_words += wc
        if wc > 0:
            sections_with_content.append(s.get("key"))

    n_figures = len(_figures.list_figures(state, slug))
    n_tables = len(_tables.list_tables(state, slug))
    n_refs = len(_references.list_references(state, slug))
    n_display = n_figures + n_tables

    metrics = {
        "abstract_words": abstract_words,
        "main_text_words": main_text_words,
        "figures": n_figures,
        "tables": n_tables,
        "display_items": n_display,
        "references": n_refs,
        "sections_with_content": sections_with_content,
    }

    checks: list[dict] = []

    def _max_check(name: str, label: str, limit: int | None, actual: int) -> None:
        if limit is None:
            return
        checks.append({
            "name": name, "label": label, "kind": "max",
            "limit": limit, "actual": actual, "ok": actual <= limit,
        })

    _max_check("abstract_words", "Abstract word count",
               req.get("abstract_max_words"), abstract_words)
    _max_check("main_text_words", "Main-text word count",
               req.get("main_text_max_words"), main_text_words)
    _max_check("figures", "Figures", req.get("max_figures"), n_figures)
    _max_check("tables", "Tables", req.get("max_tables"), n_tables)
    _max_check("display_items", "Display items (figures + tables)",
               req.get("max_display_items"), n_display)
    _max_check("references", "References", req.get("max_references"), n_refs)

    required = req.get("required_sections")
    if required:
        missing = [k for k in required if k not in sections_with_content]
        checks.append({
            "name": "required_sections", "label": "Required sections",
            "kind": "presence", "required": required, "missing": missing,
            "ok": not missing,
        })

    violations = [c for c in checks if not c["ok"]]
    return {
        "configured": True,
        "requirements": req,
        "metrics": metrics,
        "checks": checks,
        "violations": violations,
        "ok": not violations,
    }

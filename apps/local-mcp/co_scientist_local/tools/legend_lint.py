"""Deterministic legend QA — figure / table / supplementary legends that grew a
mini-Results inside them (feedback 6541fa247b44).

A legend should DESCRIBE the panel (what's plotted, the panels A–E, key numbers,
colour coding, cross-refs), not RESTATE the Results/Methods. On a real paper a
supplementary figure legend had 634 words that re-derived a threshold already in
the body. Nothing surfaced it — you had to dump every legend and eyeball word
counts. This scores each legend the way `lint_manuscript` scores prose.

Reads the SAME text the export emits: a figure legend is caption + legend joined
(exports.py concatenates both); a table legend is its caption (or title). Figure
and table thresholds differ — a table caption legitimately carries column/footnote
definitions, so it is scored far more leniently.
"""
from __future__ import annotations

import re

from ..state import State
from .figures import SUPPLEMENTARY_NUMBER_OFFSET, list_figures
from .sections import list_sections
from .tables import list_tables

# Word-count bands (info / warn) by item type.
_FIG_INFO, _FIG_WARN = 150, 220
_TAB_INFO, _TAB_WARN = 300, 450

_SHINGLE = 6           # n-gram size for the body-duplication check
_DUP_MIN = 0.60        # containment above which a legend sentence "restates" the body
_MAX_DUP_SPANS = 4     # cap reported spans per legend

# Interpretation/derivation phrasing that belongs in Results, not a legend.
_INTERPRETIVE = [re.compile(p, re.I) for p in (
    r"\bwe (?:show|showed|demonstrate[sd]?|found|find|confirm(?:ed)?)\b",
    r"\bconfirm(?:s|ed)?\b", r"\bunderscore", r"\bhighlight(?:s|ed)?\b",
    r"\bindependently recover(?:s|ed)?\b", r"\bjustified by\b",
    r"\bis adopted as\b", r"\bwe adopt\b", r"\bsets? the threshold\b",
    r"\bderived from\b.{0,40}\bbimodal", r"\bfull derivation\b",
    r"\bsuggest(?:s|ing)?\b", r"\bconsistent with\b",
)]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text or "")


def _sentences(text: str) -> list[str]:
    """Split legend prose into sentences, keeping panel-label chunks intact."""
    out: list[str] = []
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip()):
        c = chunk.strip()
        if c:
            out.append(c)
    return out


def _shingles(text: str, n: int = _SHINGLE) -> set:
    toks = [w.lower() for w in _words(text)]
    if len(toks) < n:
        return set()
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _legend_text_figure(fig: dict) -> str:
    return " ".join(v for v in ((fig.get("caption") or "").strip(),
                                (fig.get("legend") or "").strip()) if v)


def lint_legends(state: State, slug: str) -> dict:
    """Scan every figure / table / supplementary legend. Returns
    {slug, findings: [...], summary: {...}}.

    Each finding: {item, type, number, word_count, level (info|warn),
    flags (long|body_duplication|interpretive), duplicated_spans:
    [{sentence, section, overlap}], suggestion}. `level` is warn if any flag is
    warn-grade, else info; an item with no flags is omitted.
    """
    sections = list_sections(state, slug)
    # Pre-shingle each section body once; the duplication check is containment of
    # a legend sentence's n-grams in a section (NOT Jaccard — a short sentence
    # against a long body never reaches 0.6 by Jaccard; containment is the
    # "does this sentence already live in the body?" question we actually want).
    sec_shingles = [(s.get("title") or s.get("key") or "?",
                     _shingles(s.get("body") or "")) for s in sections]

    def _dup_spans(text: str) -> list[dict]:
        spans: list[dict] = []
        for sent in _sentences(text):
            sh = _shingles(sent)
            if not sh:
                continue
            best_sec, best = None, 0.0
            for title, ssh in sec_shingles:
                if not ssh:
                    continue
                overlap = len(sh & ssh) / len(sh)
                if overlap > best:
                    best, best_sec = overlap, title
            if best >= _DUP_MIN:
                spans.append({"sentence": sent[:200], "section": best_sec,
                              "overlap": round(best, 2)})
        spans.sort(key=lambda x: x["overlap"], reverse=True)
        return spans[:_MAX_DUP_SPANS]

    def _interpretive(text: str) -> list[str]:
        hits = []
        for rx in _INTERPRETIVE:
            m = rx.search(text)
            if m:
                hits.append(m.group(0))
        return hits

    findings: list[dict] = []

    def _score(item, kind, number, text, info_at, warn_at):
        text = (text or "").strip()
        if not text:
            return
        wc = len(_words(text))
        flags, level = [], None
        if wc > warn_at:
            flags.append("long"); level = "warn"
        elif wc > info_at:
            flags.append("long"); level = "info"
        dup = _dup_spans(text)
        if dup:
            flags.append("body_duplication"); level = "warn"
        interp = _interpretive(text)
        if interp:
            flags.append("interpretive"); level = level or "info"
        if not flags:
            return
        sugg = None
        if "body_duplication" in flags or "interpretive" in flags:
            sugg = ("keep panel descriptions, key numbers, colour coding and "
                    "cross-refs; move derivation/interpretation to Results "
                    "(\"Full derivation in Results\") — and prefer commas/colons "
                    "over em-dashes, as in the body.")
        elif "long" in flags:
            sugg = "trim to panel descriptions + key values; the body carries the rest."
        findings.append({
            "item": item, "type": kind, "number": number, "word_count": wc,
            "level": level, "flags": flags,
            "duplicated_spans": dup,
            "interpretive_phrases": interp,
            "suggestion": sugg,
        })

    for fig in list_figures(state, slug, supplementary=None):
        num = fig["figure_number"]
        supp = num >= SUPPLEMENTARY_NUMBER_OFFSET
        label = (f"SFig S{num - SUPPLEMENTARY_NUMBER_OFFSET}" if supp
                 else f"Fig {num}")
        _score(label, "figure", num, _legend_text_figure(fig), _FIG_INFO, _FIG_WARN)

    for tbl in list_tables(state, slug, supplementary=None):
        num = tbl["table_number"]
        supp = num >= SUPPLEMENTARY_NUMBER_OFFSET
        label = (f"STable S{num - SUPPLEMENTARY_NUMBER_OFFSET}" if supp
                 else f"Table {num}")
        cap = (tbl.get("caption") or tbl.get("title") or "")
        _score(label, "table", num, cap, _TAB_INFO, _TAB_WARN)

    findings.sort(key=lambda f: (0 if f["level"] == "warn" else 1, -f["word_count"]))
    by_level = {"warn": 0, "info": 0}
    for f in findings:
        by_level[f["level"]] += 1
    return {
        "slug": slug,
        "findings": findings,
        "summary": {"total": len(findings), "warn": by_level["warn"],
                    "info": by_level["info"], "clean": not findings},
    }

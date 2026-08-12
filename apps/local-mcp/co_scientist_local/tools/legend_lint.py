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
from .figures import SUPPLEMENTARY_NUMBER_OFFSET, is_supplementary_number, list_figures
from .sections import list_sections
from .tables import list_tables

# Word-count bands (info / warn) by item type.
_FIG_INFO, _FIG_WARN = 150, 220
_TAB_INFO, _TAB_WARN = 300, 450

_SHINGLE = 6           # n-gram size for the body-duplication check
_DUP_MIN = 0.60        # containment above which a legend sentence "restates" the body
_MAX_DUP_SPANS = 25    # safety cap only — enumerate every duplicated sentence so
                       # they all clear in one pass (feedback f6e40039cc9e)
_ROSTER_MIN_TOKEN = 0.60   # token overlap with the body for a roster "restatement"

# A sample-composition roster: two or more "<n> <group-word>" pairs in one
# sentence ("19 Korean field collections, four U.S. specimens…"). "four" etc.
# are spelled numbers, so allow a leading number word too.
_ROSTER_GROUP_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"[\w.\-'’ ]{0,32}?\b(?:samples?|specimens?|collections?|genomes?|"
    r"accessions?|isolates?|plastomes?|individuals?|taxa|sequences?|strains?|"
    r"assemblies|reads)\b", re.I)

# A roster ENUMERATES sample composition — where/what kind the samples are, not
# just a count. Require a composition qualifier (region / nationality /
# collection-type / a species binomial like "C. rostrata"); otherwise "24
# samples … the top-1 reference accession …" (a method/column sentence that
# happens to carry a count + a comma list) is not a roster.
_COMPOSITION_RX = re.compile(
    r"\b(?:korean?|u\.?s\.?|american|chinese|japan(?:ese)?|europ(?:e|ean)|"
    r"african|domestic|wild|cultivated|field|greenhouse|herbarium|natural|"
    r"population|cohort|accessions? from|collected)\b"
    r"|\b[A-Z][a-z]*\.\s+[a-z]{3,}\b", re.I)
# Column/method-description stems a table caption legitimately carries — never a
# roster even when a count + comma-list is present.
_METHOD_COLUMN_RX = re.compile(
    r"\bcolumns?\s+(?:report|are|show|list|contain|give)\b|\beach column\b"
    r"|\bsubmitted to\b|\bcomputed (?:by|as)\b|\bcalculated (?:by|as)\b"
    r"|\brun (?:through|with)\b", re.I)

# A pointer sentence: "…cataloged/listed/described … in (Supplementary) Table/
# Results/Methods…". Adds no table-reading value on its own.
_POINTER_RX = re.compile(
    r"\b(?:catalog(?:u)?ed|listed|described|detailed|reported|tabulated|shown|"
    r"given|summariz(?:ed|es)|presented|available|provided)\b[^.]*?"
    r"\b(?:in|separately in)\b[^.]*?"
    r"\b(?:Supplementary\s+)?(?:Table|Fig(?:ure)?|Results|Methods|Discussion|"
    r"Appendix|Supplementary)\b", re.I)

# A caption sentence that POINTS elsewhere (cross-reference / navigation) or
# DEFINES a column, rather than asserting a column value as fact — column_redundant
# must not fire on these.
_CROSSREF_RX = re.compile(
    r"\b(?:described|defined|listed|reported|shown|detailed|discussed|given|"
    r"summariz(?:ed|es)|explained)\s+in\b"
    r"|\bsee\b|\brefer to\b"
    r"|\b(?:Results|Methods|Discussion|Introduction|Supplementary)\b"
    r"|\b(?:Fig(?:ure)?|Table)s?\.?\s*S?\d"
    r"|=|\bdefined as\b|\bdenotes?\b|\brefers? to\b", re.I)


def _is_crossref_or_definition(sentence: str) -> bool:
    return bool(_CROSSREF_RX.search(sentence))


# Caption meta-commentary about data that ISN'T in the table.
_EXCLUDED_RX = re.compile(
    r"\bnot (?:included|tabulated|shown|listed|reported)\b"
    r"|\bexcluded from this table\b|\bnot part of this table\b", re.I)

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


def _table_columns(content: str) -> dict:
    """Parse a markdown table → {column_name: [cell values...]} for the data rows.
    Returns {} if it doesn't look like a pipe table."""
    lines = [ln.strip() for ln in (content or "").splitlines() if ln.strip()]
    rows = [[c.strip() for c in ln.strip("|").split("|")]
            for ln in lines if ln.startswith("|") or "|" in ln]
    if len(rows) < 3:
        return {}
    header = rows[0]
    # row 1 is the |---|---| separator; data starts at row 2
    sep = rows[1]
    if not all(set(c) <= set("-: ") and "-" in c for c in sep if c):
        return {}
    cols: dict = {name: [] for name in header}
    for r in rows[2:]:
        for name, val in zip(header, r):
            cols[name].append(val)
    return cols


# A caption sentence that scopes itself to one sheet/panel of a MULTI-PART
# artifact. `content` here is a single markdown table, so a workbook's other
# sheets are simply not visible — matching such a sentence against the columns
# we CAN see produced a false positive: "Sheet (b): PLINK linear regression…"
# was called redundant because "PLINK" appears in a DIFFERENT sheet's column.
# We cannot check the sheet the sentence is about, so we do not guess.
_SHEET_SCOPED = re.compile(
    r"\b(?:sheet|tab|panel|worksheet)\s*(?:\(?[a-z0-9]{1,3}\)?|[a-z0-9]{1,3})\s*[:.)-]",
    re.I,
)


def _table_caption_smells(caption: str, content: str) -> list[dict]:
    """Table-only caption checks (feedback e5e8edaa2566), both advisory (info):
    a sentence that restates a table COLUMN VALUE, and meta-notes about data not
    in the table."""
    out: list[dict] = []
    sents = _sentences(caption)
    cols = _table_columns(content)
    # column_redundant: a distinct cell value that covers >= 2 rows and appears
    # verbatim in a caption sentence. Matches VALUES, not headers, so a footnote
    # that DEFINES a column ("Raw FASTQ volume = …") is not flagged. A sentence
    # that NAVIGATES to/from those rows ("the Tier-2 cases are described in
    # Results") or DEFINES the column is a cross-reference, not a restatement —
    # skip it (feedback 3a041228b48a). Flag only when the value is asserted as a
    # fact about the rows.
    for name, vals in cols.items():
        counts: dict = {}
        for v in vals:
            if v:
                counts[v] = counts.get(v, 0) + 1
        for val, n in counts.items():
            if n < 2 or len(val) < 5 or not re.search(r"[A-Za-z]", val):
                continue
            val_rx = re.compile(r"(?<!\w)" + re.escape(val) + r"(?!\w)")
            for sent in sents:
                if _SHEET_SCOPED.search(sent):
                    continue        # describes a sheet we cannot see — see _SHEET_SCOPED
                if val_rx.search(sent) and not _is_crossref_or_definition(sent):
                    out.append({"kind": "column_redundant", "match": val,
                                "column": name, "sentence": sent[:200],
                                "note": f"'{val}' is already shown in the "
                                        f"'{name}' column ({n} rows) — drop the "
                                        f"sentence."})
                    break
    # excluded_data_note: meta-commentary about absent data.
    for sent in sents:
        if _EXCLUDED_RX.search(sent):
            out.append({"kind": "excluded_data_note", "sentence": sent[:200],
                        "note": "note about data not shown in the table — usually "
                                "unnecessary; drop unless it's a deliberate scope "
                                "caveat."})
    return out


def _legend_text_figure(fig: dict) -> str:
    return " ".join(v for v in ((fig.get("caption") or "").strip(),
                                (fig.get("legend") or "").strip()) if v)


# ── caption_only: the check that can prevent DATA LOSS ────────────────────────
#
# Every other flag here answers "is this redundant?" and the natural response to
# each is deletion — they are named `long`, `interpretive`, `bare_cross_reference`.
# This one answers the opposite question, "is this load-bearing?", and it is the
# only one whose absence can destroy information.
#
# Reported case: a Figure 6 legend said the QTL intervals were projected "with
# ± 250 kb padding". It reads exactly like method detail whose home is Methods —
# but Methods never stated that padding (it stated a DIFFERENT 100 kb constant for
# a separate step), and the manuscript's headline overlap figure depends entirely
# on that value: 39.7% unpadded, 41.4% at 100 kb, 44.9% at 250 kb, 54.0% at 1 Mb.
# The caption was its only appearance in the whole submission, so trimming it
# would have deleted the paper's method silently. The right action was the
# opposite of trimming: relocate to Methods, then drop it from the legend.
#
# Parameter-shaped tokens only: a magnitude with a unit, a named constant
# assignment, a threshold, an iteration count, a software version. Deliberately
# narrow — a bare integer ("3 panels") is not a parameter and would make it noisy.
_PARAM_TOKEN = re.compile(
    r"""(?:±|\+/-)\s*\d[\d,.]*\s*(?:kb|Mb|bp|%|nm|µm|um|mm|s|min|h)\b
      | \b\d[\d,.]*\s*(?:kb|Mb|bp)\b
      | \b(?:seed|n_init|k|K|iterations?|permutations?|restarts?|bootstraps?)
        \s*[=:]\s*\d[\d,.]*
      | \b\d[\d,]{2,}\s*(?:iterations?|permutations?|restarts?|bootstraps?|times)\b
      | \b[pq]\s*[<≤>=]\s*0?\.\d+
      | \bv(?:ersion\s*)?\d+\.\d+(?:\.\d+)?\b
    """,
    re.X,
)


def _param_tokens(text: str) -> list[str]:
    """Parameter-shaped tokens in `text`, whitespace-normalised."""
    return [re.sub(r"\s+", " ", m.group(0)).strip()
            for m in _PARAM_TOKEN.finditer(text or "")]


def _norm_for_presence(text: str) -> str:
    """Whitespace-stripped + lowercased, with ASCII +/- folded to ±, so "250 kb"
    matches "250kb" and the comparison does not fail on spacing alone."""
    return re.sub(r"\s+", "", (text or "").lower()).replace("+/-", "±")


def _caption_only_tokens(caption: str, bodies_norm: str) -> list[str]:
    """Parameter tokens present in the caption and NOWHERE in any section body.

    A false NEGATIVE is cheap (the token really is in Methods → nothing to say);
    a false POSITIVE costs the author one look. So presence is tested loosely: the
    numeric+unit core has to appear somewhere in the body, not the token verbatim.
    """
    missing = []
    for tok in _param_tokens(caption):
        core = _norm_for_presence(tok).lstrip("±")
        if core and core not in bodies_norm:
            missing.append(tok)
    return sorted(set(missing))


def lint_legends(state: State, slug: str) -> dict:
    """Scan every figure / table / supplementary legend. Returns
    {slug, findings: [...], summary: {...}}.

    Each finding: {item, type, number, word_count, level (info|warn), flags, and
    detail lists. Flags: long, body_duplication (EVERY duplicated sentence is
    enumerated in duplicated_spans, each with its section + a trim suggestion),
    interpretive, sample_roster_restatement (a sample-composition list also in
    the body), bare_cross_reference (a "…described/listed in Table/Results…"
    pointer), and table-only column_redundant / excluded_data_note (in
    caption_smells). `level` is warn if any flag is warn-grade, else info; an
    item with no flags is omitted.
    """
    sections = list_sections(state, slug)
    # Pre-shingle each section body once; the duplication check is containment of
    # a legend sentence's n-grams in a section (NOT Jaccard — a short sentence
    # against a long body never reaches 0.6 by Jaccard; containment is the
    # "does this sentence already live in the body?" question we actually want).
    sec_shingles = [(s.get("title") or s.get("key") or "?",
                     _shingles(s.get("body") or "")) for s in sections]
    # One normalised haystack of every section body, for the caption_only check.
    bodies_norm = _norm_for_presence(" ".join((x.get("body") or "") for x in sections))

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
                              "overlap": round(best, 2),
                              "suggestion": f"cut — already in {best_sec}"})
        spans.sort(key=lambda x: x["overlap"], reverse=True)
        return spans[:_MAX_DUP_SPANS]     # every duplicated sentence, not just one

    # Roster / pointer smells (reworded restatements that 6-gram containment
    # misses). Uses the body's token SET so a reordered roster still matches.
    body_tokens = {w.lower() for s in sections
                   for w in _words(s.get("body") or "") if len(w) >= 2}

    def _prose_smells(text: str) -> list[dict]:
        # Detect on the FULL text, not per-sentence: the naive sentence splitter
        # breaks on abbreviation periods ("U.S.", "C. rostrata"), which fragments
        # a roster mid-list.
        out: list[dict] = []
        rm = list(_ROSTER_GROUP_RE.finditer(text))
        if len(rm) >= 2:
            span = text[rm[0].start():rm[-1].end()]
            toks = {w.lower() for w in _words(span) if len(w) >= 2}
            # composition qualifier present, not a column/method sentence, and the
            # roster actually recurs in a body section (it's a RESTATEMENT).
            if (_COMPOSITION_RX.search(span) and not _METHOD_COLUMN_RX.search(text)
                    and toks and len(toks & body_tokens) / len(toks) >= _ROSTER_MIN_TOKEN):
                out.append({"kind": "sample_roster_restatement",
                            "sentence": span[:200],
                            "note": "sample-composition roster that also appears in "
                                    "the body — give the total and cross-reference, "
                                    "don't re-list the groups."})
        for pm in _POINTER_RX.finditer(text):
            out.append({"kind": "bare_cross_reference", "sentence": pm.group(0)[:200],
                        "note": "pointer to another location — keep only if it "
                                "guides the reader to specific rows; else cut."})
        return out

    def _interpretive(text: str) -> list[str]:
        hits = []
        for rx in _INTERPRETIVE:
            m = rx.search(text)
            if m:
                hits.append(m.group(0))
        return hits

    findings: list[dict] = []

    def _score(item, kind, number, text, info_at, warn_at, table_content=None):
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
        caption_smells: list[dict] = _prose_smells(text)
        if table_content is not None:
            caption_smells += _table_caption_smells(text, table_content)
        for s in caption_smells:
            if s["kind"] not in flags:
                flags.append(s["kind"])
        if caption_smells:
            level = level or "info"
        # RELOCATE, do not delete. Ranked warn and placed FIRST: every other flag
        # here invites deletion, and this is the one case where deleting destroys
        # information that exists nowhere else.
        orphan_params = _caption_only_tokens(text, bodies_norm)
        if orphan_params:
            flags.insert(0, "caption_only"); level = "warn"
        if not flags:
            return
        sugg = None
        if orphan_params:
            sugg = ("RELOCATE, do not delete: " + ", ".join(orphan_params) +
                    " appears in this caption and in NO section body, so trimming "
                    "it removes the value from the paper. Move it to Methods (a "
                    "threshold/constant) or Results (a derived statistic) FIRST, "
                    "then drop it here. If the value is tunable, state how much "
                    "the result moves with it.")
        elif "body_duplication" in flags or "interpretive" in flags:
            sugg = ("keep panel descriptions, key numbers, colour coding and "
                    "cross-refs; move derivation/interpretation to Results "
                    "(\"Full derivation in Results\") — and prefer commas/colons "
                    "over em-dashes, as in the body.")
        elif "long" in flags:
            sugg = "trim to panel descriptions + key values; the body carries the rest."
        finding = {
            "item": item, "type": kind, "number": number, "word_count": wc,
            "level": level, "flags": flags,
            "duplicated_spans": dup,
            "caption_only_params": orphan_params,
            "interpretive_phrases": interp,
            "suggestion": sugg,
        }
        if caption_smells:
            finding["caption_smells"] = caption_smells
        findings.append(finding)

    for fig in list_figures(state, slug, supplementary=None):
        num = fig["figure_number"]
        supp = is_supplementary_number(num)
        label = (f"SFig S{num - SUPPLEMENTARY_NUMBER_OFFSET}" if supp
                 else f"Fig {num}")
        _score(label, "figure", num, _legend_text_figure(fig), _FIG_INFO, _FIG_WARN)

    for tbl in list_tables(state, slug, supplementary=None):
        num = tbl["table_number"]
        supp = is_supplementary_number(num)
        label = (f"STable S{num - SUPPLEMENTARY_NUMBER_OFFSET}" if supp
                 else f"Table {num}")
        cap = (tbl.get("caption") or tbl.get("title") or "")
        _score(label, "table", num, cap, _TAB_INFO, _TAB_WARN,
               table_content=tbl.get("content") or "")

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

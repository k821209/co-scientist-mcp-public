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
#
# This was a 12-entry exact-phrase list, and it missed most interpretation
# (feedback 73667d96e179). Real unflagged examples: "the models are
# overwhelmingly larger than the reference, most exceeding it on all three
# axes", "Gene-Miner approaches their completeness ceiling and matches or
# exceeds BRAKER3", "Reference-matching loci are well supported …; the novel
# loci are markedly lower", "they are complete gene models rather than
# fragments … as expected". A user caught them by eye after a lint pass reported
# clean.
#
# It is in TWO tiers, because the naive broadening — add comparative adjectives
# — fires on exactly the sentences a legend is SUPPOSED to contain. "Darker
# shading indicates higher coverage" and "Larger circles denote more reads"
# describe the visual mapping; "higher" and "Larger" there are not claims.
#
# STRONG: evaluative intensifiers, inference and causation, first-person claims.
# These essentially never describe an encoding, so they fire unconditionally —
# which matters, because the reporter's Fig 2 sentence contains "axes" and would
# otherwise be suppressed as encoding text.
_INTERP_STRONG = [re.compile(p, re.I) for p in (
    # Evaluative intensifiers.
    r"\b(?:overwhelmingly|markedly|substantially|considerably|dramatically"
    r"|strikingly|notably|remarkably|appreciably|materially|vastly)\b",
    # Inference / causation / expectation.
    r"\bas expected\b", r"\bconsistent with\b", r"\btherefore\b", r"\bthus\b",
    r"\breflect(?:s|ing)?\b", r"\bdriven by\b", r"\bbecause\b", r"\bowing to\b",
    r"\bdue to\b", r"\bsuggest(?:s|ing|ed)?\b", r"\bimpl(?:y|ies|ying)\b",
    r"\bindicat(?:e|es|ing)\s+that\b", r"\bdemonstrat(?:e|es|ing)\b",
    r"\bsupport(?:s|ing)?\s+(?:the|our|this|that)\b",
    # Reported as missed: an agent writing an argument into a caption reaches
    # for these as readily as for "suggests" (feedback 81d4a52c0212).
    r"\b(?:this|these|it|they)\s+(?:shows?|indicates?|means?)\s+that\b",
    r"\brule[sd]?\s+out\b",
    r"\bexclude[sd]?\s+(?:the|any|a|an)\b",
    # Evaluative predicates.
    r"\bwell (?:supported|resolved|separated|characteri[sz]ed|conserved)\b",
    # First-person claims + the original list's specific phrasings.
    r"\bwe (?:show|showed|demonstrate[sd]?|found|find|confirm(?:ed)?|adopt)\b",
    r"\bconfirm(?:s|ed)?\b", r"\bunderscore", r"\bhighlight(?:s|ed)?\b",
    r"\bindependently recover(?:s|ed)?\b", r"\bjustified by\b",
    r"\bis adopted as\b", r"\bsets? the threshold\b",
    r"\bderived from\b.{0,40}\bbimodal", r"\bfull derivation\b",
)]

# COMPARATIVE: a comparison or an outcome verb. Real interpretation when the
# subject is a result, ordinary legend text when it describes the graphic — so
# these are suppressed in a sentence that talks about the encoding.
_INTERP_COMPARATIVE = [re.compile(p, re.I) for p in (
    r"\b(?:larger|smaller|higher|lower|greater|better|worse|stronger|weaker"
    r"|faster|slower|denser|sparser)\b",
    r"\b(?:match(?:es|ed)?|exceed(?:s|ed|ing)?|outperform(?:s|ed)?"
    r"|approach(?:es|ed)?|surpass(?:es|ed)?|recover(?:s|ed)?"
    r"|improve(?:s|d)?)\b",
)]

# Encoding-description context: the sentence is about the graphic, not a result.
# Deliberately generous — a missed interpretation costs one look, while a flag on
# "The lower panel shows the same data" is the kind of noise that gets a whole
# rule ignored.
_ENCODING_CX = re.compile(
    r"\b(?:colou?r(?:s|ed|ing)?|shad(?:e|es|ing|ed)|hue|greyscale|grayscale"
    r"|size[sd]?|symbol|marker|glyph|circle|square|triangle|bar|line|dash(?:ed)?"
    r"|solid|dotted|hatch(?:ing|ed)?|axis|axes|tick|arrow(?:head)?|asterisk"
    r"|panel|inset|legend|whisker|box(?:es|plot)?|ribbon|shape|width|thickness"
    r"|opacity|scale"
    # ...and the verbs that introduce an encoding statement.
    r"|shown|show[s]?|plotted|displayed|drawn|rendered|marked|labell?ed"
    r"|denote[sd]?|represent(?:s|ed)?|encode[sd]?|correspond(?:s|ing)?)\b",
    re.I,
)

# One interpretive sentence in a legend is a style note; several mean the legend
# has grown a mini-Results, which is what the rule is actually for.
_INTERP_WARN_AT = 2


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


def _caption_only_tokens(caption: str, data_norm: str) -> list[str]:
    """Parameter tokens present in the caption and NOWHERE else in the submission.

    `data_norm` covers section bodies AND every table's cells — a value sitting in
    a table cell is not caption-only, and calling it so would put this flag in
    direct contradiction with `number_restatement` below, which reads the same
    value as redundant. One is "never delete", the other "delete": they must never
    fire on the same token.

    A false NEGATIVE is cheap (the token really is in Methods → nothing to say);
    a false POSITIVE costs the author one look. So presence is tested loosely: the
    numeric+unit core has to appear somewhere, not the token verbatim.
    """
    missing = []
    for tok in _param_tokens(caption):
        core = _norm_for_presence(tok).lstrip("±")
        if core and core not in data_norm:
            missing.append(tok)
    return sorted(set(missing))


# ── number_restatement: the caption re-tabulating data the item already shows ──
#
# `column_redundant` above catches a caption echoing a CATEGORICAL cell value
# ("Gene-Miner", "Representative") and is table-only. It cannot see the more
# egregious case: a caption whose prose re-quotes the NUMBERS in the item's own
# cells. Reported case (feedback 4aa8a17820fc): an STable caption walked through
# "rice 93.6% → 96.5%, Drosophila 96.5% → 98.9%, C. elegans 95.1% → 98.3%,
# soybean 91.9% → 92.1%" — every one of those the exact value in the table's own
# Complete (C) column — and the lint fired only on the words "Gene-Miner" and
# "BRAKER3". A figure caption could carry a whole mini-Results of numbers with no
# rule able to see it at all, since figures have no columns.
#
# Word count does not surface this: a numeric-dense caption can be short, and the
# `long` flag is the one authors most reasonably ignore.
_MEASURE_TOKEN = re.compile(
    r"""\d[\d,]*(?:\.\d+)?\s*[×x]\s*10\s*\^?\s*-?\d+   # 1.4 × 10^8
      | \d[\d,]*(?:\.\d+)?\s*%                          # 96.5%
      | \b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b                # 1,234 / 9,876.5
      | \b\d+\.\d+\b                                    # 96.5
    """,
    re.X,
)
# How many restated numbers make a caption a re-tabulation rather than emphasis.
# NOT 1: quoting the one headline value is good caption writing, and our own
# suggestion text tells authors to "keep key numbers". Three is where a caption
# has stopped pointing at the data and started reprinting it.
_MIN_RESTATED = 3


def _measure_tokens(text: str) -> list[tuple[str, str]]:
    """Measurement-shaped numeric literals as (verbatim, normalised).

    Excludes any literal a `_PARAM_TOKEN` span already claims — a threshold,
    named constant, padding or version. That is what keeps this rule and
    `caption_only` disjoint BY CONSTRUCTION rather than by coincidence of which
    haystack each happens to search.
    """
    param_spans = [m.span() for m in _PARAM_TOKEN.finditer(text or "")]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _MEASURE_TOKEN.finditer(text or ""):
        s, e = m.span()
        if any(ps < e and s < pe for ps, pe in param_spans):
            continue
        norm = _norm_number(m.group(0))
        if norm and norm not in seen:
            seen.add(norm)
            out.append((m.group(0).strip(), norm))
    return out


def _norm_number(tok: str) -> str:
    """Canonical form of a numeric literal, for comparison across contexts.

    Lowercased, whitespace and thousands commas removed, ×→x, ^ dropped, and a
    trailing % stripped — the caption writes "96.5%" while the cell under a
    "Complete (C) %" header often writes "96.5", and those are the same number.
    """
    s = re.sub(r"\s+", "", (tok or "").lower())
    return s.replace("×", "x").replace("^", "").replace(",", "").rstrip("%")


# Generous on the HAYSTACK side: any numeric literal counts as the number being
# shown, including one inside a threshold or a version, because the question here
# is only "is this value already in front of the reader somewhere".
_ANY_NUMBER = re.compile(
    r"\d[\d,]*(?:\.\d+)?(?:\s*[×x]\s*10\s*\^?\s*-?\d+)?\s*%?")


def _number_set(text: str) -> set[str]:
    """Every numeric literal in `text`, canonicalised.

    A SET, not a squashed haystack string: the obvious implementation — strip
    whitespace and substring-search — silently fails on exactly the reported case.
    Adjacent numeric cells "| 93.6 | 96.5 |" squash to "93.696.5", where a
    digit-boundary guard then REFUSES to match the real "96.5" (it is preceded by
    the "." of 93.6). The check would have reported clean on the caption it exists
    to catch.
    """
    return {n for n in (_norm_number(m.group(0)) for m in _ANY_NUMBER.finditer(text or ""))
            if n and any(ch.isdigit() for ch in n)}


def _restated_numbers(caption: str, own_cells: set[str],
                      shown: set[str]) -> list[dict]:
    """Caption numbers already shown in the item's own cells or elsewhere.

    Own cells are reported separately because restating your own table is the
    stronger finding — there is no argument for it at all, whereas quoting a body
    number can be a deliberate pointer to the key result.
    """
    out: list[dict] = []
    for verbatim, norm in _measure_tokens(caption):
        if norm in own_cells:
            out.append({"number": verbatim, "source": "own_cells",
                        "note": "already a cell in this table"})
        elif norm in shown:
            out.append({"number": verbatim, "source": "body_or_other_item",
                        "note": "already in a section body or another table"})
    return out


def lint_legends(state: State, slug: str) -> dict:
    """Scan every figure / table / supplementary legend. Returns
    {slug, findings: [...], summary: {...}}.

    Each finding: {item, type, number, word_count, level (info|warn), flags, and
    detail lists. Flags: long, body_duplication (EVERY duplicated sentence is
    enumerated in duplicated_spans, each with its section + a trim suggestion),
    number_restatement (>= 3 caption numbers already shown in the item's own cells
    or in the body — every one listed in duplicated_numbers so they clear in a
    single pass), interpretive, sample_roster_restatement (a sample-composition
    list also in the body), bare_cross_reference (a "…described/listed in
    Table/Results…" pointer), and table-only column_redundant /
    excluded_data_note (in caption_smells). `level` is warn if any flag is
    warn-grade, else info; an item with no flags is omitted.
    """
    sections = list_sections(state, slug)
    # Pre-shingle each section body once; the duplication check is containment of
    # a legend sentence's n-grams in a section (NOT Jaccard — a short sentence
    # against a long body never reaches 0.6 by Jaccard; containment is the
    # "does this sentence already live in the body?" question we actually want).
    sec_shingles = [(s.get("title") or s.get("key") or "?",
                     _shingles(s.get("body") or "")) for s in sections]
    # One normalised haystack of everything the submission SHOWS: every section
    # body plus every table's cells. Captions are deliberately excluded — an
    # item's own caption would trivially "contain" its own numbers, and two
    # captions quoting the same value is not the duplication either rule is about.
    all_tables = list_tables(state, slug, supplementary=None)
    cells_text = " ".join(
        v for t in all_tables
        for vals in _table_columns(t.get("content") or "").values()
        for v in vals if v
    )
    bodies_text = " ".join((x.get("body") or "") for x in sections)
    data_norm = _norm_for_presence(bodies_text + " " + cells_text)
    shown_numbers = _number_set(bodies_text) | _number_set(cells_text)

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

    def _interpretive(text: str) -> list[dict]:
        """Interpretive sentences, each with what triggered it.

        Per SENTENCE, not per document: the old version searched the whole text
        and returned bare matched phrases, so an author was told "interpretive:
        confirms" with no indication of where. Reporting the sentence is what
        lets the item clear in one editing pass, like duplicated_spans.
        """
        out: list[dict] = []
        for sent in _sentences(text):
            # finditer, not search: "matches or exceeds BRAKER3" has two
            # triggers in one pattern, and listing only the first reads as if the
            # rest were fine.
            hits = [m.group(0) for rx in _INTERP_STRONG for m in rx.finditer(sent)]
            # Comparisons only count outside an encoding description.
            if not _ENCODING_CX.search(sent):
                hits += [m.group(0) for rx in _INTERP_COMPARATIVE
                         for m in rx.finditer(sent)]
            if hits:
                out.append({"sentence": sent[:200],
                            "matches": sorted(set(h.lower() for h in hits))})
        return out

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
            flags.append("interpretive")
            # One interpretive sentence is a style note; several mean the legend
            # has grown a mini-Results. Escalating on VOLUME keeps the warn tier
            # meaningful now that the detector is broad enough to fire often.
            level = "warn" if len(interp) >= _INTERP_WARN_AT else (level or "info")
        # number_restatement: the caption reprinting numbers the reader already
        # sees. Ranked warn like body_duplication — the reporter's point is that
        # it is the MORE egregious duplication, and `long` (the flag authors most
        # reasonably ignore) cannot surface it, since a numeric-dense caption can
        # be short.
        own_cells = (_number_set(" ".join(
            v for vals in _table_columns(table_content).values() for v in vals if v))
            if table_content is not None else set())
        restated = _restated_numbers(text, own_cells, shown_numbers)
        if len(restated) >= _MIN_RESTATED:
            flags.append("number_restatement"); level = "warn"
        else:
            restated = []       # below the threshold this is emphasis, not a finding
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
        orphan_params = _caption_only_tokens(text, data_norm)
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
        elif restated:
            where = ("this table's own cells"
                     if any(r["source"] == "own_cells" for r in restated)
                     else "the body or another table")
            sugg = (f"{len(restated)} number(s) in this caption are already shown in "
                    f"{where} — see duplicated_numbers. A caption points at the key "
                    f"result; it does not reprint the data. Cut the walk-through and "
                    f"keep at most the single headline value, or replace it with what "
                    f"the reader should NOTICE in those numbers.")
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
            "duplicated_numbers": restated,
            "caption_only_params": orphan_params,
            # The sentence AND what triggered it, so the item clears in one pass.
            "interpretive_spans": interp,
            "interpretive_phrases": sorted(
                {m for i in interp for m in i["matches"]}),
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

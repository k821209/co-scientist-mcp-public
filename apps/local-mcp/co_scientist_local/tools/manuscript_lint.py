"""Deterministic manuscript QA lint (the prose analogue of the deck layout lint).

Addresses the three writing-quality failures reviewers reported:
  1. section leakage   — Results content inside Methods (or procedure inside Results)
  2. content duplication — the same sentence restated across sections
  3. non-academic style  — LLM-tell phrases / run-on sentences

`lint_manuscript(state, slug)` reads the paper's section bodies and returns
grouped warnings. Heuristic + conservative (report the offending sentence so a
human/agent can judge), bilingual EN + KO. Used as a hard done-gate: a section
isn't "complete" until its warnings are resolved.
"""
from __future__ import annotations

import re

from . import papers as _papers

# ── tunables ─────────────────────────────────────────────────────────────────
_DUP_JACCARD = 0.62        # sentence-pair similarity at/above this → duplication
_DUP_MIN_TOKENS = 6        # ignore very short sentences (boilerplate)
_LONG_SENTENCE_WORDS = 45  # a single sentence longer than this → run-on flag
_MAX_PER_KIND = 40         # cap noise

# Result signals that do NOT belong in Methods.
_RESULT_CUES = re.compile(
    r"""(\bp\s*[<>=]\s*0?\.\d+ | \bp[-\s]?values?\b
       | \bsignificant(?:ly)? | 유의(?:하|미|성|한)
       | \b(?:we\s+)?(?:found|observed|showed|demonstrated|revealed|
             identified|detected|confirmed)\b
       | 나타났 | 확인(?:하였|되었|됐) | 관찰되 | 유의하게
       | \b(?:increased|decreased|higher|lower|greater|reduced|elevated|
             improved)\b[^.]{0,40}?(?:\d|%|배|fold))""",
    re.I | re.X,
)
# Procedure signals that (in force) do NOT belong in Results.
_METHOD_CUES = re.compile(
    r"""(\b(?:was|were)\s+(?:performed|conducted|carried\s+out|prepared|
             incubated|centrifuged|amplified)\b
       | according\s+to\s+(?:the\s+)?manufacturer
       | 제조사(?:의)?\s*지침 | 프로토콜에\s*따라 | 지침(?:에|을)\s*따라
       | \bwe\s+used\b[^.]{0,50}?\b(?:kit|reagent|instrument|software|
             package|version|apparatus)\b
       | 를\s*사용하여\s*(?:수행|측정|분석)하 )""",
    re.I | re.X,
)
# Well-known LLM / non-academic tells (EN + KO).
_STYLE_TELLS = [
    (r"it is (?:important|worth|interesting) to note", "hedge filler — state it directly"),
    (r"it should be noted", "hedge filler — cut or state directly"),
    (r"plays? an? (?:crucial|key|vital|pivotal|important|significant) role",
     "vague importance claim — say what it does"),
    (r"a wide (?:range|variety) of", "vague quantifier — be specific"),
    (r"in the realm of", "wordy — 'in'"),
    (r"delve into", "LLM tell — 'examine'/'analyze'"),
    (r"shed(?:s|ding)? light on", "cliché — 'clarifies'/'shows'"),
    (r"pave(?:s|d)? the way", "cliché"),
    (r"it is well known that", "cut — cite instead"),
    (r"needless to say|last but not least", "filler"),
    (r"\butiliz(?:e|es|ed|ing)\b", "prefer 'use'"),
    (r"in order to\b", "prefer 'to'"),
    (r"due to the fact that", "prefer 'because'"),
    (r"매우 중요한 역할을", "막연한 중요성 — 무엇을 하는지 서술"),
    (r"아무리 강조해도 지나치지 않", "상투구 — 삭제"),
    (r"할 수 있을 것으로 사료된다", "완곡 남발 — 단정하거나 근거 제시"),
]
_STYLE_TELLS = [(re.compile(p, re.I), why) for p, why in _STYLE_TELLS]

# Which canonical sections each check applies to.
_METHODS_KEYS = {"methods", "materials", "materials_and_methods", "methods_and_materials"}
_RESULTS_KEYS = {"results"}


def _strip_markdown(body: str) -> str:
    """Drop code fences, tables, headings, images/links, HTML, citation tokens —
    keep only prose so sentence checks don't trip on structure."""
    text = body or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)      # code fences
    text = re.sub(r"`[^`]*`", " ", text)                      # inline code
    out_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith(">"):
            continue                                          # heading / table / quote
        if re.match(r"^[-*+]\s|^\d+\.\s", s):                 # list marker → keep text
            s = re.sub(r"^[-*+]\s|^\d+\.\s", "", s)
        out_lines.append(s)
    text = " ".join(out_lines)
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", text)        # images / links
    text = re.sub(r"\{doi:[^}]*\}|\{cite:[^}]*\}", " ", text)  # citation tokens
    text = re.sub(r"<[^>]+>", " ", text)                      # html (<br> etc.)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sentences(text: str) -> list[str]:
    """Split cleaned prose into sentences (EN . ! ? and KO endings)."""
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 1]


def _tokens(sentence: str) -> list[str]:
    """Normalised word tokens (keep Latin + Korean + digits)."""
    s = sentence.lower()
    return re.findall(r"[0-9a-z가-힣]+", s)


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


def lint_manuscript(state, slug: str) -> dict:
    """Return QA warnings for a paper's sections:

    {duplication: [...], section_leakage: [...], style: [...],
     summary: {total, by_kind}}

    Empty lists everywhere == a clean manuscript.
    """
    bundle = _papers.get_paper_state(state, slug)
    sections = bundle["sections"]

    # Flatten to (section_key, section_title, sentence, token_set) once.
    sents: list[tuple[str, str, str, set]] = []
    for sec in sections:
        key = sec.get("key", "")
        title = sec.get("title", key)
        for sent in _sentences(_strip_markdown(sec.get("body", ""))):
            toks = _tokens(sent)
            if len(toks) >= _DUP_MIN_TOKENS:
                sents.append((key, title, sent, set(toks)))

    # ── 1. duplication (near-duplicate sentences, any two sections/positions) ──
    duplication: list[dict] = []
    seen_pairs: set = set()
    for i in range(len(sents)):
        ki, ti, si, tsi = sents[i]
        for j in range(i + 1, len(sents)):
            kj, tj, sj, tsj = sents[j]
            sim = _jaccard(tsi, tsj)
            if sim >= _DUP_JACCARD:
                pair_key = (min(si, sj), max(si, sj))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                duplication.append({
                    "kind": "duplicate_sentence",
                    "cross_section": ki != kj,
                    "sections": sorted({ti, tj}),
                    "similarity": round(sim, 2),
                    "a": si[:200], "b": sj[:200],
                    "note": ("near-identical sentence " +
                             (f"in {ti} and {tj}" if ki != kj else f"twice in {ti}") +
                             " — state each fact once, in its home section"),
                })
    duplication.sort(key=lambda d: (-d["cross_section"], -d["similarity"]))

    # ── 2. section leakage ────────────────────────────────────────────────────
    leakage: list[dict] = []
    for key, title, sent, _t in sents:
        if key in _METHODS_KEYS and _RESULT_CUES.search(sent):
            leakage.append({
                "kind": "results_in_methods", "section": title, "sentence": sent[:220],
                "note": ("a finding/statistic in Methods — Methods states what you "
                         "DID (past tense, procedures); move results to Results"),
            })
        elif key in _RESULTS_KEYS and _METHOD_CUES.search(sent):
            leakage.append({
                "kind": "methods_in_results", "section": title, "sentence": sent[:220],
                "note": ("procedure detail in Results — Results states what you "
                         "FOUND; move the how-to to Methods"),
            })

    # ── 3. style tells + run-on sentences ─────────────────────────────────────
    style: list[dict] = []
    for key, title, sent, _t in sents:
        for rx, why in _STYLE_TELLS:
            m = rx.search(sent)
            if m:
                style.append({"kind": "style_tell", "section": title,
                              "match": m.group(0), "note": why, "sentence": sent[:180]})
        if len(re.findall(r"[A-Za-z]+", sent)) > _LONG_SENTENCE_WORDS:
            style.append({"kind": "run_on", "section": title,
                          "words": len(re.findall(r"[A-Za-z]+", sent)),
                          "note": f"sentence > {_LONG_SENTENCE_WORDS} words — split it",
                          "sentence": sent[:180]})

    duplication = duplication[:_MAX_PER_KIND]
    leakage = leakage[:_MAX_PER_KIND]
    style = style[:_MAX_PER_KIND]
    total = len(duplication) + len(leakage) + len(style)
    return {
        "slug": slug,
        "duplication": duplication,
        "section_leakage": leakage,
        "style": style,
        "summary": {
            "total": total,
            "by_kind": {
                "duplication": len(duplication),
                "section_leakage": len(leakage),
                "style": len(style),
            },
            "clean": total == 0,
        },
    }

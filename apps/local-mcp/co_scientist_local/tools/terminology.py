"""One thing, one name — the part of that a program can check.

Feedback 14fcdeea1b75 (2026-11-15). A commissioned report called two different
things by six names — "신규 유전자", "신규 locus", "신규 후보" for a gene added
where the reference had none, "대안 전사체", "추가 전사체" for a transcript added
to an existing gene — and while the names were mixed, "신규 18,934개" could be
read as a count of either. The transcript count (22,013) was not in the report
at all, and nothing showed it missing: one word stood for two numbers. The
author found it by reading; fifteen places in seven sections had to change.

`lint_manuscript` reported that text clean throughout. Its `overused_word`
counts one word used many times; this is the reverse, one thing under many
words, and no rule looked.

Two parts, kept apart because one is a verdict and the other is not:

**Declared** (`variant_findings`). The author says which names are one thing —
`set_paper_glossary` — and every use of a name they declared a variant is
reported with its section and sentence. Exact, so it counts toward the lint's
total. A sentence that uses the variant AND the canonical name is listed apart
and not counted: that sentence is defining or contrasting the two, which is
the one place both belong.

**Candidates** (`candidate_groups`). With or without a glossary: two-word names
that share their first word or their second, each used several times —
"신규 locus ×18 / 신규 후보 ×21". A list to read, never a finding, because
sharing a word is what DIFFERENT things do as well ("게놈 크기 / 게놈 특성").

Measured on 172 of the account's documents before choosing what to show. As
the report proposed it (each name used 3+ times): a median of 4.5 groups per
document, a mean of 10.4, 63 documents over ten and one with 79, nearly all of
them different things — the reported group sat among 23. At 5+ uses: median 0,
mean 2.1, 91 documents with none, five over ten; the reported group is third
of eleven in its document. So 5, the ten largest groups, and no place in
`total`. It still cannot tell one thing from two: it counts, and the reader
decides.

Not judged at all: a translation pair in a Korean document (locus / 로커스,
transcript / 전사체). No dictionary here knows that the two are the same word,
and a guess would be a second noisy list. Declared in the glossary, such a
pair is checked like any other.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

# Each name in a candidate group is used at least this often, and at most this
# many groups are listed. Both from the measurement above.
CANDIDATE_MIN_USES = 5
CANDIDATE_GROUPS = 10
MAX_FINDINGS = 60

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_NOISE = re.compile(
    r"`[^`\n]*`|!?\[[^\]]*\]\([^)]*\)|\{[a-z]+:[^}]*\}|<[^>]+>|https?://\S+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


# ── the glossary ─────────────────────────────────────────────────────────────

def clean_glossary(terms) -> list[dict]:
    """The glossary as it is stored, or ValueError naming what is wrong.

    Refused rather than repaired: a variant listed under two names, or a
    variant that IS another entry's canonical name, is a glossary that
    contradicts itself, and whichever reading was picked the lint would then
    report the other as an error in the prose.
    """
    if terms is None:
        return []
    if not isinstance(terms, list):
        raise ValueError("terms must be a list of {canonical, variants}")
    out: list[dict] = []
    owner: dict[str, str] = {}
    accepted: dict[str, str] = {}
    canonicals: dict[str, str] = {}
    for index, term in enumerate(terms, start=1):
        if not isinstance(term, dict):
            raise ValueError(f"term {index} is not an object with canonical and variants")
        canonical = " ".join(str(term.get("canonical") or "").split())
        if not canonical:
            raise ValueError(f"term {index} has no canonical name")
        if _key(canonical) in canonicals:
            raise ValueError(f"{canonical!r} is the canonical name of two terms")
        raw = term.get("variants") or []
        if isinstance(raw, str):
            raw = [raw]
        variants: list[str] = []
        for variant in raw:
            variant = " ".join(str(variant or "").split())
            if not variant or _key(variant) == _key(canonical):
                continue
            if _key(variant) in {_key(v) for v in variants}:
                continue
            if _key(variant) in owner:
                raise ValueError(
                    f"{variant!r} is listed as a variant of both "
                    f"{owner[_key(variant)]!r} and {canonical!r}")
            owner[_key(variant)] = canonical
            variants.append(variant)
        # A short form the document itself declares — "이하 '신규 후보'는 신규
        # locus 후보를 가리킨다" — is a second ACCEPTED name: counted, never a
        # finding. Without this a declared abbreviation had to go under
        # `variants`, and its 24 ordinary uses all became findings (feedback
        # c0b0e65d26cc).
        raw_short = term.get("abbreviations") or []
        if isinstance(raw_short, str):
            raw_short = [raw_short]
        abbreviations: list[str] = []
        for short in raw_short:
            short = " ".join(str(short or "").split())
            if not short or _key(short) == _key(canonical):
                continue
            if _key(short) in {_key(a) for a in abbreviations}:
                continue
            if _key(short) in {_key(v) for v in variants}:
                raise ValueError(
                    f"{short!r} is both an abbreviation and a variant of {canonical!r} — "
                    "it is accepted or it is not")
            if _key(short) in owner:
                raise ValueError(
                    f"{short!r} is an abbreviation of {canonical!r} and a variant of "
                    f"{owner[_key(short)]!r}")
            accepted[_key(short)] = canonical
            abbreviations.append(short)
        if not variants and not abbreviations:
            raise ValueError(f"{canonical!r} has no variants — there is nothing to look for")
        canonicals[_key(canonical)] = canonical
        entry = {"canonical": canonical, "variants": variants}
        if abbreviations:
            entry["abbreviations"] = abbreviations
        note = " ".join(str(term.get("note") or "").split())
        if note:
            entry["note"] = note
        out.append(entry)
    for variant_key, canonical in owner.items():
        if variant_key in canonicals and canonicals[variant_key] != canonical:
            raise ValueError(
                f"{canonicals[variant_key]!r} is a canonical name and also a variant "
                f"of {canonical!r}")
        if variant_key in accepted:
            raise ValueError(
                f"a name is a variant of {canonical!r} and an abbreviation of "
                f"{accepted[variant_key]!r}")
    return out


def _key(name: str) -> str:
    return " ".join(name.split()).lower()


def _pattern(name: str) -> re.Pattern:
    """`name` wherever it stands: any run of spaces between its words, either
    case, and — at a Latin edge — not inside a longer Latin word ("locus" is
    not in "blocus"; a Korean particle straight after it is still a match)."""
    words = [re.escape(word) for word in name.split()]
    body = r"\s+".join(words)
    lead = r"(?<![A-Za-z0-9])" if re.match(r"[A-Za-z0-9]", name) else ""
    tail = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", name) else ""
    return re.compile(lead + body + tail, re.IGNORECASE)


def _units(body: str) -> list[str]:
    """The text in the pieces a finding points at: a sentence of prose, a
    heading, a row of a table. Code is not prose; everything else is — a
    variant in a table header is exactly where one word came to mean two
    numbers."""
    text = _FENCE.sub(" ", body or "")
    out: list[str] = []
    for line in text.splitlines():
        line = _INLINE_NOISE.sub(" ", line).strip()
        if not line or set(line) <= set("|:- "):
            continue
        if line.startswith(("#", "|")):
            out.append(" ".join(line.lstrip("#").split()))
            continue
        line = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line)
        out.extend(part.strip() for part in _SENTENCE_END.split(line) if part.strip())
    return out


def variant_findings(sections: list[dict], glossary: list[dict],
                     display_items: list[dict] | None = None) -> dict:
    """Every use of a declared variant.

    {variants: [...], contrasted: [...], by_term: {...}, examined: {...}}.
    `variants` are the findings; `contrasted` are sentences that also carry the
    canonical name and are listed without being counted.
    """
    terms = [(entry["canonical"],
              # Longest first: an abbreviation that CONTAINS the canonical name
              # ("추가 전사체 후보") is counted as itself, not as the name plus a word.
              [(name, _pattern(name))
               for name in sorted((entry["canonical"], *entry.get("abbreviations", ())),
                                  key=len, reverse=True)],
              [(variant, _pattern(variant)) for variant in entry["variants"]])
             for entry in glossary]
    variants: list[dict] = []
    contrasted: list[dict] = []
    by_term: dict[str, dict[str, int]] = {
        entry["canonical"]: {"canonical": 0,
                             **{a: 0 for a in entry.get("abbreviations", ())},
                             **{v: 0 for v in entry["variants"]}}
        for entry in glossary}
    units = 0

    def scan(where: dict, text: str) -> None:
        nonlocal units
        for unit in _units(text):
            units += 1
            for canonical, accepted_names, names in terms:
                # The accepted names — the canonical one and any declared
                # abbreviation — are counted and taken out of the way. A variant
                # inside one ("전사체 모델" in "추가 전사체 모델") is that name,
                # not a variant of it.
                hits = 0
                rest = unit
                for accepted_name, accepted_re in accepted_names:
                    found = len(accepted_re.findall(rest))
                    hits += found
                    key = "canonical" if accepted_name == canonical else accepted_name
                    by_term[canonical][key] += found
                    rest = accepted_re.sub(lambda m: " " * len(m.group(0)), rest)
                for variant, variant_re in names:
                    found = len(variant_re.findall(rest))
                    if not found:
                        continue
                    by_term[canonical][variant] += found
                    row = {**where, "variant": variant, "canonical": canonical,
                           "count": found, "sentence": unit[:200]}
                    (contrasted if hits else variants).append(row)

    for section in sections:
        scan({"section": section.get("key") or "", "title": section.get("title") or ""},
             section.get("body") or "")
    for item in display_items or []:
        scan({"item": item["item"]}, item["text"])
    return {
        "variants": variants[:MAX_FINDINGS],
        "total": sum(row["count"] for row in variants),
        "contrasted": contrasted[:MAX_FINDINGS],
        "by_term": by_term,
        "examined": {"terms": len(glossary), "units": units},
    }


# ── candidates: names that share a word ──────────────────────────────────────

_STOP_EN = frozenset("""
    the a an of in on at to for from by with and or but as is are was were be been this that
    these those it its we our their each every all both more most less than not no which who
    whose when where while into over under between among per via also only such same other
    then there here can may will would should could has have had do does did using used use
    based show shows shown found
""".split())
_STOP_KO = frozenset("""
    및 등 또는 그리고 그러나 하지만 본 각 이 그 저 한 수 것 때 중 후 전 더 약 총 즉 위 아래 대한
    대해 통해 위해 따라 의해 관한 같은 다른 모든 여러 일부 해당 경우 이상 이하 대비 모두 기준으로
    있다 없다 한다 된다 이다 있는 없는 하는 되는
""".split())
_KO_PARTICLES = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "이라는", "라는",
                 "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만")
_KO_WORD = re.compile(r"[가-힣]{2,}")
_EN_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def _bare(word: str) -> str:
    """A word as it is counted: punctuation off its ends, one Korean particle
    off its tail, Latin lowercased."""
    word = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", word)
    if word and "가" <= word[-1] <= "힣":
        for particle in _KO_PARTICLES:
            if word.endswith(particle) and len(word) - len(particle) >= 2:
                return word[: -len(particle)]
        return word
    return word.lower()


# How a Korean predicate or a connective ends. "유전자 확인하였다" is a noun and
# what was done to it, not a name — and every sentence has one, so with these
# counted the largest "group" in a document was whatever its verbs were.
_KO_NOT_A_NOUN_END = (
    "다", "하여", "하고", "하며", "하면", "해서", "하는", "하지", "했던", "하게",
    "되어", "되고", "되며", "되면", "되는", "되지", "된", "한", "할", "될",
    "않은", "않는", "않고", "않으면", "있는", "없는", "있고", "없고", "있어", "없어",
)


def _names_a_thing(word: str) -> bool:
    if _KO_WORD.fullmatch(word):
        return word not in _STOP_KO and not word.endswith(_KO_NOT_A_NOUN_END)
    if _EN_WORD.fullmatch(word):
        return word not in _STOP_EN
    return False


def candidate_groups(sections: list[dict]) -> list[dict]:
    """Two-word names that share a word, each used CANDIDATE_MIN_USES times or
    more — the largest CANDIDATE_GROUPS of them. See the module docstring for
    why this is a list and not a finding."""
    uses: Counter = Counter()
    where: dict[tuple[str, str], set[str]] = defaultdict(set)
    for section in sections:
        key = section.get("key") or ""
        for unit in _units(section.get("body") or ""):
            words = [_bare(word) for word in unit.split()]
            for first, second in zip(words, words[1:]):
                if _names_a_thing(first) and _names_a_thing(second):
                    uses[(first, second)] += 1
                    where[(first, second)].add(key)
    strong = {pair: count for pair, count in uses.items() if count >= CANDIDATE_MIN_USES}
    by_first: dict[str, list] = defaultdict(list)
    by_second: dict[str, list] = defaultdict(list)
    for (first, second), count in strong.items():
        by_first[first].append(((first, second), count))
        by_second[second].append(((first, second), count))
    groups = []
    for shared, role, table in (*((w, "first", by_first[w]) for w in by_first),
                                *((w, "second", by_second[w]) for w in by_second)):
        if len(table) < 2:
            continue
        names = sorted(table, key=lambda row: -row[1])
        groups.append({
            "shared_word": shared,
            "position": role,
            "names": [{"name": " ".join(pair), "count": count,
                       "sections": sorted(where[pair])} for pair, count in names],
            "uses": sum(count for _, count in names),
        })
    groups.sort(key=lambda group: (-group["uses"], group["shared_word"], group["position"]))
    return groups[:CANDIDATE_GROUPS]

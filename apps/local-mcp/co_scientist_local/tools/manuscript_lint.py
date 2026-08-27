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

from . import doc_profile as _doc_profile
from . import papers as _papers
from .figures import list_figures as _list_figures
from .tables import list_tables as _list_tables

# ── tunables ─────────────────────────────────────────────────────────────────
_DUP_JACCARD = 0.62        # sentence-pair similarity at/above this → duplication
_DUP_MIN_TOKENS = 6        # ignore very short sentences (boilerplate)
_LONG_SENTENCE_WORDS = 45  # a single sentence longer than this → run-on flag
_MAX_PER_KIND = 40         # cap noise

# Result signals that do NOT belong in Methods — split by confidence, because a
# bare reporting verb is ALSO an ordinary adjective. Reported from a real Methods
# section: "…appears in the null as well as in the observed value" was flagged as
# a finding on the strength of "observed". False positives here are expensive —
# they train the reader to dismiss the rule.
_RESULT_CUES_STRONG = re.compile(
    r"""(\bp\s*[<>=]\s*0?\.\d+ | \bp[-\s]?values?\b
       | \bsignificant(?:ly)?\b | 유의(?:하|미|성|한)
       | \bwe\s+(?:found|observed|showed|demonstrated|revealed|
             identified|detected|confirmed)\b
       | 나타났 | 확인(?:하였|되었|됐) | 관찰되 | 유의하게
       | \b(?:increased|decreased|higher|lower|greater|reduced|elevated|
             improved)\b[^.]{0,40}?(?:\d|%|배|fold))""",
    re.I | re.X,
)
# The same verbs without "we" — a finding when used as a verb ("observed a shift"),
# procedure prose when used as a modifier ("the observed value", "these identified
# genes"). The determiner in front is the discriminator.
_WEAK_REPORT_VERB = re.compile(
    r"""\b(?:found|observed|showed|demonstrated|revealed|identified|detected|
             confirmed)\b""",
    re.I | re.X,
)
_ADJECTIVAL_LEAD = re.compile(
    r"\b(?:the|a|an|these|those|this|that|our|its|their|any|each|both|all)\s+$", re.I)


def _result_cue(sent: str) -> "re.Match | None":
    """A reported finding in `sent`, or None. See _RESULT_CUES_STRONG."""
    m = _RESULT_CUES_STRONG.search(sent)
    if m:
        return m
    for m in _WEAK_REPORT_VERB.finditer(sent):
        if not _ADJECTIVAL_LEAD.search(sent[:m.start()]):
            return m
    return None


# A MEASURED MAGNITUDE reported in Methods — the shape a methods-paper benchmark
# takes, and the biggest blind spot the cue list had: it looked for statistical
# language, so an entire Methods paragraph of sizes, times and memory ("per-sample
# wall-clock time was 52.1 ± 8.5 s, peak resident memory was approximately
# 3.0 GB, end-to-end runtime was approximately 88 minutes") passed clean while
# appearing NOWHERE in Results.
#
# The discriminator is the verb: a past-tense report OF A MAGNITUDE ("was 52.1 s",
# "averaging 5.5 MB") versus a past-tense ACTION that happens to carry a duration
# ("were incubated for 30 s", "were shuffled up to 10,000 times"). Hence only
# hedge words may sit between the verb and the number — an action participle there
# means it is a procedure.
#
# Units are matched CASE-SENSITIVELY (via a scoped (?i:…) on the verb only): "kb"
# and "Mb" are genomic coordinates and legitimately parameterise Methods, while
# "KB"/"MB" are storage sizes.
_MEASURED_MAGNITUDE = re.compile(
    r"(?i:\b(?:was|were|averaged?|averaging|took|taking|required|requiring|"
    r"reached|reaching|peaked\s+at|totall?ed|totall?ing|measured|measuring)\b)"
    r"(?:\s+(?i:approximately|about|roughly|around|nearly|only|just|up\s+to|"
    r"on\s+average))?"
    r"\s*~?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:±|\+/-)\s*\d[\d.]*)?[\s-]*"
    r"(?:[KMGT]i?B|bytes?|s|sec|secs|second|seconds|min|mins|minute|minutes|"
    r"h|hr|hrs|hour|hours|ms|fold|×)\b"
)
# "…on a 64-core, 256 GB node" is a machine SPEC, not an outcome. The giveaway is
# a hardware noun immediately after the unit.
_SPEC_TAIL = re.compile(
    r"^\W{0,3}(?:nodes?|machines?|servers?|workstations?|clusters?|hosts?|CPUs?|"
    r"GPUs?|cores?|processors?|threads?|instances?)\b", re.I)


def _measured_magnitude(sent: str) -> "re.Match | None":
    for m in _MEASURED_MAGNITUDE.finditer(sent):
        if not _SPEC_TAIL.match(sent[m.end():m.end() + 24]):
            return m
    return None


# Numeric literals worth cross-checking between sections and display items:
# 2+ digits, or any decimal. Single digits are everywhere and carry no signal.
_SIGNIFICANT_NUMBER = re.compile(r"\d[\d,]*\.\d+|\d[\d,]{1,}")


def _numbers(text: str) -> set:
    """Normalised numeric literals in `text` (commas dropped so 6,255 == 6255)."""
    return {m.group(0).replace(",", "") for m in _SIGNIFICANT_NUMBER.finditer(text or "")}


# Citation/reference tokens the system resolves. Anything else in braces is a
# token that will never resolve.
#
# This is the quiet class of failure: {sharma2005} instead of {cite:sharma2005}
# saves clean, lints clean, and exports clean — the reference simply is not in
# the bibliography of the finished PDF. Every other citation error here is loud
# (a hallucinated DOI 404s at registration), and `validate_references` reports
# the same empty `manuscript_contexts` for "registered but not cited yet",
# which is a normal state, so the signal was indistinguishable from nothing
# being wrong (feedback 3e13dcc07a58).
_KNOWN_TOKEN_PREFIXES = ("doi:", "cite:", "ref:", "fig:", "tab:")
_BRACE_TOKEN = re.compile(r"\{([^{}\n]{1,120})\}")
# Math is the one place braces are structural rather than a token — `$\frac{a}{b}$`
# must not be read as a citation key.
_MATH_SPAN = re.compile(r"\$\$.*?\$\$|\$[^$\n]{1,200}\$", re.S)


def _unresolved_tokens(body: str) -> list[str]:
    """Brace tokens in `body` that no resolver claims, in order of appearance."""
    text = re.sub(r"```.*?```", " ", body or "", flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = _MATH_SPAN.sub(" ", text)
    out: list[str] = []
    for m in _BRACE_TOKEN.finditer(text):
        inner = m.group(1).strip()
        # Case-sensitive: {Fig:2} is a typo for {fig:2} and resolves to nothing,
        # so reporting it is the whole point.
        if any(inner.startswith(pre) for pre in _KNOWN_TOKEN_PREFIXES):
            continue
        out.append(m.group(0))
    return out


# Citation syntaxes this project does NOT use, but that a writer reaches for by
# habit: pandoc/BibTeX `[@key]`, LaTeX `\cite{key}`, and a bare numeric `[12]`
# that was typed rather than rendered from a token.
#
# These are worse than an unknown brace token, because nothing about them looks
# broken. `[@kim2026]` is the most standard citation syntax in markdown; it
# renders as literal text, it is invisible to the numbering pass, and
# validate_references finds no `{doi:}` occurrence to check context against — so
# the manuscript reads fine on screen and silently has no citations at all.
_FOREIGN_CITATION = [
    ("pandoc", re.compile(r"\[@[A-Za-z][\w:.#$%&+?<>~/-]*(?:\s*;\s*@[\w:.#$%&+?<>~/-]+)*\]")),
    ("latex", re.compile(r"\\(?:cite|citep|citet|autocite)\s*(?:\[[^\]]*\])?\{[^}]+\}")),
]
# Bare `[12]` / `[3,4]` / `[7-10]`. Only flagged when the manuscript has NO
# tokens anywhere: in a paper that uses tokens properly, a stray bracketed
# number is far more likely to be a range or an array index than a citation.
_BARE_NUMERIC_CITATION = re.compile(r"(?<![\w\]])\[\d{1,3}(?:\s*[,\u2013-]\s*\d{1,3})*\](?!\()")


def _foreign_citations(body: str, tokens_used: bool) -> list[tuple[str, str]]:
    """(syntax, matched text) for citations written in another system's syntax."""
    text = re.sub(r"```.*?```", " ", body or "", flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = _MATH_SPAN.sub(" ", text)
    # Markdown links and images own their brackets — [text](url) and ![](figure:1)
    # are not citations.
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", text)
    out = [(name, m.group(0)) for name, rx in _FOREIGN_CITATION for m in rx.finditer(text)]
    if not tokens_used:
        out += [("numeric", m.group(0)) for m in _BARE_NUMERIC_CITATION.finditer(text)]
    return out


# Conventional significance thresholds. Stating one is an ANALYSIS PLAN, which
# is what Methods is for; it is not a measured value that went missing from
# Results. Scoped to the checks below — a real finding OF 0.05 would be reported
# with a magnitude alongside it and is not what these two checks look at.
_ALPHA_LEVELS = {"0.05", "0.01", "0.001"}

# A capitalised or CamelCase word immediately before a number: "STEADi 24",
# "GENTi 32", "Illumina 6000", "NanoDrop 2000". The number is part of an
# instrument's NAME, so it can never appear in Results and no amount of writing
# will clear the warning. Excluded only when the word is not the sentence
# opener, since "The 24 samples…" starts with a capital for grammar, not naming.
_NAME_LEAD = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*|[A-Z]{2,})\s+$")


def _partition_numbers(sentences: list[str]) -> tuple[set, set]:
    """(every number, numbers that ONLY ever appear bound to a proper name).

    The second set is subtracted from the first elsewhere. It is "only ever"
    rather than "ever" on purpose: if 24 also appears as "24 samples" somewhere,
    the model-number occurrence must not buy it an exemption."""
    every: set = set()
    bound: set = set()
    free: set = set()
    for sent in sentences:
        for m in _SIGNIFICANT_NUMBER.finditer(sent):
            num = m.group(0).replace(",", "")
            every.add(num)
            lead = _NAME_LEAD.search(sent[:m.start()])
            (bound if (lead and lead.start() > 0) else free).add(num)
    return every, bound - free


# The vocabulary of a statistical ANALYSIS PLAN — what test was applied, at what
# threshold. "Significant ANOVAs were followed by Tukey's HSD test at p < 0.05"
# is a correct Methods sentence by any style guide, but it trips the result cue
# on both `significant` and `p < 0.05`.
_STAT_PROCEDURE = re.compile(
    r"""\b(?: ANOVAs? | ANCOVAs? | MANOVAs? | t-tests? | tests? | Tukey | HSD
           | Bonferroni | Dunnett | Scheff | Kruskal | Wilcoxon | chi-square
           | post[-\s]?hoc | correction | corrected | threshold | alpha
           | significance\s+level | considered\s+(?:statistically\s+)?significant
           | (?:were|was)\s+(?:analy[sz]ed|compared|performed|conducted|used|set)
        )\b""",
    re.I | re.X,
)


def _analysis_plan(sent: str) -> bool:
    """True when a Methods sentence STATES THE TEST rather than a finding.

    Three conditions, all required. The report verb is the load-bearing one:
    "The treatment showed a significant effect in the ANOVA (p < 0.05)" also
    names a test and carries only an alpha level, and that sentence IS a result
    sitting in Methods. Naming the test does not earn an exemption; naming the
    test *without reporting anything* does."""
    if not _STAT_PROCEDURE.search(sent):
        return False
    if _WEAK_REPORT_VERB.search(sent):
        return False
    nums = {m.group(0).replace(",", "") for m in _SIGNIFICANT_NUMBER.finditer(sent)}
    return nums <= _ALPHA_LEVELS


# Figure/Table cited as a noun phrase instead of parenthetically. The author's
# convention: "…using metric MDS (Figure 4A)", never "The resulting projection is
# Figure 4A."
_DISPLAY_REF = re.compile(r"\b(?:S?Figures?|S?Tables?)\s+\d+[A-D]?\b")


def _outside_parentheses(sent: str, start: int) -> bool:
    """True when the character at `start` is not inside a (...) group.

    Scans OUTWARD for the enclosing delimiter rather than looking at adjacent
    characters: the multi-item parentheticals the harness already writes —
    "(Figures 3A, 4, Table 1; SFigure 2)", "(STable 6, Figure 6)" — put a comma or
    semicolon between the "(" and the match. Checking the two neighbouring
    characters produced 6 false positives out of 11 hits on a real manuscript.
    """
    depth = 0
    for ch in sent[:start]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
    return depth == 0


# A line that is mostly one italic span. By the /response-letter convention a
# reviewer's verbatim point is written in italics ("**1.** *<reviewer point>*")
# while our reply is a blockquote — and `_strip_markdown` already drops blockquote
# lines, so the ONLY prose being style-checked in a response letter was the
# reviewer's own words. `run_on` fired on a 55-word quoted comment we are not
# allowed to edit. Threshold rather than any-italics: a letter may italicise a
# gene name inside its own sentence, and that sentence should still be checked.
_ITALIC_SPAN = re.compile(r"(?<!\*)\*([^*\n]{4,})\*(?!\*)")
_QUOTED_SHARE = 0.6


def _is_quoted_source(line: str) -> bool:
    """True when `line` is predominantly an italic quotation — someone else's
    sentence, reproduced as evidence, and not ours to fix."""
    stripped = line.strip()
    if len(stripped) < 12:
        return False
    inside = sum(len(m.group(1)) for m in _ITALIC_SPAN.finditer(stripped))
    return inside / len(stripped) >= _QUOTED_SHARE


# "Major 3" with nobody's name on it. In a response letter whose OWN sections are
# also headed "Major 1-4", a bare number reads as a self-reference and the reviewer
# cannot tell we are pointing back at them. Correspondence only.
_REVIEWER_REF = re.compile(r"\b(?:Major|Minor|Comment|Point)\s+\d+\b")
_ATTRIBUTED = re.compile(r"reviewer(?:'s|s')?\s*\d*\s*$", re.I)


def _unattributed_reviewer_ref(sent: str) -> "re.Match | None":
    for m in _REVIEWER_REF.finditer(sent):
        lead = sent[max(0, m.start() - 30):m.start()]
        if not _ATTRIBUTED.search(lead):
            return m
    return None


# Writing about the STATISTIC instead of the object it measures. Four corrections
# in one session traced to this single habit, three of them on one sentence: "the
# chance adjustment is not biased against fragmented genes, in that their typical
# adjusted value is no lower than other genes'" — precise, and nearly unreadable.
# The accepted version made the biological object the subject: "Fragmentation does
# not lower the score a gene typically gets. It lowers the highest score a gene can
# get." Estimator-property language is correct in METHODS, where the estimator IS
# the subject, so this fires everywhere else.
_ESTIMATOR_VOICE = [
    (r"\bis (?:not )?biased\b", "estimator property — make the biological object the subject"),
    (r"\bunbiased\b", "estimator property — say what it does to the object"),
    (r"\bin expectation\b", "estimator property — state the effect on the object"),
    (r"\bpenali[sz]ed on average\b", "estimator property — say what happens to the gene/sample"),
    (r"\b(?:adjusted|corrected) value is no (?:lower|higher)\b",
     "estimator property — state it as an event ('X does not lower Y')"),
    (r"\bdoes not receive an inflated\b", "estimator property — name the object and the effect"),
    (r"\btypical (?:adjusted|corrected) value\b", "estimator property — restate as an event"),
]
_ESTIMATOR_VOICE = [(re.compile(p, re.I), why) for p, why in _ESTIMATOR_VOICE]

# The OTHER failure mode, and the reason the two ship together: correcting
# estimator-voice overshoots into conversation ("the number that decides this",
# "does not tell you that"), which was rejected in the same session. Plain is not
# colloquial; both axes have to hold.
_COLLOQUIAL = [
    (r"\byou(?:r|rs)?\b", "second person — academic register is impersonal"),
    (r"\btells? you\b", "conversational — state the relation"),
    (r"\bdecides this\b", "vague verb standing in for a technical relation"),
    (r"\bsays so\b", "conversational — name what is claimed"),
]
_COLLOQUIAL = [(re.compile(p, re.I), why) for p, why in _COLLOQUIAL]


# Prose whose frame is the AUTHORING SESSION rather than the work. For a revision
# the reader's frame is exactly (what they received) → (what they are receiving
# now); a draft they never saw, or an option we rejected, is noise, and reads as
# retracting something that never existed for them. Caught three times by hand on
# one revision, in the manuscript, the response letter and the cover letter — and
# it produced a factual error too (a removed panel described as having shown the
# 285 accessions, when the panel the reviewers saw was the 69-accession one).
_INSIDER_CONTEXT = [
    # Draft history — the reader saw the submitted version, not our drafts.
    (r"an earlier (?:draft|version)", "draft history — the reader never saw it"),
    (r"a previous (?:draft|version)", "draft history — the reader never saw it"),
    (r"in our first attempt", "draft history — the reader never saw it"),
    (r"\bwe initially\b", "draft history — state the current claim, not its history"),
    (r"\boriginally,? we\b", "draft history — state the current claim, not its history"),
    (r"\bwe had written\b", "draft history — the reader never saw it"),
    # Roads not taken — if we didn't do it, there is nothing to report.
    (r"\bwe considered\b", "road not taken — if it was rejected, don't raise it"),
    (r"\bwe decided against\b", "road not taken — if it was rejected, don't raise it"),
    (r"\bwe (?:chose|opted) not to\b", "road not taken — don't raise it"),
    (r"\bwe opted against\b", "road not taken — don't raise it"),
    # Authoring-process narration — the process is not the finding.
    (r"\bon reflection\b", "narrates the authoring process, not the work"),
    (r"\bwe (?:judged|felt|realised|realized)\b",
     "narrates the authoring process — state the claim and its basis"),
    (r"more than we (?:expected|anticipated)",
     "narrates the authoring process, not the work"),
    # Reader-management asides — write one document for one reader.
    (r"for readers who\b", "reader-management aside — decide, don't offer options"),
    (r"readers who (?:want|prefer)\b", "reader-management aside — decide"),
    (r"a reader who prefers\b", "reader-management aside — decide"),
]
_INSIDER_CONTEXT = [(re.compile(p, re.I), why) for p, why in _INSIDER_CONTEXT]
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
    # Forward references / signpost pointers — keep each paragraph self-contained.
    (r"(?:is|are|will be) (?:developed|discussed|described|addressed|presented|examined) (?:in|below|later)(?: the)? (?:Discussion|Results|Methods|section|below)",
     "forward reference — say it here, don't point elsewhere"),
    (r"as (?:discussed|described|shown|noted|mentioned) (?:below|later|above|earlier)",
     "signpost pointer — state it in place or cross-reference a figure/section number"),
    (r"\bsee (?:the )?(?:Discussion|Results|Methods|section) below\b",
     "forward pointer — reorder so the reader has it when needed"),
    # 'not X but Y' writerly construction — prefer a plain declarative.
    (r"\bnot\b[^.,;]{1,40}\bbut (?:rather|instead)\b",
     "'not X but Y' — state Y plainly"),
    (r"\brather than a\b", "writerly contrast — a plain declarative usually reads clearer"),
    (r"매우 중요한 역할을", "막연한 중요성 — 무엇을 하는지 서술"),
    (r"아무리 강조해도 지나치지 않", "상투구 — 삭제"),
    (r"할 수 있을 것으로 사료된다", "완곡 남발 — 단정하거나 근거 제시"),
]
_STYLE_TELLS = [(re.compile(p, re.I), why) for p, why in _STYLE_TELLS]

# Rhetorical / AI-favored words that read as filler when repeated — flagged when
# one appears >= _RHETORICAL_MAX times across the manuscript (a PI bounced
# "vetted" used 6x). Domain nouns legitimately repeat, so this is a CURATED list
# of non-domain rhetorical words only, to keep false positives near zero.
_RHETORICAL = {
    "vetted", "robust", "robustly", "leverage", "leverages", "leveraged",
    "delve", "seamless", "seamlessly", "comprehensive", "comprehensively",
    "nuanced", "intricate", "pivotal", "crucial", "crucially", "notably",
    "importantly", "arguably", "meticulous", "meticulously", "underscore",
    "underscores", "underscoring", "showcase", "showcases", "myriad",
    "furthermore", "moreover", "additionally",
}
_RHETORICAL_MAX = 4

# Em-dash (U+2014) or a double-hyphen used as one. NOT an en-dash (– U+2013,
# legitimate numeric range) or a minus (− U+2212). Advisory — many journal
# reviewers read em-dashes as informal.
_EM_DASH = re.compile(r"—|(?<=\w)--(?=\w)|(?<=\w) -- (?=\w)")

# Bare comparatives that hide WHAT varies (size? count? length?) — advisory.
# Only flagged when NOT part of an explicit "… than …" comparison (checked in
# code): "a larger set" fires; "higher than the 2-fold cutoff" does not.
_VAGUE_COMPARATIVE = re.compile(
    r"\b(larger|bigger|smaller|greater|higher|lower)\b", re.I)


def _is_vague_comparative(sent: str, m: "re.Match") -> bool:
    """True if the comparative isn't resolved by a 'than …' clause soon after."""
    tail = sent[m.end():m.end() + 40].lower()
    return " than " not in tail and not tail.lstrip().startswith("than ")

# Which canonical sections each check applies to.
_METHODS_KEYS = {"methods", "materials", "materials_and_methods", "methods_and_materials"}
_RESULTS_KEYS = {"results"}


def _strip_markdown(body: str, *, drop_quotes: bool = False) -> str:
    """Drop code fences, tables, headings, images/links, HTML, citation tokens —
    keep only prose so sentence checks don't trip on structure.

    `drop_quotes` additionally removes lines that are predominantly an italic
    quotation. Used for correspondence, where by convention those lines are the
    REVIEWER's verbatim words: they are evidence, not our prose, and we do not get
    to edit them, so no check should fire on them."""
    text = body or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)      # code fences
    text = re.sub(r"`[^`]*`", " ", text)                      # inline code
    out_lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith(">"):
            continue                                          # heading / table / quote
        if drop_quotes and _is_quoted_source(s):
            continue                                          # someone else's sentence
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
    paper = bundle.get("paper") or {}

    # Captions/legends are prose too. Run the sibling lint and fold a summary in
    # so this tool's `clean` cannot mean "clean, except where I did not look".
    from . import legend_lint as _legend_lint
    _legends = _legend_lint.lint_legends(state, slug)
    display_items = {
        "total": _legends["summary"]["total"],
        "warn": _legends["summary"]["warn"],
        "info": _legends["summary"]["info"],
        "items": [
            {"item": f["item"], "level": f["level"], "flags": f["flags"],
             "word_count": f["word_count"]}
            for f in _legends["findings"]
        ],
        "detail": "run lint_legends(slug) for the offending sentences",
    }

    # Which sections are correspondence. The section KEY is checked first, but a
    # letter is often its own paper, and then its keys are structural rather than
    # type-declaring — a real response letter came back with `opening`,
    # `reviewer1_major`, `reviewer2`, a cover letter with `letter`. Key matching
    # alone therefore classified every one of them as manuscript and the profile
    # never engaged on the documents it exists for, so the paper decides when the
    # key does not. See doc_profile.resolve_kind.
    corr_by_key = {
        sec.get("key", ""): _doc_profile.is_correspondence(sec.get("key", ""), paper)
        for sec in sections
    }

    # Flatten to (section_key, section_title, sentence, token_set) once.
    sents: list[tuple[str, str, str, set]] = []
    unresolved: list[dict] = []
    # Whether the manuscript uses the real convention ANYWHERE, which decides
    # how a bare `[12]` should be read.
    tokens_used = any(
        re.search(r"\{(?:doi|cite|ref):", sec.get("body", "") or "")
        for sec in sections)
    for sec in sections:
        key = sec.get("key", "")
        title = sec.get("title", key)
        for syntax, match in _foreign_citations(sec.get("body", ""), tokens_used):
            unresolved.append({
                "kind": "foreign_citation_syntax", "section": title,
                "token": match, "syntax": syntax,
                "note": (
                    f"{match} is {syntax} citation syntax, which this project "
                    "does not resolve — citations are {doi:10.…} when a DOI "
                    "exists and {cite:key} when one does not. Nothing about "
                    "this looks broken: it renders as literal text, the "
                    "numbering pass does not see it, and validate_references "
                    "has no occurrence to check, so the paper reads as cited "
                    "and exports with no bibliography entry for it."),
            })
        for tok in _unresolved_tokens(sec.get("body", "")):
            unresolved.append({
                "kind": "unresolved_token", "section": title, "token": tok,
                "note": ("no resolver handles this token — citations are "
                         "{doi:10.…} when a DOI exists and {cite:key} when one "
                         "does not; display items are {fig:N}/{tab:N}. It will "
                         "vanish from the export instead of failing"),
            })
        body = _strip_markdown(sec.get("body", ""), drop_quotes=corr_by_key.get(key, False))
        for sent in _sentences(body):
            toks = _tokens(sent)
            if len(toks) >= _DUP_MIN_TOKENS:
                sents.append((key, title, sent, set(toks)))

    # ── 1. duplication (near-duplicate sentences, any two sections/positions) ──
    duplication: list[dict] = []
    suppressed: list[dict] = []
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
                # "Say it once" is a MANUSCRIPT rule. A response/cover letter
                # restating what the manuscript now says is doing its job — the
                # recipient is deciding whether a point was met, so the letter
                # tells them and points. Flagging it pushes the document the wrong
                # way. Recorded rather than dropped, so the exemption is auditable
                # if it is ever wrong.
                #
                # Scoped to DIFFERENT sections: repetition ACROSS documents that
                # involves correspondence is expected (a cover letter and a
                # response letter also legitimately overlap — different readers),
                # but a letter repeating itself is plain redundancy, and a letter
                # that pads is a defect in its own right.
                if ki != kj and (corr_by_key.get(ki, False)
                                 or corr_by_key.get(kj, False)):
                    suppressed.append({
                        "kind": "duplicate_sentence", "sections": sorted({ti, tj}),
                        "why": ("correspondence restating the manuscript is expected "
                                "— 'say it once' applies to the manuscript body"),
                    })
                    continue
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
        if key in _METHODS_KEYS and _result_cue(sent):
            if _analysis_plan(sent):
                # Recorded, not dropped: the exemption stays auditable, and an
                # unfixable warning must not sit in the bucket that gates
                # `clean` — a gate that can never close teaches everyone to
                # wave the list through, which costs more than the noise.
                suppressed.append({
                    "kind": "results_in_methods", "section": title,
                    "sentence": sent[:180],
                    "why": ("states the statistical test and its significance "
                            "level — an analysis plan belongs in Methods"),
                })
            else:
                leakage.append({
                    "kind": "results_in_methods", "section": title,
                    "sentence": sent[:220],
                    "note": ("a finding/statistic in Methods — Methods states what "
                             "you DID (past tense, procedures); move results to "
                             "Results"),
                })
        elif key in _METHODS_KEYS and (mm := _measured_magnitude(sent)):
            leakage.append({
                "kind": "measurement_in_methods", "section": title,
                "match": mm.group(0)[:80], "sentence": sent[:220],
                "note": ("a MEASURED magnitude in Methods (size/time/memory/fold) — "
                         "Methods describes the benchmark, Results reports what it "
                         "measured; move the number and cite the table"),
            })
        elif key in _RESULTS_KEYS and _METHOD_CUES.search(sent):
            leakage.append({
                "kind": "methods_in_results", "section": title, "sentence": sent[:220],
                "note": ("procedure detail in Results — Results states what you "
                         "FOUND; move the how-to to Methods"),
            })

    # ── 2b. a number that lives in Methods and in a display item, but not in
    #        Results. No NLP: if the value is important enough to tabulate and it
    #        is stated in Methods while Results never mentions it, the result is
    #        simply in the wrong section. This is what actually happened —
    #        52.1 ± 8.5 s and 88 minutes sat in Methods and in Table 2, with zero
    #        occurrences in Results, and the benchmark answered a reviewer's major
    #        point. ────────────────────────────────────────────────────────────
    methods_text = " ".join(s for k, _t, s, _x in sents if k in _METHODS_KEYS)
    results_text = " ".join(s for k, _t, s, _x in sents if k in _RESULTS_KEYS)
    if methods_text and results_text:
        display_text_parts: list[str] = []
        try:
            for fig in _list_figures(state, slug, supplementary=None):
                display_text_parts += [str(fig.get("caption") or ""),
                                       str(fig.get("legend") or "")]
            for tbl in _list_tables(state, slug, supplementary=None):
                display_text_parts += [str(tbl.get("caption") or ""),
                                       str(tbl.get("legend") or ""),
                                       str(tbl.get("content") or "")]
        except Exception:      # display items are optional context, never fatal
            display_text_parts = []
        display_nums = _numbers(" ".join(display_text_parts))
        methods_sents = [s_ for k_, _t, s_, _x in sents if k_ in _METHODS_KEYS]
        every_num, name_bound = _partition_numbers(methods_sents)
        orphaned = sorted((every_num & display_nums) - _numbers(results_text))
        real: list[str] = []
        for num in orphaned:
            why = None
            if num in _ALPHA_LEVELS:
                why = ("a conventional significance threshold, not a measured "
                       "value — stating it is what Methods is for")
            elif num in name_bound:
                why = ("part of an instrument/product name, not a measurement — "
                       "it cannot appear in Results")
            if why:
                suppressed.append({"kind": "result_only_in_methods",
                                   "value": num, "why": why})
            else:
                real.append(num)
        for num in real[:10]:
            leakage.append({
                "kind": "result_only_in_methods", "value": num,
                "note": (f"{num} appears in Methods and in a figure/table, but "
                         f"never in Results — a measured value important enough to "
                         f"tabulate belongs in Results; Methods should describe how "
                         f"it was obtained"),
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
        m = _VAGUE_COMPARATIVE.search(sent)
        if m and _is_vague_comparative(sent, m):
            style.append({"kind": "vague_comparative", "section": title,
                          "match": m.group(0),
                          "note": "ambiguous comparative — state exactly what varies "
                                  "(more isoforms? longer CDS? higher score?)",
                          "sentence": sent[:180]})
        for m in _DISPLAY_REF.finditer(sent):
            if not _outside_parentheses(sent, m.start()):
                continue
            # Parenthetical citation is a MANUSCRIPT convention: there a display
            # item is evidence for a claim. In a letter reporting what changed the
            # figures ARE the subject ("The submitted Figure 5 becomes the new
            # Figure 4"), and rewriting those sentences would destroy the
            # paragraph. 17 such findings landed on one real response letter.
            if corr_by_key.get(key, False):
                suppressed.append({
                    "kind": "prose_cross_reference", "section": title,
                    "match": m.group(0),
                    "why": ("correspondence may make a display item the subject — "
                            "parenthetical citation is a manuscript convention"),
                })
                continue
            style.append({
                "kind": "prose_cross_reference", "section": title,
                "match": m.group(0), "sentence": sent[:180],
                "note": ("cite a display item parenthetically — "
                         f"'… ({m.group(0)})', not woven into the sentence as a "
                         "noun phrase ('The resulting projection is "
                         f"{m.group(0)}')"),
            })
        # Estimator voice: correct in Methods (the estimator IS the subject there),
        # a readability failure anywhere else.
        if key not in _METHODS_KEYS:
            for rx, why in _ESTIMATOR_VOICE:
                m = rx.search(sent)
                if m:
                    style.append({"kind": "estimator_voice", "section": title,
                                  "match": m.group(0), "note": why,
                                  "sentence": sent[:180]})
        # Shipped WITH estimator_voice on purpose: fixing one by hand overshoots
        # into the other, and both were rejected in the same session.
        for rx, why in _COLLOQUIAL:
            m = rx.search(sent)
            if m:
                style.append({"kind": "colloquial_register", "section": title,
                              "match": m.group(0), "note": why,
                              "sentence": sent[:180]})
        if corr_by_key.get(key, False) and (m := _unattributed_reviewer_ref(sent)):
            style.append({
                "kind": "unattributed_reviewer_reference", "section": title,
                "match": m.group(0), "sentence": sent[:180],
                "note": (f"'{m.group(0)}' with nobody's name on it — this letter's own "
                         f"sections are numbered the same way, so write \"the "
                         f"reviewer's {m.group(0)}\" / \"Reviewer 1's "
                         f"{m.group(0)}\""),
            })
        for m in _EM_DASH.finditer(sent):
            style.append({"kind": "em_dash", "section": title, "match": m.group(0),
                          "note": "em-dash reads as informal to many reviewers — "
                                  "a single dash → comma (or colon if it introduces "
                                  "a list/definition); a paired aside → parentheses",
                          "sentence": sent[:180]})

    # Overused rhetorical words across the whole manuscript (count once).
    from collections import Counter
    word_counts: Counter = Counter()
    for _k, _t, sent, _toks in sents:
        for w in re.findall(r"[a-z]+", sent.lower()):
            if w in _RHETORICAL:
                word_counts[w] += 1
    for word, cnt in word_counts.items():
        if cnt >= _RHETORICAL_MAX:
            style.append({"kind": "overused_word", "word": word, "count": cnt,
                          "note": f"'{word}' used {cnt}x — vary or cut repeated "
                                  "rhetorical words"})

    # ── 4. insider context — prose framed from inside the authoring session ───
    insider: list[dict] = []
    for _key, title, sent, _t in sents:
        for rx, why in _INSIDER_CONTEXT:
            m = rx.search(sent)
            if m:
                insider.append({
                    "kind": "insider_context", "section": title,
                    "match": m.group(0), "note": why, "sentence": sent[:180],
                })

    duplication = duplication[:_MAX_PER_KIND]
    leakage = leakage[:_MAX_PER_KIND]
    style = style[:_MAX_PER_KIND]
    insider = insider[:_MAX_PER_KIND]
    unresolved = unresolved[:_MAX_PER_KIND]
    total = (len(duplication) + len(leakage) + len(style) + len(insider)
             + len(unresolved))
    return {
        "slug": slug,
        "duplication": duplication,
        "section_leakage": leakage,
        "style": style,
        # Reader-frame problems, reported separately from `style` because they are
        # judgement calls the author must make: not every hit is guilty ("we
        # withdraw the original explanation" is fine — the reviewer read the
        # original). Advisory, never a gate.
        "insider_context": insider,
        # Counts toward `total`, unlike insider_context: this is not a judgement
        # call. A token no resolver handles is a reference that will be missing
        # from the finished document, and export is where that becomes permanent.
        "unresolved_tokens": unresolved,
        # Findings a document-kind profile deliberately withheld. Surfaced rather
        # than dropped: a silent exemption makes the lint unauditable, and this
        # list is exactly what you would want to see if a profile were wrong.
        "suppressed_by_profile": suppressed[:_MAX_PER_KIND],
        # Captions and legends, from lint_legends. Included because this tool's
        # `clean` is the gate skills re-run until it goes true, and it used to
        # cover section text ONLY — so a manuscript whose figure legends restated
        # whole paragraphs of the synthesis reported "clean: 0 warnings"
        # (feedback 81d4a52c0212). Duplication does not stop being duplication
        # because it is under a figure, and a gate that cannot see half the prose
        # is the quiet failure this codebase keeps meeting. Summary only; the
        # per-sentence detail stays in lint_legends(slug).
        "display_items": display_items,
        "summary": {
            "total": total,
            "by_kind": {
                "duplication": len(duplication),
                "section_leakage": len(leakage),
                "style": len(style),
                "insider_context": len(insider),
                "unresolved_tokens": len(unresolved),
            },
            "suppressed_by_profile": len(suppressed),
            "display_items": display_items["total"],
            # Body only — kept so "is the prose clean?" is still answerable.
            "body_clean": total == 0,
            "clean": total == 0 and display_items["total"] == 0,
        },
    }

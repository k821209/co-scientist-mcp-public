"""A number in a sentence that cites a table or a figure is IN that item.

The author's rule, stated 2026-11-14: "본문을 작성할 때 수치를 쓸 거면 해당 표에
혹은 주어진 그래프에 수치가 있어야 된다. 독자가 알아서 계산하도록 하면 안
된다." A sentence says "1.6-fold higher (Table 2)" and Table 2 holds the two
values the fold was worked out from; or "a 23% gain" beside a table of raw
yields. The reader who goes to the table to check the sentence finds no such
number and has to do the arithmetic — and cannot tell a correct derivation
from a typo.

The table half of that is mechanical: parse the cited table's cells, its
caption and its legend, find the numbers in the citing sentence, look each
up. The figure half is not — a value printed on a bar is pixels to this code —
so a number that cites only a figure is LISTED, never judged: the list is the
thing to check against the plot, and it is kept out of the pass/fail count.

What is deliberately not a "number" here: a p- or q-value and its threshold
(tables rarely carry them and nobody computes one from a table), a confidence
level, a year, a single digit that is not a fold or a percent, digits inside
an identifier, and the display item's own number.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

# {tab:N} / {fig:N}; 101 and up are supplementary items.
_TOKEN = re.compile(r"\{(tab|fig):(\d+)\}")
# "Table 2", "Fig. 3A", "Figure 3", "Supplementary Table 1", "Table S1",
# "표 2", "그림 3", "보충 표 1".
_PROSE = re.compile(
    r"(?P<supp>Supplementa(?:ry|l)\s+|Supp\.?\s+|보충\s*)?"
    r"(?P<kind>Tables?|Fig(?:ures?|s?\.)?|표|그림)\s*"
    r"(?P<s>S)?(?P<n>\d{1,3})(?![\d.]\d)",
    re.I)
_BRACE = re.compile(r"\{[^{}\n]{1,160}\}")
_MATH = re.compile(r"\$\$.*?\$\$|\$[^$\n]{1,200}\$", re.S)
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+(?=[A-Z0-9(\"'가-힣])|\n+")

# A numeric literal, not glued to a word on its left ("chr01", "Glyma.01G",
# "v2.1"): the left side must not be a letter, a digit, an underscore or a dot.
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_CELL_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
# What makes a single digit worth checking: it is a fold or a percentage.
_FOLD_AFTER = re.compile(r"\s?(?:-?\s?fold\b(?!\s*(?:CV|cross))|×|x\b|배|\s?times\b)", re.I)
# Lines that are not prose about a result: a heading, or a caption written
# into the body ("**Table 1.** …").
_NOT_PROSE_LINE = re.compile(r"^\s*(?:#{1,6}\s|\*\*(?:Table|Figure|Fig\.|표|그림)\s*S?\d)", re.I)
# "§1.6", "Section 3.2", "3장": a place in the document, not a quantity.
_SECTION_BEFORE = re.compile(r"(?:§|Sections?\s|Sec\.\s|Chapter\s|Step\s|Stage\s)$", re.I)
_SECTION_AFTER = re.compile(r"\s?(?:장|절|항)\b")
_PERCENT_AFTER = re.compile(r"\s?(?:%|percent\b|퍼센트|pp\b)", re.I)
# p / q values and thresholds: "p < 0.05", "(P = 0.003)", "FDR < 0.01", "q≤0.1".
_STAT_BEFORE = re.compile(r"(?:\b[pPqQ]|FDR|α|alpha|padj|p-?adj|p-?value)\s*[<>=≤≥]\s*$", re.I)
# "95% CI", "95 % confidence", "95% 신뢰".
_CONFIDENCE_AFTER = re.compile(r"\s?%\s*(?:CI\b|confidence|credible|신뢰)", re.I)
_SEP_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

_MAX_LISTED = 60


# A typeset minus is the same sign as a typed one; a table printing −37.99 and
# a sentence quoting -37.99 agree.
_MINUS = str.maketrans({"\u2212": "-", "\u2013": "-"})

# Words that say a percentage is a CHANGE and not a level: "23% higher" is a
# number somebody worked out, "23% of reads" may be a cell.
# The change word has to sit ON the percentage — "23% higher", "rose by 23%",
# "23% 증가". Anywhere-in-the-sentence was tried first: "94.4% of all genes
# show higher diversity" is a share, and it was flagged as a change.
_CHANGE_AFTER = re.compile(
    r"\s?(?:%|percent)\s*(?:points?\s+)?(?:higher|lower|more|less|fewer|greater|smaller|"
    r"faster|slower|increase|decrease|gain|drop|reduction|improvement|decline|"
    r"증가|감소|향상|하락|개선|높|낮|많|적)", re.I)
_CHANGE_BEFORE = re.compile(
    r"(?:increas\w*|decreas\w*|rose|fell|dropp\w*|improv\w*|reduc\w*|grew|declin\w*|"
    r"gain\w*)\s+(?:by|of)\s+(?:about\s+|around\s+|~)?$", re.I)


def _significant(raw: str) -> int:
    return len(raw.lstrip("-").replace(",", "").replace(".", "").lstrip("0"))


def _dec(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _places(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def item_numbers(*texts: str | None) -> list[Decimal]:
    """Every number printed in a display item's text — table cells, caption,
    legend, title. The separator row of a pipe table is not data."""
    out: list[Decimal] = []
    for text in texts:
        for line in (text or "").splitlines():
            if _SEP_ROW.match(line):
                continue
            for m in _CELL_NUMBER.finditer(line.translate(_MINUS)):
                value = _dec(m.group(0))
                if value is not None:
                    out.append(value)
    return out


def _printed(value: Decimal, places: int, percent: bool, pool: list[Decimal]) -> bool:
    """Is this number in the item — as printed, or as the item's own value
    rounded to the precision the sentence uses? A percentage may be printed as
    its fraction (44.9% beside 0.449): that is a notation, not a calculation
    left to the reader. Nothing else is equivalent — a ratio of two cells, a
    difference, a sum are exactly what this exists to find."""
    quantum = Decimal(1).scaleb(-places)
    for have in pool:
        for shown in ((have, have * 100) if percent else (have,)):
            if shown == value:
                return True
            for rounding in (ROUND_HALF_UP, ROUND_HALF_EVEN):
                try:
                    if shown.quantize(quantum, rounding=rounding) == value:
                        return True
                except InvalidOperation:
                    break
    return False


def table_grid(content: str | None) -> list[list[Decimal | None]]:
    """A pipe table as rows of numbers: the first number in each cell, None
    for a cell without one. The header and the rule line are dropped."""
    rows: list[list[Decimal | None]] = []
    seen_rule = False
    for line in (content or "").splitlines():
        if "|" not in line:
            continue
        if _SEP_ROW.match(line):
            seen_rule = True
            rows = []                       # what came before the rule is the header
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        row: list[Decimal | None] = []
        for cell in cells:
            m = _CELL_NUMBER.search(cell.translate(_MINUS))
            row.append(_dec(m.group(0)) if m else None)
        rows.append(row)
    return rows if seen_rule else []


def _same(value: Decimal, places: int, got: Decimal) -> bool:
    quantum = Decimal(1).scaleb(-places)
    for rounding in (ROUND_HALF_UP, ROUND_HALF_EVEN):
        try:
            if got.quantize(quantum, rounding=rounding) == value:
                return True
        except InvalidOperation:
            return False
    return False


def derivation(value: Decimal, places: int, percent: bool,
               grid: list[list[Decimal | None]]) -> str | None:
    """How this number can be WORKED OUT from the table, when it can: a
    column's sum, mean, median or range, the count of rows, or a ratio,
    difference or percent change of two cells in one row or one column.

    That is the proof the rule needs. "Not in the table" has innocent
    explanations — a parameter, a count from elsewhere, the wrong item cited;
    "equal to row 3 over row 1 of column 2" has one: the reader was left to
    do it. A whole number is matched only against sums, counts and
    differences of three digits or more, because small integers coincide.
    """
    if not grid:
        return None
    whole = places == 0
    big = abs(value) >= 100
    width = max(len(r) for r in grid)
    lines: list[tuple[str, list[Decimal]]] = []
    for c in range(width):
        col = [r[c] for r in grid if c < len(r) and r[c] is not None]
        if len(col) >= 2:
            lines.append((f"column {c + 1}", col))
    columns = len(lines)
    for i, r in enumerate(grid):
        row = [v for v in r if v is not None]
        if len(row) >= 2:
            lines.append((f"row {i + 1}", row))
    for index, (where, vals) in enumerate(lines):
        n = len(vals)
        ordered = sorted(vals)
        # A column is one quantity down the rows, so its total or its median
        # means something; a row usually mixes quantities, and its "sum" was
        # a coincidence every time it matched.
        if index < columns and n >= 3:
            stats = {"sum": sum(vals), "range (max − min)": ordered[-1] - ordered[0]}
            if not whole:
                stats["mean"] = sum(vals) / n
                stats["median"] = (ordered[n // 2] if n % 2
                                   else (ordered[n // 2 - 1] + ordered[n // 2]) / 2)
            for name, got in stats.items():
                if (not whole or big) and _same(value, places, got) and got not in vals:
                    return f"the {name} of {where}"
        if n > 40:
            continue                        # pairs are for tables a reader could work through
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                a, b = vals[i], vals[j]
                if a == 0 or b == 0:
                    continue                # x − 0 is x, which is printed
                pairs = [("the difference", a - b)] if (not whole or big) else []
                if b != 0 and not whole:
                    pairs.append(("the ratio", a / b))
                    pairs.append(("the percent change", (a - b) / b * 100))
                    pairs.append(("the percentage", a / b * 100))
                for name, got in pairs:
                    if got <= 0:
                        continue
                    if name in ("the percent change", "the percentage") and not percent:
                        continue
                    if name == "the ratio" and percent:
                        continue
                    if _same(value, places, got):
                        return f"{name} of two cells in {where} ({a} and {b})"
    return None


def _refs(sentence: str) -> tuple[set[int], set[int], str]:
    """(table numbers, figure numbers, the sentence with every reference and
    every non-prose span blanked out)."""
    tables: set[int] = set()
    figures: set[int] = set()

    def token(m: re.Match) -> str:
        (tables if m.group(1) == "tab" else figures).add(int(m.group(2)))
        return " "

    text = _CODE.sub(" ", sentence)
    text = _MATH.sub(" ", text)
    text = _TOKEN.sub(token, text)
    text = _BRACE.sub(" ", text)
    text = _LINK.sub(lambda m: m.group(1), text)

    def prose(m: re.Match) -> str:
        n = int(m.group("n")) + (100 if (m.group("supp") or m.group("s")) else 0)
        kind = m.group("kind").lower()
        (tables if kind.startswith("table") or kind == "표" else figures).add(n)
        return " "

    text = _PROSE.sub(prose, text)
    return tables, figures, text


def sentence_numbers(text: str) -> list[dict]:
    """The numbers in a (reference-stripped) sentence that a reader would look
    for in the cited item: {raw, value, places, percent, fold}."""
    out: list[dict] = []
    text = text.translate(_MINUS)
    for m in _NUMBER.finditer(text):
        raw = m.group(0)
        value = _dec(raw)
        if value is None:
            continue
        after = text[m.end(): m.end() + 14]
        before = text[max(0, m.start() - 14): m.start()]
        if _STAT_BEFORE.search(before) or _CONFIDENCE_AFTER.match(after):
            continue
        if _SECTION_BEFORE.search(before) or _SECTION_AFTER.match(after):
            continue
        fold = bool(_FOLD_AFTER.match(after))
        percent = bool(_PERCENT_AFTER.match(after))
        change = percent and bool(
            _CHANGE_AFTER.match(text[m.end(): m.end() + 30])
            or _CHANGE_BEFORE.search(text[max(0, m.start() - 30): m.start()]))
        digits = raw.lstrip("-").replace(",", "")
        if "." not in digits and len(digits) == 1 and not (fold or percent):
            continue                       # a bare single digit carries no signal
        if "." not in digits and len(digits) == 4 and 1900 <= int(digits) <= 2099 \
                and not (fold or percent):
            continue                       # a year
        out.append({"raw": raw + ("%" if percent else "") + ("-fold" if fold else ""),
                    "value": value, "places": _places(raw), "percent": percent, "fold": fold,
                    "digits": raw, "change": change})
    return out


def cited_number_findings(sections: list[dict], tables: list[dict], figures: list[dict],
                          *, skip_sections: tuple[str, ...] = ("methods",)) -> dict:
    """Check every number in a sentence that cites a display item against that item.

    `sections`: [{key, title, body}]; `tables`: [{table_number, title, caption,
    legend, content}]; `figures`: [{figure_number, title, caption, legend}].

    Returns `not_in_table` (the sentence cites tables only and the number is in
    none of them — the reader would have to compute it or look elsewhere),
    `check_on_figure` (it cites a figure, and the number is not in any cited
    table, caption or legend: it may be printed on the plot, which this cannot
    see), `unknown_items` (a cited number with no such table or figure
    registered), and `examined` — how many sentences carried a citation and
    how many numbers were looked up, so an empty list can be told from a
    manuscript that cites nothing.
    """
    grids = {int(t.get("table_number")): table_grid(t.get("content"))
             for t in tables if t.get("table_number") is not None}
    derived: list[dict] = []
    table_pool = {int(t.get("table_number")): item_numbers(
        t.get("content"), t.get("caption"), t.get("legend"), t.get("title"))
        for t in tables if t.get("table_number") is not None}
    figure_pool = {int(f.get("figure_number")): item_numbers(
        f.get("caption"), f.get("legend"), f.get("title"))
        for f in figures if f.get("figure_number") is not None}

    not_in_table: list[dict] = []
    check_on_figure: list[dict] = []
    unknown: set[str] = set()
    sentences_examined = numbers_examined = 0
    for sec in sections:
        key = (sec.get("key") or "").lower()
        if key in skip_sections:
            continue
        title = sec.get("title") or key
        body = "\n".join(line for line in (sec.get("body") or "").splitlines()
                         if not _NOT_PROSE_LINE.match(line))
        for sent in _SENTENCE_END.split(body):
            sent = sent.strip()
            if not sent:
                continue
            cited_tables, cited_figures, stripped = _refs(sent)
            if not cited_tables and not cited_figures:
                continue
            for n in sorted(cited_tables - set(table_pool)):
                unknown.add(f"table {n}")
            for n in sorted(cited_figures - set(figure_pool)):
                unknown.add(f"figure {n}")
            pool: list[Decimal] = []
            for n in cited_tables:
                pool += table_pool.get(n, [])
            for n in cited_figures:
                pool += figure_pool.get(n, [])
            numbers = sentence_numbers(stripped)
            if not numbers:
                continue
            sentences_examined += 1
            for num in numbers:
                numbers_examined += 1
                if _printed(num["value"], num["places"], num["percent"], pool):
                    continue
                row = {"section": title, "value": num["raw"], "sentence": sent[:300],
                       "tables": sorted(cited_tables), "figures": sorted(cited_figures)}
                how = next((d for d in (derivation(num["value"], num["places"], num["percent"],
                                                   grids.get(n) or []) for n in sorted(cited_tables))
                            if d), None)
                # Two cells of a long column differ by almost any two-digit
                # number, so a derivation is believed at three significant
                # digits, or when the sentence itself says fold or percent.
                believed = how and (num["fold"] or num["percent"]
                                    or _significant(num["digits"]) >= 3)
                if not believed and not cited_figures and (num["fold"] or num["change"]):
                    # No arithmetic needed to know this one was worked out: a
                    # fold, or a percent change, is a derived number by what
                    # it is — and the cited table does not print it.
                    how = ("a fold change" if num["fold"] else "a percent change")
                    how += " that the cited table does not print"
                    believed = True
                if believed:
                    row["derivation"] = how
                    row["note"] = (f"this is {how} — the reader is left to work it out. Give it "
                                   "a cell of its own, generated with the table, and quote that")
                    derived.append(row)
                elif cited_figures:
                    row["note"] = ("not in the caption, the legend or a cited table — check "
                                   "that it is printed on the figure itself; if the reader "
                                   "would have to read it off an axis or work it out, label "
                                   "it on the plot or give it in a table")
                    check_on_figure.append(row)
                else:
                    row["note"] = (
                        ("a fold or ratio the table does not print" if num["fold"] else
                         "not a cell of the cited table, nor in its caption or legend")
                        + " — the reader would have to calculate it or look elsewhere. Add the "
                          "column (generated with the table, not typed), or quote the cell")
                    not_in_table.append(row)
    return {
        "derived_not_printed": derived[:_MAX_LISTED],
        "not_in_table": not_in_table[:_MAX_LISTED],
        "check_on_figure": check_on_figure[:_MAX_LISTED],
        "unknown_items": sorted(unknown),
        "examined": {"sentences_citing_an_item": sentences_examined,
                     "numbers": numbers_examined,
                     "tables_read": len(table_pool), "figures_read": len(figure_pool)},
        "total": len(derived),
        "listed_of": {"derived_not_printed": len(derived),
                      "not_in_table": len(not_in_table),
                      "check_on_figure": len(check_on_figure)},
    }

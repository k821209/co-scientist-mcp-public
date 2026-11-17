"""Which `$` in a body open and close math, and which are dollar signs.

Two renderers read a manuscript's `$`, and they did not agree. The export is
pandoc, whose rule is strict: the opening `$` has a non-space character right
after it, the closing `$` has a non-space character right before it and no
digit right after, and no `$` in between follows whitespace. The dashboard
was remark-math, whose rule is none: any two `$` in a paragraph are a formula.

    … 월 US$ 2,400의 연구활동비를 지급한다.** 안내문은 이를 환율 1,340원/US$로
    환산해 월 3,216,000원으로 적고 있다. 6개월이면 US$ 14,400, …

The dashboard made a formula of the first sign to the second — italic, spaces
gone, the paragraph's `**` printed as asterisks. Pandoc makes one of the
second to the third ("$로 환산해 … 6개월이면 US$"), so the exported file was
wrong too, somewhere else. Nothing said so in either place, and the guide
named a `math_warnings` that no code had ever produced (feedback
946a651fe771).

This module is pandoc's rule, written out once. The dashboard holds the same
rule in apps/web/src/lib/dollarMath.ts, so the page the author reads shows
what the file will print; and both are tested against
tests/data/dollar_math_cases.json — the answers of a real pandoc (3.9) on
each case, not of either implementation.

The rule, from Text.Pandoc.Parsing.Math and confirmed case by case:

* `$` opens inline math when the next character is not whitespace or `$`.
* From there the first `$` closes it. Before that `$` there may be single
  line breaks and runs of spaces, but not a blank line, and never whitespace
  directly before a `$`; a backslash takes the next character with it.
* If the closing `$` is followed by a digit, there is no formula at all, and
  the opening `$` is a dollar sign ("$20,000 and $30,000").
* `$$ … $$` is display math, within one paragraph.

So "US$ 2,400" alone is a dollar sign, and "US$로" is an opening one as soon
as any later `$` in the paragraph can close it. What the rule reads as math
and is a sentence is `looks_like_prose`, and the lint reports it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SPACE = " \t\n\r"
_DIGITS = "0123456789"
_FILL = "\x01"          # stands in for code: not a space, not a digit, not a `$`

_FENCE_OPEN = re.compile(r"(`{3,}|~{3,})")


@dataclass(frozen=True)
class Span:
    start: int          # index of the opening `$`
    end: int            # index one past the closing `$`
    content: str        # what is between them, trimmed
    display: bool = False


def _mask(text: str) -> str:
    """`text` with code replaced, character for character, by a filler.

    Written as two plain scans rather than two regexes because the dashboard
    runs the same two scans in another language (dollarMath.ts), and a regex
    with a lookbehind is not something every browser it meets can parse."""
    chars = list(text)

    def blank(start: int, end: int) -> None:
        for at in range(start, end):
            if chars[at] != "\n":
                chars[at] = _FILL

    # Fenced blocks: a line that starts with ``` or ~~~, to the next line that
    # is that same marker and nothing else.
    at, marker, opened = 0, "", -1
    while at <= len(text):
        stop = text.find("\n", at)
        stop = len(text) if stop < 0 else stop
        line = text[at:stop]
        if opened < 0:
            found = _FENCE_OPEN.match(line)
            if found:
                marker, opened = found.group(1), at
        elif line.startswith(marker) and not line[len(marker):].strip("`~ \t"):
            blank(opened, stop)
            opened = -1
        at = stop + 1

    # Code spans: a run of backticks, to the next run of the same length.
    at, n = 0, len(chars)
    while at < n:
        if chars[at] != "`":
            at += 1
            continue
        run = at
        while run < n and chars[run] == "`":
            run += 1
        seek, close = run, -1
        while seek < n:
            if chars[seek] != "`":
                seek += 1
                continue
            end = seek
            while end < n and chars[end] == "`":
                end += 1
            if end - seek == run - at:
                close = end
                break
            seek = end
        if close < 0:
            at = run
        else:
            blank(at, close)
            at = close
    return "".join(chars)


def _close_inline(text: str, opener: int) -> int | None:
    """Index of the `$` that closes the inline formula opened at `opener`."""
    n = len(text)
    j = opener + 1
    if j >= n or text[j] in _SPACE or text[j] == "$":
        return None
    while j < n:
        ch = text[j]
        if ch == "$":
            return None if j + 1 < n and text[j + 1] in _DIGITS else j
        if ch == "\\":
            j += 2
            continue
        if ch in _SPACE:
            k = j
            while k < n and text[k] in _SPACE:
                k += 1
            if text.count("\n", j, k) > 1 or k >= n or text[k] == "$":
                return None
            j = k
            continue
        j += 1
    return None


def _close_display(text: str, after: int) -> int | None:
    """Index of the `$$` that closes display math whose content starts at `after`."""
    close = text.find("$$", after)
    if close <= after:
        return None
    return None if re.search(r"\n[ \t]*\n", text[after:close]) else close


def scan(body: str) -> tuple[list[Span], list[int]]:
    """(formulas, positions of every `$` that is a dollar sign), in order."""
    text = _mask(body or "")
    spans: list[Span] = []
    literal: list[int] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch != "$":
            i += 1
            continue
        if text.startswith("$$", i):
            close = _close_display(text, i + 2)
            if close is not None:
                spans.append(Span(i, close + 2, body[i + 2:close].strip(), display=True))
                i = close + 2
                continue
        close = _close_inline(text, i)
        if close is None:
            literal.append(i)
            i += 1
        else:
            spans.append(Span(i, close + 1, body[i + 1:close].strip()))
            i = close + 1
    return spans, literal


def spans(body: str) -> list[Span]:
    return scan(body)[0]


def strip(body: str, fill: str = " ") -> str:
    """`body` with every formula replaced by `fill` — and nothing else: the
    prose between two dollar signs stays, to be read like any other prose."""
    out, last = [], 0
    for span in spans(body):
        out += [body[last:span.start], fill]
        last = span.end
    return "".join(out) + (body or "")[last:]


_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_TEXT_COMMAND = re.compile(r"\\(?:text|textrm|textbf|textit|mathrm|mbox|operatorname)\s*\{[^{}]*\}")
_WORD = re.compile(r"[A-Za-z]{2,}")


def looks_like_prose(content: str) -> str | None:
    """Why this formula is probably a sentence caught between two dollar
    signs — or None when nothing says so.

    Two signs, both of something a formula does not contain: Korean outside a
    `\\text{}`, or three or more plain words with no TeX command anywhere.
    Measured on the 360 inline formulas in the account's 205 documents before
    choosing (2026-11-17): neither sign fires on any of them."""
    bare = _TEXT_COMMAND.sub(" ", content or "")
    if _HANGUL.search(bare):
        return "Korean text"
    if "\\" not in bare and len(_WORD.findall(bare)) >= 3:
        return "words and no formula"
    return None

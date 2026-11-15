"""What a rendered document calls its tables and figures.

Every caption an export writes used to begin "Table N." / "Figure N.",
whatever the document was written in. A Korean commissioned report whose body
says "표 4는 유전자당 1개 기준이다" came out with "Table 4." over the table on
the same page, and the find-and-replace that fixed it had to be done again
after every export (feedback 2712865bc0f7).

The rule is the one `_display_label` already states for supplementary items:
the label is spelled the way the BODY spells it.

1. If the body refers to its tables by number, the word it uses wins —
   "표 3" against "Table 3", counted. Table and figure are decided
   separately, because a body can say "표 1" and "Fig. 2".
2. If it never does, or the two are tied, the body's language decides: Korean
   when at least half its words contain Hangul.

Measured on the account's 187 documents before choosing (2026-11-15): the
share of words containing Hangul is bimodal — 82 documents under 0.1, 103 at
0.5 or above, two between (0.19 and 0.36, both without a single numbered
reference). Language alone would have been wrong for the Korean documents
that write "Table 3" / "Figure 2" in Korean prose, which is ordinary in
Korean scientific writing — one does it 41 times. As shipped, 88 of the 103
get 표 and 그림, and 15 keep an English word for tables, figures or both (4
both, 4 tables only, 7 figures only), which is the label they have today.
The 84 others are unchanged.

Not judged: a document in a language other than Korean or English gets the
English words, as before.

The dashboard shows `{tab:N}` with the same words, from its own copy of this
rule (apps/web/src/lib/labelWords.ts). Two copies in two languages are held
together by one file of cases, tests/data/label_words_cases.json, which both
test suites run: change the rule here and a case there fails on the other side.
"""
from __future__ import annotations

import contextlib
import contextvars
import re
from dataclasses import dataclass

# Half the words. Not tuned to a case: nothing measured sits between 0.36 and 0.56.
KOREAN_SHARE = 0.5

_FENCE = re.compile(r"```.*?```", re.S)
_NOISE = re.compile(r"https?://\S+|\{[a-z]+:[^}]*\}|<[^>]+>|!\[[^\]]*\]\([^)]*\)")
_HANGUL = re.compile(r"[가-힣]")
_WORD = re.compile(r"[A-Za-z가-힣][A-Za-z가-힣\-']*")

# "표 4", "표4", "<표 4>" — and not the tail of 발표 / 목표 / 대표 / 좌표.
_KO_TABLE = re.compile(r"(?<![가-힣])표\s?\d")
_KO_FIGURE = re.compile(r"(?<![가-힣])그림\s?\d")
_EN_TABLE = re.compile(r"\bTables?\s?\d")
_EN_FIGURE = re.compile(r"\bFig(?:ure|s|ures)?\.?\s?\d")


@dataclass(frozen=True)
class Words:
    table: str = "Table"
    figure: str = "Figure"
    # Headings follow the document's language, not the label count: a Korean
    # report that writes "Table 3" in its prose still has a Korean heading
    # above its reference list.
    korean_headings: bool = False
    why: str = "default"

    def of(self, kind: str) -> str:
        return self.figure if kind == "Figure" else self.table

    def label(self, kind: str, number, *, supplementary: bool, offset: int) -> str:
        """`STable 5`, `표 4`, `보충 표 5` — the caption's label."""
        word = self.of(kind)
        if supplementary and isinstance(number, int):
            if word == kind:
                return f"S{kind} {number - offset}"
            return f"보충 {word} {number - offset}"
        return f"{word} {number}"

    def reference(self, kind: str, number: int, *, supplementary: bool, offset: int) -> str:
        """What a `{tab:N}` token reads as in prose."""
        word = self.of(kind)
        if supplementary:
            prefix = "Supplementary " if word == kind else "보충 "
            return f"{prefix}{word} {number - offset}"
        return f"{word} {number}"

    def heading(self, english: str) -> str:
        return _KOREAN_HEADINGS.get(english, english) if self.korean_headings else english

    def report(self) -> dict:
        return {"table": self.table, "figure": self.figure, "why": self.why}


_KOREAN_HEADINGS = {
    "Tables": "표",
    "Figures": "그림",
    "Supplementary Tables": "보충 표",
    "Supplementary Figures": "보충 그림",
    "Supplementary Material": "보충 자료",
    "References": "참고문헌",
}

ENGLISH = Words()


def hangul_share(body: str) -> float | None:
    """The share of the body's words that contain Hangul; None with no words."""
    words = _WORD.findall(_NOISE.sub(" ", _FENCE.sub(" ", body or "")))
    if not words:
        return None
    return sum(1 for word in words if _HANGUL.search(word)) / len(words)


def choose(body: str) -> Words:
    """The words for a document with this body. See the module docstring."""
    text = _NOISE.sub(" ", _FENCE.sub(" ", body or ""))
    share = hangul_share(body)
    korean = share is not None and share >= KOREAN_SHARE
    said = []

    def pick(kind: str, ko_word: str, ko_re: re.Pattern, en_re: re.Pattern) -> str:
        ko, en = len(ko_re.findall(text)), len(en_re.findall(text))
        if ko != en:
            winner = ko_word if ko > en else kind
            said.append(f"{winner}: the body writes \"{ko_word} N\" {ko} time(s) "
                        f"and \"{kind} N\" {en}")
            return winner
        winner = ko_word if korean else kind
        said.append(f"{winner}: the body "
                    + ("names none by number" if not ko else f"uses both {ko} time(s)")
                    + ", so by its language ("
                    + ("no words" if share is None else f"{share:.0%} of words in Hangul")
                    + ")")
        return winner

    table = pick("Table", "표", _KO_TABLE, _EN_TABLE)
    figure = pick("Figure", "그림", _KO_FIGURE, _EN_FIGURE)
    return Words(table=table, figure=figure, korean_headings=korean, why="; ".join(said))


_CURRENT: contextvars.ContextVar[Words] = contextvars.ContextVar("label_words", default=ENGLISH)


def current() -> Words:
    return _CURRENT.get()


def use(words: Words) -> None:
    """Set the words for the export in progress (inside `scope`)."""
    _CURRENT.set(words)


@contextlib.contextmanager
def scope():
    """One export. Whatever `use` set inside is gone on the way out, so a
    warning or a lint written after it — in English — never picks up the
    words of the last document exported in this process."""
    token = _CURRENT.set(ENGLISH)
    try:
        yield
    finally:
        _CURRENT.reset(token)

"""Small helpers shared by tool modules."""
from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp in the format the original co-scientist uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Keep letters/digits of ANY script (Korean, CJK, accented Latin, …); collapse
# every other run — spaces, punctuation, underscores — into a single hyphen.
# `[\W_]` = "not a word char, or underscore", so `_` also becomes a separator
# (matching the original ASCII behavior). re.UNICODE keeps 한글/CJK letters.
_slug_re = re.compile(r"[\W_]+", re.UNICODE)


def slugify(text: str) -> str:
    """Lowercase kebab-case slug, Unicode-aware.

    Non-Latin titles keep their letters ("벼 유전체 2026" → "벼-유전체-2026")
    instead of being stripped to an empty string. Returns "" only when the
    input has no letters/digits at all (e.g. emoji/punctuation only) — callers
    should fall back to a generated id in that case.
    """
    return _slug_re.sub("-", text.lower()).strip("-")


def word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())


def new_id() -> str:
    """Short opaque id for things that don't have a natural key (reviews, etc)."""
    return uuid.uuid4().hex[:12]


def exact_replace(text: str, old: str, new: str, count: int | None = 1) -> tuple[str, int]:
    """Replace `old` with `new` in `text` under the host Edit tool's contract:
    `old` must be present, and — with `count` given — present exactly that
    many times; `count=None` replaces every occurrence. Absent or a
    different number → ValueError naming the number found, so a terminology
    sweep learns which substitution did not match instead of re-sending the
    whole body (feedback c1de307ee051)."""
    if not old:
        raise ValueError("old must not be empty")
    found = text.count(old)
    if found == 0:
        raise ValueError(f"old text not found: {old[:80]!r}")
    if count is not None and found != count:
        raise ValueError(
            f"old text occurs {found} time(s), expected {count}: {old[:80]!r} — "
            "give more context, or count=<n> / count=None to replace all")
    return text.replace(old, new), found


# How much text around a replacement answers "did it land where I meant?".
EDIT_CONTEXT_CHARS = 120


def replace_with_contexts(text: str, old: str, new: str, count: int | None = 1,
                          *, window: int = EDIT_CONTEXT_CHARS) -> tuple[str, int, list[str]]:
    """`exact_replace`, plus a snippet of the NEW text around each hit.

    The surgical edit tools used to answer with the whole body — the one thing
    the caller had just read. Twenty one-word copy-edits on a 3,700-word
    section echoed something like 120k tokens for a payload under 400
    characters, and the pressure that creates is to batch them into a retyped
    `update_section`, which is the transcription risk these tools exist to
    remove (feedback ab361fd69b24). A window around each replacement keeps the
    one thing the body was being read for: did this land where I meant?
    """
    out, found = exact_replace(text, old, new, count)
    contexts: list[str] = []
    pos, offset = 0, 0
    while True:
        index = text.find(old, pos)
        if index == -1:
            break
        at = index + offset                      # the same spot in `out`
        left = max(0, at - window)
        right = min(len(out), at + len(new) + window)
        contexts.append(("…" if left > 0 else "") + out[left:right]
                        + ("…" if right < len(out) else ""))
        offset += len(new) - len(old)
        pos = index + len(old)
    return out, found, contexts


# A tag that CrossRef left abutting a word, and the word that abuts a closing
# one: `genus<i>Cuscuta</i>spp.` is what the registry returns, and converting
# the markup faithfully then prints "genusCuscutaspp.".
# Only an OPENING tag gets a space in front of it: putting one before a
# closing tag would italicise a trailing space instead of fixing anything.
_TAG_AFTER_WORD = re.compile(r"(\w)(<\s*[a-zA-Z][a-zA-Z0-9]*\s*>)")
_WORD_AFTER_TAG = re.compile(r"(<\s*/\s*[a-zA-Z][a-zA-Z0-9]*\s*>)([\w(])")


def tidy_source_text(value: str | None) -> str | None:
    """Make a registry-supplied title / journal / publisher printable.

    Two defects arrive from CrossRef and both are invisible until someone
    reads the rendered bibliography (feedback 6842a3897d99):

      - entities, sometimes doubly escaped: `&lt;i&gt;Cuscuta&lt;/i&gt;`,
        `Organisms Diversity &amp; Evolution`;
      - markup with no space around it: `the parasitic plant genus<i>Cuscuta</i>`,
        which prints as one word however correctly the tag is converted.

    Unescaping is repeated because `&amp;lt;` is one pass from `&lt;` and two
    from `<`. The tags themselves are left in place — the .bib writer turns
    them into \textit{} and friends, which is where that decision belongs.
    """
    if value is None:
        return None
    s = str(value)
    for _ in range(3):
        once = html.unescape(s)
        if once == s:
            break
        s = once
    s = _TAG_AFTER_WORD.sub(r"\1 \2", s)
    s = _WORD_AFTER_TAG.sub(r"\1 \2", s)
    return re.sub(r"\s+", " ", s).strip()

"""Small helpers shared by tool modules."""
from __future__ import annotations

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

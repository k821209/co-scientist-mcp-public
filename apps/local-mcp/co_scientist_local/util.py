"""Small helpers shared by tool modules."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp in the format the original co-scientist uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase kebab-case slug. Empty input → empty string."""
    s = _slug_re.sub("-", text.lower()).strip("-")
    return s


def word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())


def new_id() -> str:
    """Short opaque id for things that don't have a natural key (reviews, etc)."""
    return uuid.uuid4().hex[:12]

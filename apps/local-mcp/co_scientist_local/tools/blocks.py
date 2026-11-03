"""A section body as blocks with stable identity.

The body stays the canonical thing: one markdown string, exactly as it is
stored and exactly as `prepare_export`, the lints, the citation numbering and
Pandoc already read it. What this adds is an ID per block, kept beside the
body, so the things that break today stop breaking:

  - a comment anchors to a BLOCK, not to a quoted phrase re-found at render
    time. Rewording the sentence it sits on currently orphans it, which is why
    `reconcile_review_anchors` exists and why the dashboard says "위치를 찾지
    못했습니다";
  - a write names the block it changes and the revision it read, so an agent
    and a person editing one section no longer silently overwrite each other —
    `update_section` replaces the whole body and the last write wins.

The split is LOSSLESS: `join_blocks(split_blocks(body)) == body`, byte for
byte, because each block keeps the separator that followed it. That is what
lets the body remain canonical — nothing downstream sees a different string.

This is a faithful port of `apps/web/src/lib/paragraphs.ts`, and the two have
to agree or an id points at the wrong text. They are not checked against each
other by construction, so they are checked against the same committed corpus:
`tests/fixtures/section_blocks.json`, read by `tests/test_blocks.py` here and
by `paragraphs.test.ts` there. Change one splitter and the other's suite fails.
"""
from __future__ import annotations

import hashlib
import re
import secrets

# A blank line, with any run of further blank lines, kept as the separator.
_SEP = re.compile(r"(\n[ \t]*\n(?:[ \t]*\n)*)")
_FENCE = re.compile(r"^\s*(?:```|~~~)", re.MULTILINE)


def _fence_count(text: str) -> int:
    return len(_FENCE.findall(text))


def split_blocks(body: str) -> list[dict]:
    """The body as `[{"text", "sep"}]`. A blank line separates blocks, except
    inside a fenced code block, which stays whole however many it holds."""
    if not body:
        return []
    parts = _SEP.split(body)        # text, sep, text, sep, …, text
    blocks: list[dict] = []
    i = 0
    while i < len(parts):
        text = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        # An unbalanced fence: those blank lines were inside the code block.
        while _fence_count(text) % 2 == 1 and i < len(parts):
            text += sep + parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            i += 2
        blocks.append({"text": text, "sep": sep})
    # A single trailing newline rides on the last block's separator, not in the
    # text a person edits.
    last = blocks[-1]
    if not last["sep"] and last["text"].endswith("\n"):
        last["text"] = last["text"][:-1]
        last["sep"] = "\n"
    return blocks


def join_blocks(blocks: list[dict]) -> str:
    """Blocks back to the body. The inverse of `split_blocks`, byte for byte."""
    out = []
    count = len(blocks)
    for index, block in enumerate(blocks):
        sep = block.get("sep") or ("\n\n" if index < count - 1 else "")
        out.append((block.get("text") or "") + sep)
    return "".join(out)


def block_hash(text: str) -> str:
    """Short content hash. Not a security boundary — a drift detector, and the
    guard a caller passes back as `if_hash`."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def new_block_id() -> str:
    return secrets.token_hex(6)


def align(stored: list[dict] | None, blocks: list[dict]) -> list[dict]:
    """The id list for `blocks`, keeping an id wherever the text is the same.

    Called after any write that replaced the whole body, where nobody said
    which block is which. Keeping an id by position alone would move a
    comment onto someone else's sentence, so identity follows the TEXT:

      1. a block whose hash matches the stored entry at the same position
         keeps that id — the common case, where one paragraph of several
         changed;
      2. otherwise a block whose hash matches an unclaimed stored entry
         anywhere keeps that id — a reorder;
      3. anything left is NEW, and gets a new id. A rewritten paragraph is a
         new block on purpose: a comment on the old wording should be reported
         as orphaned rather than silently moved onto text it never read.
    """
    stored = list(stored or [])
    out: list[dict | None] = [None] * len(blocks)
    taken: set[int] = set()

    for position, block in enumerate(blocks):
        digest = block_hash(block["text"])
        if position < len(stored) and stored[position].get("hash") == digest:
            out[position] = {"id": stored[position].get("id") or new_block_id(),
                             "rev": int(stored[position].get("rev") or 1),
                             "hash": digest}
            taken.add(position)
    for position, block in enumerate(blocks):
        if out[position] is not None:
            continue
        digest = block_hash(block["text"])
        match = next((i for i, entry in enumerate(stored)
                      if i not in taken and entry.get("hash") == digest), None)
        if match is not None:
            taken.add(match)
            out[position] = {"id": stored[match].get("id") or new_block_id(),
                             "rev": int(stored[match].get("rev") or 1),
                             "hash": digest}
    for position, block in enumerate(blocks):
        if out[position] is None:
            out[position] = {"id": new_block_id(), "rev": 1,
                             "hash": block_hash(block["text"])}
    return [entry for entry in out if entry is not None]

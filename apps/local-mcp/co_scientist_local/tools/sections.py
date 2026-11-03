"""Section-level reads/writes.

The section doc holds the canonical body text plus metadata (word_count,
status). On every write we regenerate the manuscript.md blob so consumers
that want one file (export, dashboard download) get it for free.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso, word_count
from .blocks import align, block_hash, join_blocks, split_blocks
from .activity import log_event
from .display_lint import inline_object_warnings
from .papers import _paper_path, _regenerate_manuscript, _section_path


def get_section(state: State, slug: str, key: str) -> dict:
    """Return a section doc by key."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    doc = state.backend.get_doc(_section_path(state, slug, key))
    if doc is None:
        raise NotFound(f"section not found: {slug!r}/{key!r}")
    return doc


def list_sections(state: State, slug: str) -> list[dict]:
    """List all sections for a paper, ordered by sort_order."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(
        state.project_path("papers", slug, "sections")
    )
    sections = [data for _, data in pairs]
    sections.sort(key=lambda s: s.get("sort_order", 999))
    return sections


def _replace_block(existing: dict, block_id: str, text: str,
                   if_rev: int | None) -> tuple[str, list[dict]]:
    """The body with one block's text swapped, and the id list that goes with it.

    The id is KEPT and the revision incremented, which is the whole point: a
    reworded paragraph is the same paragraph, so a comment anchored to it still
    points at the words its author read. (A write of the whole body cannot know
    that, and `align` there deliberately treats rewritten text as a new block
    so the comment is reported orphaned instead of moved.)
    """
    blocks, stored = _blocks_for(existing)
    position = next((i for i, entry in enumerate(stored)
                     if entry["id"] == block_id), None)
    if position is None:
        raise NotFound(
            f"block {block_id!r} is not in {existing.get('key') or 'this section'} "
            f"— it was rewritten or removed; read the blocks again")
    current = stored[position]
    if if_rev is not None and int(if_rev) != int(current["rev"]):
        raise BlockConflict(
            f"block {block_id} is at rev {current['rev']}, you read "
            f"{if_rev} — someone edited it since. Their text stands; read it "
            f"and decide.",
            block={"id": block_id, "rev": current["rev"],
                   "text": blocks[position]["text"]})
    updated = list(blocks)
    updated[position] = {"text": text, "sep": blocks[position]["sep"] or "\n\n"}
    entries = [dict(entry) for entry in stored]
    entries[position] = {"id": block_id, "rev": int(current["rev"]) + 1,
                         "hash": block_hash(text)}
    return join_blocks(updated), entries


class BlockConflict(ValueError):
    """A block-level write whose `if_rev` is not the block's current one.

    Carries the block as it stands, because the caller has to decide with the
    new text in hand; their edit stands either way, and this is never resolved
    by overwriting.
    """

    def __init__(self, message: str, *, block: dict):
        super().__init__(message)
        self.block = block


def _blocks_for(existing: dict) -> tuple[list[dict], list[dict]]:
    """A section's blocks and their id entries, repaired if the two disagree.

    The body is canonical. The id list lives beside it and can be stale — an
    older client, a restore, a hand edit in the console — so it is realigned
    against the body on every read rather than trusted.
    """
    blocks = split_blocks(existing.get("body") or "")
    stored = existing.get("blocks") or []
    if len(stored) != len(blocks) or any(
            entry.get("hash") != block_hash(block["text"])
            for entry, block in zip(stored, blocks)):
        stored = align(stored, blocks)
    return blocks, stored


def section_blocks(state: State, slug: str, key: str) -> list[dict]:
    """A section as addressable blocks: `id`, `rev`, `text`.

    What a comment anchors to and what a block-level write names. The body
    stays the canonical string; this is identity laid over it.
    """
    path = _section_path(state, slug, key)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"section not found: {slug!r}/{key!r}")
    blocks, stored = _blocks_for(existing)
    # Persist a list that had to be rebuilt, or the ids are minted fresh on
    # every read and nothing can be anchored to them — a comment stored
    # yesterday would point at an id that no longer exists. Written only when
    # it actually changed, so a read stays a read in the common case.
    if stored != (existing.get("blocks") or []):
        state.backend.update_doc(path, {"blocks": stored})
    return [{"id": entry["id"], "rev": entry["rev"], "hash": entry["hash"],
             "text": block["text"]}
            for entry, block in zip(stored, blocks)]


def update_section(
    state: State,
    slug: str,
    key: str,
    *,
    body: str | None = None,
    status: str | None = None,
    title: str | None = None,
    block_id: str | None = None,
    text: str | None = None,
    if_rev: int | None = None,
) -> dict:
    """Update a section's body / status / title; regenerate manuscript blob.

    `block_id` + `text` replaces ONE block instead of the whole body, and
    `if_rev` is the revision the caller read. Writing the whole body is still
    allowed and still the way to restructure a section — but it is also how an
    agent and a person silently overwrote each other, because the last write
    won and nothing said a word. A block write with a stale `if_rev` raises
    `BlockConflict` and changes nothing: whoever typed into the section while
    you were thinking keeps their text.

    Returns the updated section doc.
    """
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    path = _section_path(state, slug, key)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"section not found: {slug!r}/{key!r}")

    keep_entries: list[dict] | None = None
    if block_id is not None or text is not None or if_rev is not None:
        if block_id is None or text is None:
            raise ValueError("a block write needs both block_id and text")
        if body is not None:
            raise ValueError("pass body, or block_id + text — not both")
        body, keep_entries = _replace_block(existing, block_id, text, if_rev)

    fields: dict = {"updated_at": now_iso()}
    if body is not None:
        fields["body"] = body
        fields["word_count"] = word_count(body)
        # Identity, carried across the edit. A block write says which block it
        # is, so that id survives the rewording. A whole-body write does not,
        # and `align` keeps an id only where the text is unchanged.
        if keep_entries is not None:
            fields["blocks"] = keep_entries
        else:
            _, stored = _blocks_for(existing)
            fields["blocks"] = align(stored, split_blocks(body))
    if status is not None:
        fields["status"] = status
    if title is not None:
        fields["title"] = title
    state.backend.update_doc(path, fields)

    # Bump paper's updated_at to feed list_papers ordering and dashboard "last activity"
    paper_fields: dict = {"updated_at": fields["updated_at"]}
    if key == "abstract" and body is not None:
        # The missing half of the mirror. update_paper(abstract=…) has always
        # written this section, but a section edit left `paper.abstract`
        # stale — so the two drifted, and the next update_paper wrote the old
        # field text over the newer section and deleted an author's clause
        # silently (feedback 5862140d9f73). One store, both directions.
        paper_fields["abstract"] = body
    state.backend.update_doc(_paper_path(state, slug), paper_fields)

    _regenerate_manuscript(state, slug)
    log_event(
        state, slug, action="section_updated",
        detail={
            "key": key,
            "word_count": fields.get("word_count"),
            "status": fields.get("status"),
        },
    )
    result = state.backend.get_doc(path)
    # Guardrail: flag inline markdown tables/images the author wrote straight
    # into the body — they're not registered objects and can be lost on rewrite.
    if body is not None:
        warnings = inline_object_warnings(body)
        if warnings:
            result = {**result, "warnings": warnings}
    return result


def replace_in_section(
    state: State, slug: str, key: str, *, old: str, new: str, count: int | None = 1,
    return_body: bool = False,
) -> dict:
    """A partial edit: replace `old` with `new` in the section body without
    re-sending it. Exact match or fail (see util.exact_replace).

    Answers with `replaced` (how many), `word_count`, and a `contexts` snippet
    around each replacement — not the whole body, which is what the caller
    just read. `return_body=True` for the old answer; a 3,700-word section is
    ~11k tokens of echo per one-word fix, and twenty fixes in a session is the
    whole budget (feedback ab361fd69b24).
    """
    from ..util import replace_with_contexts
    path = _section_path(state, slug, key)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"section not found: {slug!r}/{key!r}")
    body, n, contexts = replace_with_contexts(existing.get("body") or "",
                                              old, new, count)
    out = update_section(state, slug, key, body=body)
    if return_body:
        return {**out, "replaced": n, "contexts": contexts}
    # Everything the full row carried EXCEPT the body, so a caller that was
    # reading `updated_at` / `status` / warnings still gets them.
    return {**{k: v for k, v in out.items() if k != "body"},
            "replaced": n, "contexts": contexts}


def add_section(
    state: State,
    slug: str,
    *,
    key: str,
    title: str,
    sort_order: float | int,
    body: str = "",
) -> dict:
    """Register a custom section (e.g. journal-specific) beyond the defaults."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    path = _section_path(state, slug, key)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"section already exists: {slug!r}/{key!r}")
    now = now_iso()
    doc = {
        "key": key,
        "title": title,
        "body": body,
        "word_count": word_count(body),
        # Block identity from the start, so a comment made on a section nobody
        # has edited yet still anchors to a block rather than to a phrase.
        "blocks": align(None, split_blocks(body)),
        "status": "pending",
        "sort_order": sort_order,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    _regenerate_manuscript(state, slug)
    # The same guardrail update_section has always had. Creating a section is
    # the NORMAL way a document is built, so a body written here carried
    # exactly the risk the warning describes and was never told about it — the
    # author only found out if they happened to rewrite that section later,
    # and four sections sat with unregistered tables for two hours before an
    # unrelated edit surfaced it (feedback 306900c4f405).
    warnings = inline_object_warnings(body)
    if warnings:
        return {**doc, "warnings": warnings}
    return doc


def delete_section(state: State, slug: str, key: str) -> bool:
    """Delete a section; regenerate manuscript. Returns True if it existed."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    path = _section_path(state, slug, key)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    now = now_iso()
    state.backend.update_doc(_paper_path(state, slug), {"updated_at": now})
    _regenerate_manuscript(state, slug)
    log_event(state, slug, action="section_deleted", detail={"key": key})
    return True


def reorder_section(
    state: State,
    slug: str,
    key: str,
    *,
    sort_order: float | int,
) -> dict:
    """Set a section's sort_order; regenerate manuscript. Returns updated doc.

    Use fractional values to slot a section between two others without
    touching the rest (e.g. sort_order=2.5 to place it after key with order 2).
    """
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    path = _section_path(state, slug, key)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"section not found: {slug!r}/{key!r}")
    now = now_iso()
    state.backend.update_doc(path, {"sort_order": sort_order, "updated_at": now})
    state.backend.update_doc(_paper_path(state, slug), {"updated_at": now})
    _regenerate_manuscript(state, slug)
    log_event(
        state, slug, action="section_reordered",
        detail={"key": key, "sort_order": sort_order},
    )
    return state.backend.get_doc(path)


def get_manuscript(state: State, slug: str) -> str:
    """Return the assembled manuscript.md as a string."""
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    blob = state.backend.get_blob(state.project_path("papers", slug, "manuscript.md"))
    return blob.decode("utf-8") if blob else ""

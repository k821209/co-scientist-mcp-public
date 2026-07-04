"""Decks: presentations built from a paper.

A deck attaches to a paper and holds:
  - `concept`     — palette / typography / motif strings the slides
                    inherit (the "single source of visual unity"). The
                    PPTX export harvests `accent` / `bg` / `text` colors
                    from here to theme native text slides.
  - `theme`       — optional theme slug (e.g. "minimal-modern-academic")
  - `aspect_ratio` — "16:9" (default) | "16:10" | "4:3"; sets PPTX size
  - `audience`    — free text ("lab seminar", "Nature poster", …)
  - `duration_min` — target talk length in minutes
  - slides as a subcollection

Each slide doc carries:
  - `slide_number`  (1-based, sparse during edits, normalized by renumber_deck)
  - `role`          (title | outline | background | method | result |
                     discussion | conclusion | qa | custom)
  - `title`         short slide heading
  - `body`          markdown content for the body text
  - `prompt`        full-image prompt if the slide will be rendered via
                    generate_image (starts with the deck's unity header)
  - `notes`         MANDATORY speaker notes
  - `code`          optional code block (for shape-code render mode)
  - `render_mode`   "code-shape" | "paper-figure" | "ai-image" |
                    "hybrid" | "text". A `text` slide carries no image —
                    it becomes a native (editable) PPTX text slide at
                    export, styled from the deck concept's palette. A
                    `hybrid` slide carries `regions[]` — several images
                    of mixed types on one slide.
  - `figure_number` if render_mode == paper-figure
  - `regions`       if render_mode == hybrid: a list of positioned image
                    regions, each {id, render_mode, x/y/w/h fractions,
                    figure_number|prompt|code, caption, image_blob_path}.
                    Set via set_slide_regions; rendered via render_region.
  - `status`        "draft" | "rendered"

Render + PPTX export are Phase 3 — not implemented here. This module
ships the data layer + CRUD so /paper-deck can build the structure
incrementally.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso, slugify
from . import limits as _limits
from .activity import log_event
from .papers import _paper_path

_VALID_ROLES = {
    # canonical roles (paper-deck SKILL §4)
    "title", "outline", "background", "method", "result",
    "discussion", "conclusion", "qa", "custom",
    # extended vocabulary common in real decks (todo 007 #1)
    "hook", "thesis", "section", "figure", "image", "content",
}
_VALID_RENDER_MODES = {
    "code-shape", "paper-figure", "ai-image", "hybrid", "text", "code",
}
_VALID_DECK_STATUS = {"draft", "drafted", "rendered"}
_VALID_SLIDE_STATUS = {"draft", "rendered"}
_VALID_ASPECT = {"16:9", "16:10", "4:3"}
# A region is a leaf image — it cannot itself be `hybrid` or `text`.
_VALID_REGION_MODES = {"ai-image", "code-shape", "paper-figure"}
# How a region's image fills its box: contain = letterbox, never crop
# (figures, charts, tables); cover = fill the box, crop overflow
# (eyecatch / decorative / photos).
_VALID_FIT_MODES = {"contain", "cover"}


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


def _deck_path(state: State, slug: str, deck_id: str) -> str:
    return state.project_path("papers", slug, "decks", deck_id)


def _slides_path(state: State, slug: str, deck_id: str) -> str:
    return state.project_path("papers", slug, "decks", deck_id, "slides")


def _slide_path(state: State, slug: str, deck_id: str, slide_id: str) -> str:
    return state.project_path("papers", slug, "decks", deck_id, "slides", slide_id)


# ─── deck-level CRUD ────────────────────────────────────────────────────────


def create_deck(
    state: State,
    slug: str,
    *,
    title: str,
    audience: str | None = None,
    duration_min: int | None = None,
    theme: str | None = None,
    image_style: str | None = None,
    aspect_ratio: str = "16:9",
    deck_id: str | None = None,
) -> dict:
    """Create a deck attached to `slug`. Idempotent on (slug, deck_id) — if
    deck_id is supplied and exists, returns the existing doc unchanged.
    Without deck_id, deck slug is derived from `title`.
    """
    _ensure_paper(state, slug)
    if not title or not title.strip():
        raise ValueError("title is required")
    if aspect_ratio not in _VALID_ASPECT:
        raise ValueError(
            f"invalid aspect_ratio: {aspect_ratio!r}; "
            f"choose from {sorted(_VALID_ASPECT)}"
        )
    # Unicode-aware slugify keeps 한글/CJK titles; only a letter/digit-free
    # title yields "" — fall back to a generated id so create never breaks.
    deck_id = deck_id or slugify(title) or f"deck-{new_id()[:8]}"
    path = _deck_path(state, slug, deck_id)
    existing = state.backend.get_doc(path)
    if existing is not None:
        return existing
    _limits.enforce_cap(
        len(state.backend.list_collection(state.project_path("papers", slug, "decks"))),
        _limits.DECKS_PER_PAPER, "decks per paper",
    )
    now = now_iso()
    doc = {
        "id": deck_id,
        "title": title,
        "audience": audience,
        "duration_min": duration_min,
        "theme": theme,
        "image_style": image_style,  # deck-wide AI-image style hint
        "aspect_ratio": aspect_ratio,
        "concept": None,            # set later via update_deck
        "status": "draft",
        "slide_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    log_event(
        state, slug, action="deck_created",
        detail={"deck_id": deck_id, "title": title},
        actor="claude",
    )
    return doc


def get_deck(state: State, slug: str, deck_id: str) -> dict:
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_deck_path(state, slug, deck_id))
    if doc is None:
        raise NotFound(f"deck not found: {deck_id!r} on paper {slug!r}")
    return doc


def list_decks(state: State, slug: str) -> list[dict]:
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "decks"))
    decks = [data for _, data in pairs]
    decks.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return decks


def update_deck(
    state: State,
    slug: str,
    deck_id: str,
    *,
    title: str | None = None,
    audience: str | None = None,
    duration_min: int | None = None,
    theme: str | None = None,
    image_style: str | None = None,
    aspect_ratio: str | None = None,
    concept: str | None = None,
    status: str | None = None,
) -> dict:
    _ensure_paper(state, slug)
    path = _deck_path(state, slug, deck_id)
    cur = state.backend.get_doc(path)
    if cur is None:
        raise NotFound(f"deck not found: {deck_id!r} on paper {slug!r}")
    fields: dict = {"updated_at": now_iso()}
    if title is not None: fields["title"] = title
    if audience is not None: fields["audience"] = audience
    if duration_min is not None: fields["duration_min"] = duration_min
    if theme is not None: fields["theme"] = theme
    if image_style is not None: fields["image_style"] = image_style
    if aspect_ratio is not None:
        if aspect_ratio not in _VALID_ASPECT:
            raise ValueError(
                f"invalid aspect_ratio: {aspect_ratio!r}; "
                f"choose from {sorted(_VALID_ASPECT)}"
            )
        fields["aspect_ratio"] = aspect_ratio
    if concept is not None: fields["concept"] = concept
    if status is not None:
        if status not in _VALID_DECK_STATUS:
            raise ValueError(f"invalid deck status: {status!r}")
        fields["status"] = status
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def delete_deck(state: State, slug: str, deck_id: str) -> bool:
    """Delete deck doc + cascade all slide docs."""
    _ensure_paper(state, slug)
    path = _deck_path(state, slug, deck_id)
    if state.backend.get_doc(path) is None:
        return False
    # cascade slides
    for slide_id, _ in state.backend.list_collection(_slides_path(state, slug, deck_id)):
        state.backend.delete_doc(_slide_path(state, slug, deck_id, slide_id))
    state.backend.delete_doc(path)
    log_event(
        state, slug, action="deck_deleted",
        detail={"deck_id": deck_id}, actor="claude",
    )
    return True


# ─── slide CRUD ─────────────────────────────────────────────────────────────


def _validate_slide_fields(
    role: str | None,
    render_mode: str | None,
    status: str | None,
) -> None:
    if role is not None and role not in _VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")
    if render_mode is not None and render_mode not in _VALID_RENDER_MODES:
        raise ValueError(f"invalid render_mode: {render_mode!r}")
    if status is not None and status not in _VALID_SLIDE_STATUS:
        raise ValueError(f"invalid slide status: {status!r}")


def add_slide(
    state: State,
    slug: str,
    deck_id: str,
    *,
    slide_number: int,
    role: str,
    title: str,
    body: str = "",
    prompt: str = "",
    notes: str = "",
    code: str = "",
    render_mode: str | None = None,
    figure_number: int | None = None,
) -> dict:
    """Insert a slide at the 1-based `slide_number` (a TRUE insert): every
    existing slide at that number or later is shifted +1, so the new slide
    lands exactly at `slide_number` with no duplicate-number window. To insert
    "between 4 and 5", add at 5. To append, use `len(list_slides)+1` (or any
    number past the end). `reorder_deck` / `renumber_deck` remain for bulk
    reordering / gap-packing.

    `render_mode` is optional (todo 010 — defer the design decision to
    authoring time). When `None`, the exporter / renderer infers the
    mode from which fields are populated (regions → hybrid, code with
    python-pptx signals → code, figure_number → paper-figure, prompt
    → ai-image, otherwise → text). Pass an explicit mode only when you
    want to lock the strategy at outline time."""
    _ensure_paper(state, slug)
    if state.backend.get_doc(_deck_path(state, slug, deck_id)) is None:
        raise NotFound(f"deck not found: {deck_id!r} on paper {slug!r}")
    _validate_slide_fields(role, render_mode, None)
    if slide_number < 1:
        raise ValueError("slide_number must be >= 1")
    now = now_iso()
    # TRUE insert: shift every existing slide at >= slide_number up by 1 so the
    # new slide occupies `slide_number` with no duplicate-number window.
    for s in list_slides(state, slug, deck_id):
        cur = s.get("slide_number") or 0
        if cur >= slide_number:
            state.backend.update_doc(
                _slide_path(state, slug, deck_id, s["id"]),
                {"slide_number": cur + 1, "updated_at": now},
            )
    # Doc id is the slide_number zero-padded so list ordering by id matches.
    slide_id = f"s{slide_number:04d}_{new_id()[:6]}"
    doc = {
        "id": slide_id,
        "slide_number": slide_number,
        "role": role,
        "title": title,
        "body": body,
        "prompt": prompt,
        "notes": notes,
        "code": code,
        "render_mode": render_mode,
        "figure_number": figure_number,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(_slide_path(state, slug, deck_id, slide_id), doc)
    # bump deck.slide_count + updated_at
    deck_path = _deck_path(state, slug, deck_id)
    deck = state.backend.get_doc(deck_path) or {}
    state.backend.update_doc(deck_path, {
        "slide_count": (deck.get("slide_count") or 0) + 1,
        "updated_at": now,
    })
    return doc


def update_slide(
    state: State,
    slug: str,
    deck_id: str,
    slide_id: str,
    *,
    slide_number: int | None = None,
    role: str | None = None,
    title: str | None = None,
    body: str | None = None,
    prompt: str | None = None,
    notes: str | None = None,
    code: str | None = None,
    render_mode: str | None = None,
    figure_number: int | None = None,
    status: str | None = None,
) -> dict:
    _ensure_paper(state, slug)
    path = _slide_path(state, slug, deck_id, slide_id)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"slide not found: {slide_id!r}")
    _validate_slide_fields(role, render_mode, status)
    fields: dict = {"updated_at": now_iso()}
    if slide_number is not None: fields["slide_number"] = slide_number
    if role is not None: fields["role"] = role
    if title is not None: fields["title"] = title
    if body is not None: fields["body"] = body
    if prompt is not None: fields["prompt"] = prompt
    if notes is not None: fields["notes"] = notes
    if code is not None: fields["code"] = code
    if render_mode is not None: fields["render_mode"] = render_mode
    if figure_number is not None: fields["figure_number"] = figure_number
    if status is not None: fields["status"] = status
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def _validate_region(r: dict, index: int) -> dict:
    """Validate one region spec; return a normalized region dict (no id,
    no render fields — those are added by set_slide_regions)."""
    mode = r.get("render_mode")
    if mode not in _VALID_REGION_MODES:
        raise ValueError(
            f"region {index}: render_mode must be one of "
            f"{sorted(_VALID_REGION_MODES)}, got {mode!r}"
        )
    box: dict[str, float] = {}
    for k in ("x", "y", "w", "h"):
        v = r.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"region {index}: {k} must be a number in [0,1]")
        v = float(v)
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"region {index}: {k}={v} is outside [0,1]")
        box[k] = v
    if box["w"] <= 0 or box["h"] <= 0:
        raise ValueError(f"region {index}: w and h must be > 0")
    if box["x"] + box["w"] > 1.0 + 1e-6 or box["y"] + box["h"] > 1.0 + 1e-6:
        raise ValueError(f"region {index}: box extends past the slide edge")
    fig = r.get("figure_number")
    prompt = r.get("prompt")
    if mode == "paper-figure" and fig is None:
        raise ValueError(f"region {index}: paper-figure region needs figure_number")
    if mode == "ai-image" and not (prompt and str(prompt).strip()):
        raise ValueError(f"region {index}: ai-image region needs a prompt")
    fit = r.get("fit") or "contain"
    if fit not in _VALID_FIT_MODES:
        raise ValueError(
            f"region {index}: fit must be 'contain' or 'cover', got {fit!r}"
        )
    return {
        "render_mode": mode,
        "x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"],
        "fit": fit,
        "figure_number": fig,
        "prompt": prompt,
        "code": r.get("code"),
        "caption": r.get("caption"),
    }


def set_slide_regions(
    state: State,
    slug: str,
    deck_id: str,
    slide_id: str,
    *,
    regions: list[dict],
) -> dict:
    """Define the multi-image region layout for a slide. Each region is
    one positioned image with its own render_mode (ai-image / code-shape
    / paper-figure); x/y/w/h are fractions (0..1) of the slide so the
    layout is aspect-independent.

    Forces the slide's render_mode to 'hybrid', EXCEPT when the slide is
    in 'code' mode OR already carries a `code` snippet — in that case
    regions act as image placeholders the slide's `code` references via
    `h.image_region(region_id, ...)`. This lets the agent plan a
    slide's images up-front (regions = placeholders), have them
    rendered separately, and embed them by id at compose time.

    Preserving 'code' for a slide that has `code` matters: the export
    runs a `code` slide's snippet (placing both text and region images),
    whereas a `hybrid` slide only lays down region pictures — so snapping
    a code slide to hybrid would silently drop its text/shape overlay.

    Replaces any existing regions. A region whose *source* (render_mode +
    figure_number / prompt / code) is unchanged keeps its rendered image,
    so re-positioning a region doesn't force a re-render.
    """
    _ensure_paper(state, slug)
    path = _slide_path(state, slug, deck_id, slide_id)
    cur = state.backend.get_doc(path)
    if cur is None:
        raise NotFound(f"slide not found: {slide_id!r}")
    if not regions:
        raise ValueError("regions must be a non-empty list")

    def _source_key(r: dict) -> tuple:
        return (
            r.get("render_mode"), r.get("figure_number"),
            (r.get("prompt") or "").strip(), (r.get("code") or "").strip(),
        )

    # Carry rendered images across when a region's source is unchanged.
    prior = {
        _source_key(r): r
        for r in (cur.get("regions") or [])
        if r.get("image_blob_path")
    }

    normalized: list[dict] = []
    for i, raw in enumerate(regions):
        reg = _validate_region(raw, i)
        reg["id"] = f"r{i + 1}"
        old = prior.get(_source_key(reg))
        reg["image_blob_path"] = old.get("image_blob_path") if old else None
        reg["rendered_at"] = old.get("rendered_at") if old else None
        normalized.append(reg)

    # Preserve `code` mode (image placeholder use) whenever the slide is
    # in code mode OR carries a code snippet; everything else snaps to
    # `hybrid` (the historical default). Without the snippet check, adding
    # regions to a code slide whose render_mode was left inferred (None)
    # would flip it to hybrid and drop its text/shape overlay on export.
    has_code = bool((cur.get("code") or "").strip())
    new_mode = "code" if (cur.get("render_mode") == "code" or has_code) else "hybrid"
    state.backend.update_doc(path, {
        "regions": normalized,
        "render_mode": new_mode,
        "updated_at": now_iso(),
    })
    return state.backend.get_doc(path)


def delete_slide(state: State, slug: str, deck_id: str, slide_id: str) -> bool:
    _ensure_paper(state, slug)
    path = _slide_path(state, slug, deck_id, slide_id)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    deck_path = _deck_path(state, slug, deck_id)
    deck = state.backend.get_doc(deck_path) or {}
    state.backend.update_doc(deck_path, {
        "slide_count": max(0, (deck.get("slide_count") or 1) - 1),
        "updated_at": now_iso(),
    })
    return True


def list_slides(
    state: State,
    slug: str,
    deck_id: str,
    *,
    fields: list[str] | None = None,
) -> list[dict]:
    """List a deck's slides in display order.

    Ordering is `(slide_number, created_at, id)`. `add_slide` now does a true
    insert (shifts later slides), so duplicate numbers shouldn't arise; the
    created_at/id tie-break just keeps ordering deterministic if they ever do.

    `fields`, if given, projects each slide to just those keys (plus `id`
    and `slide_number`, always kept). Use it to skip the large `code` /
    `notes` blobs when you only need an index — full `list_slides()`
    output can blow past the tool's token budget on a 20-slide deck."""
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(_slides_path(state, slug, deck_id))
    slides = [data for _, data in pairs]
    slides.sort(key=lambda s: (
        s.get("slide_number") or 0,
        s.get("created_at") or "",
        s.get("id") or "",
    ))
    if fields is not None:
        keep = {"id", "slide_number", *fields}
        slides = [{k: v for k, v in s.items() if k in keep} for s in slides]
    return slides


def renumber_deck(state: State, slug: str, deck_id: str) -> dict:
    """Pack slide_numbers tightly starting at 1, preserving order.
    Call after bulk add/delete. Returns {old_to_new: {old: new}, count}."""
    _ensure_paper(state, slug)
    slides = list_slides(state, slug, deck_id)
    old_to_new: dict[int, int] = {}
    now = now_iso()
    for i, s in enumerate(slides, start=1):
        old = s.get("slide_number")
        if old != i:
            state.backend.update_doc(
                _slide_path(state, slug, deck_id, s["id"]),
                {"slide_number": i, "updated_at": now},
            )
            if old is not None:
                old_to_new[old] = i
    return {"count": len(slides), "old_to_new": old_to_new}


def reorder_deck(state: State, slug: str, deck_id: str, order: list[str]) -> dict:
    """Set the slide order explicitly: `order` is the full list of slide ids in
    the desired sequence; each is reassigned slide_number 1..N in one pass (no
    duplicate-number window). The deck analogue of reorder_section /
    reorder_supplementary — use it to move/reorder slides instead of juggling
    add_slide + renumber. `order` must be a permutation of the deck's current
    slide ids. Returns {count, order}."""
    _ensure_paper(state, slug)
    current = {s["id"] for s in list_slides(state, slug, deck_id)}
    seen = list(dict.fromkeys(order))  # de-dup, preserve order
    given = set(seen)
    if given != current:
        missing = sorted(current - given)
        extra = sorted(given - current)
        raise ValueError(
            f"order must be a permutation of the deck's {len(current)} slide ids "
            f"(missing: {missing}; unknown: {extra})"
        )
    now = now_iso()
    for i, sid in enumerate(seen, start=1):
        state.backend.update_doc(
            _slide_path(state, slug, deck_id, sid),
            {"slide_number": i, "updated_at": now},
        )
    return {"count": len(seen), "order": seen}


# ─── slide comments ─────────────────────────────────────────────────────────
#
# A reviewer leaves a comment on a specific slide from the dashboard's
# Presentations tab. Mirrors the manuscript review loop, slide-scoped:
# the dashboard writes `source='user'` comments, the agent reads the open
# ones with list_deck_comments, revises the slide, then resolves them.
# `region_id` optionally points the comment at one region of a hybrid
# slide.

_VALID_COMMENT_STATUS = {"open", "resolved", "rejected"}


def _comments_path(state: State, slug: str, deck_id: str, slide_id: str) -> str:
    return state.project_path(
        "papers", slug, "decks", deck_id, "slides", slide_id, "comments",
    )


def _comment_path(state: State, slug: str, deck_id: str, slide_id: str,
                  comment_id: str) -> str:
    return _comments_path(state, slug, deck_id, slide_id) + "/" + comment_id


def list_deck_comments(
    state: State, slug: str, deck_id: str, *, status: str | None = "open",
) -> list[dict]:
    """Every comment across the deck's slides, each tagged with its slide.

    `status='open'` (default) returns only unaddressed comments — the
    agent's to-do list for revising the deck. Pass status=None for all.
    """
    _ensure_paper(state, slug)
    if state.backend.get_doc(_deck_path(state, slug, deck_id)) is None:
        raise NotFound(f"deck not found: {deck_id!r} on paper {slug!r}")
    out: list[dict] = []
    for slide in list_slides(state, slug, deck_id):
        pairs = state.backend.list_collection(
            _comments_path(state, slug, deck_id, slide["id"]))
        for cid, c in pairs:
            if status is not None and c.get("status") != status:
                continue
            out.append({
                "comment_id": cid,
                "slide_id": slide["id"],
                "slide_number": slide.get("slide_number"),
                "slide_title": slide.get("title"),
                **c,
            })
    out.sort(key=lambda c: (c.get("slide_number") or 0,
                            c.get("created_at") or ""))
    return out


def resolve_deck_comment(
    state: State, slug: str, deck_id: str, slide_id: str, comment_id: str,
    *, status: str = "resolved",
) -> dict:
    """Mark a slide comment `resolved` (addressed) or `rejected` (declined)
    — or `open` to reopen it."""
    if status not in _VALID_COMMENT_STATUS:
        raise ValueError(
            f"status must be one of {sorted(_VALID_COMMENT_STATUS)}"
        )
    path = _comment_path(state, slug, deck_id, slide_id, comment_id)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"comment not found: {comment_id!r}")
    state.backend.update_doc(path, {
        "status": status,
        "resolved_at": now_iso() if status != "open" else None,
    })
    return state.backend.get_doc(path)

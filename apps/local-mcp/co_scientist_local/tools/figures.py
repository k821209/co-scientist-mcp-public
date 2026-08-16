"""Figures: doc metadata + image blob.

Paths:
    doc:  users/{uid}/papers/{slug}/figures/{figure_number}
    blob: users/{uid}/papers/{slug}/figures/figure_{n}.{ext}

When `add_figure` is given a `local_path`, we read the bytes and upload them
to the blob backend. The doc carries a `blob_path` that consumers (dashboard,
export pipeline) use to download the image. We never store image bytes inside
the doc.

For supplementary figures the original uses `figure_number = N + 100`
(SFigure 1 → figure_number=101). Same convention here.
"""
from __future__ import annotations

import os
import pathlib

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from . import limits as _limits
from .papers import _paper_path

SUPPLEMENTARY_NUMBER_OFFSET = 100


def is_supplementary_number(n) -> bool:
    """Whether a figure/table number denotes a supplementary item.

    Supplementary item N is stored as OFFSET + N, so the FIRST one is 101 and
    100 is the hundredth main item. Every docstring here said "≥ 101" and the
    reorder path allocates from 101 up, but the two list functions compared
    `>= 100` — so a manually registered item 100 was classified supplementary
    and then labelled "STable 0". One predicate, so the readers cannot drift
    from the writer again.
    """
    return isinstance(n, int) and n > SUPPLEMENTARY_NUMBER_OFFSET


def _figure_path(state: State, slug: str, figure_number: int) -> str:
    return state.project_path("papers", slug, "figures", str(figure_number))


def _figure_blob_path(state: State, slug: str, figure_number: int, ext: str) -> str:
    return state.project_path(
        "papers", slug, "figures", f"figure_{figure_number}.{ext.lstrip('.')}",
    )


# The one line a caller sees at the moment memory is freshest. Registration is
# when back-filling provenance is cheapest — an hour later the command is gone
# from scrollback, and a month later it is unrecoverable (feedback f3f9b4b56577:
# 9 hours of foreground training whose hyperparameters no longer exist anywhere).
# Returned, never stored, and never an error: a schematic has no analysis behind
# it and failing the call would be wrong.
_NO_PROVENANCE_HINT = (
    "no source_analysis on this artifact — if its numbers were computed, record "
    "the run (create_analysis + record_analysis_run) and link it with "
    "source_analysis=, or it will be untraceable at submission. Ignore for "
    "schematics and hand-built tables."
)


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")



def _prompt_fields(existing: dict | None, prompt: str | None,
                   uploading_bytes: bool) -> dict:
    """Decide what happens to the stored generation `prompt` on this write.

    The stored prompt is an INSTRUCTION the dashboard's re-render button obeys.
    When a generated figure is later replaced by a hand-built one — an uploaded
    vector, say — the prompt survives and silently outranks the image: pressing
    re-render regenerates an AI raster from text that no longer describes the
    figure, destroying a production asset with nothing to warn anyone. Reported
    on a real manuscript whose stored prompt still specified a notation the paper
    had deliberately retired, so a re-render would have produced a figure
    contradicting its own caption (feedback 3f65f2e18dd5).

    So: supplying image BYTES without also supplying a prompt is taken as the
    statement it is — this image is no longer what the prompt described. The old
    text moves to `prompt_superseded` rather than being deleted, because it is
    still the provenance of whatever was there before. `generate_image` passes
    both prompt and local_path, so the generation path is untouched.

    An explicit empty string clears it too, for the case where no new bytes are
    being written.
    """
    prev = (existing or {}).get("prompt")
    if prompt is not None and prompt.strip():
        return {"prompt": prompt, "prompt_superseded": None}
    if prompt is not None:                       # explicit "" → clear
        return {"prompt": None, "prompt_superseded": prev or
                (existing or {}).get("prompt_superseded")}
    if uploading_bytes and prev:
        return {"prompt": None, "prompt_superseded": prev}
    return {"prompt": prev,
            "prompt_superseded": (existing or {}).get("prompt_superseded")}


def add_figure(
    state: State,
    slug: str,
    *,
    figure_number: int,
    title: str,
    caption: str | None = None,
    legend: str | None = None,
    local_path: str | None = None,
    status: str = "pending",
    overwrite: bool = False,
    prompt: str | None = None,
    style_applied: str | None = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
    source_analysis: str | None = None,
) -> dict:
    """Register a figure. If `local_path` is provided, upload the file bytes.

    With `overwrite=True`, an existing figure at the same `figure_number` is
    replaced in place (created_at preserved) instead of raising.

    `prompt`/`style_applied`/`aspect_ratio`/`quality` record how a generated
    figure was produced so the dashboard can show (and let the user edit) them
    and so a re-render reuses the same shape. They are preserved across an
    overwrite when not supplied. Writing a figure always clears
    `rerender_pending` — a fresh render satisfies any pending web edit.
    """
    _ensure_paper(state, slug)
    path = _figure_path(state, slug, figure_number)
    existing = state.backend.get_doc(path)
    if existing is not None and not overwrite:
        raise ValueError(f"figure {figure_number} already exists for {slug!r}")
    if existing is None:  # adding a NEW figure (not overwriting) → cap applies
        _limits.enforce_cap(
            len(state.backend.list_collection(state.project_path("papers", slug, "figures"))),
            _limits.FIGURES_PER_PAPER, "figures per paper",
        )

    blob_path: str | None = None
    if local_path:
        p = pathlib.Path(local_path)
        if not p.is_file():
            raise FileNotFoundError(f"local figure file not found: {local_path}")
        ext = p.suffix.lstrip(".") or "png"
        blob_path = _figure_blob_path(state, slug, figure_number, ext)
        state.backend.put_blob(blob_path, p.read_bytes())

    now = now_iso()
    doc = {
        "figure_number": figure_number,
        "title": title,
        "caption": caption,
        "legend": legend,
        "blob_path": blob_path,
        "status": status,
        **_prompt_fields(existing, prompt, bool(local_path)),
        "style_applied": style_applied if style_applied is not None
        else (existing.get("style_applied") if existing else None),
        "aspect_ratio": aspect_ratio if aspect_ratio is not None
        else (existing.get("aspect_ratio") if existing else None),
        "quality": quality if quality is not None
        else (existing.get("quality") if existing else None),
        "rerender_pending": False,
        # Provenance link for the export-time staleness check (see
        # exports.prepare_export). Preserved on overwrite so a re-upload that
        # omits it doesn't silently drop the link.
        "source_analysis": source_analysis if source_analysis is not None
        else (existing.get("source_analysis") if existing else None),
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
        # When the IMAGE last changed, as opposed to any field on the row. The
        # staleness check compares against this, because `updated_at` also moves
        # for a legend fix or for adding the provenance link — either of which
        # would otherwise mark a stale PNG fresh. On an overwrite that ships no
        # new bytes, the previous value is kept.
        "content_updated_at": now if (local_path or not existing)
        else (existing.get("content_updated_at") or existing.get("updated_at")),
    }
    state.backend.set_doc(path, doc)
    if not (source_analysis or "").strip():
        return {**doc, "provenance_hint": _NO_PROVENANCE_HINT}
    return doc


def update_figure(
    state: State,
    slug: str,
    figure_number: int,
    *,
    title: str | None = None,
    caption: str | None = None,
    legend: str | None = None,
    local_path: str | None = None,
    status: str | None = None,
    source_analysis: str | None = None,
    prompt: str | None = None,
) -> dict:
    """Patch a figure's metadata; optionally replace the image bytes.

    `source_analysis` links the figure to the analysis that generates it, which
    lets `prepare_export` warn when that analysis has re-run since.

    Replacing the bytes (`local_path`) without also passing a `prompt` retires
    the stored generation prompt to `prompt_superseded` — see `_prompt_fields`.
    `prompt=""` clears it explicitly."""
    _ensure_paper(state, slug)
    path = _figure_path(state, slug, figure_number)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"figure {figure_number} not found for {slug!r}")

    now = now_iso()
    fields: dict = {"updated_at": now}
    if title is not None: fields["title"] = title
    if caption is not None: fields["caption"] = caption
    if legend is not None: fields["legend"] = legend
    if status is not None: fields["status"] = status
    if source_analysis is not None: fields["source_analysis"] = source_analysis
    if prompt is not None or local_path:
        fields.update(_prompt_fields(existing, prompt, bool(local_path)))

    # Rows created before content_updated_at existed have none, so seed it from
    # the CURRENT updated_at before that gets overwritten. Without this, the very
    # call that adds the provenance link — a metadata-only edit — would assert the
    # figure is current and permanently mask the staleness the link was added to
    # find. Retro-linking existing figures is the normal path, not an edge case.
    if not existing.get("content_updated_at"):
        fields["content_updated_at"] = (
            existing.get("updated_at") or existing.get("created_at") or now
        )

    if local_path:
        p = pathlib.Path(local_path)
        if not p.is_file():
            raise FileNotFoundError(f"local figure file not found: {local_path}")
        ext = p.suffix.lstrip(".") or "png"
        # If the existing blob has a different extension, delete it first
        old_blob = existing.get("blob_path")
        new_blob = _figure_blob_path(state, slug, figure_number, ext)
        if old_blob and old_blob != new_blob:
            state.backend.delete_blob(old_blob)
        state.backend.put_blob(new_blob, p.read_bytes())
        fields["blob_path"] = new_blob
        fields["content_updated_at"] = now      # new bytes = new content

    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def get_figure(
    state: State,
    slug: str,
    figure_number: int,
    *,
    dest_dir: str | None = None,
    dest_path: str | None = None,
) -> dict:
    """Figure metadata. If `dest_dir` or `dest_path` is given, also download
    the image blob to local disk and add a `local_path` field to the result
    (so the agent can embed the PNG in a docx or hand it to the user).

    Writes to `dest_path` if given, else `dest_dir`/<blob-filename>.
    """
    _ensure_paper(state, slug)
    doc = state.backend.get_doc(_figure_path(state, slug, figure_number))
    if doc is None:
        raise NotFound(f"figure {figure_number} not found for {slug!r}")
    if dest_dir is None and dest_path is None:
        return doc
    blob_path = doc.get("blob_path")
    if not blob_path:
        raise NotFound(f"figure {figure_number} has no stored image")
    data = state.backend.get_blob(blob_path)
    if data is None:
        raise NotFound(f"figure {figure_number} blob missing at {blob_path}")
    if dest_path:
        out = pathlib.Path(dest_path).expanduser()
    else:
        out = pathlib.Path(dest_dir).expanduser() / pathlib.Path(blob_path).name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return {**doc, "local_path": str(out.resolve())}


def list_figures(state: State, slug: str, *, supplementary: bool | None = False) -> list[dict]:
    """List figures in ascending figure_number order.

    supplementary=False → main figures only (number ≤ 100, default); True →
    SFigures only (number ≥ 101); None → all (main + supplementary).
    """
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "figures"))
    figs = [data for _, data in pairs]
    if supplementary is not None:
        figs = [f for f in figs
                if is_supplementary_number(f["figure_number"]) == supplementary]
    figs.sort(key=lambda f: f["figure_number"])
    return figs


def delete_figure(state: State, slug: str, figure_number: int) -> bool:
    """Delete the figure doc and its blob. Returns True if it existed."""
    _ensure_paper(state, slug)
    path = _figure_path(state, slug, figure_number)
    existing = state.backend.get_doc(path)
    if existing is None:
        return False
    if existing.get("blob_path"):
        state.backend.delete_blob(existing["blob_path"])
    state.backend.delete_doc(path)
    return True

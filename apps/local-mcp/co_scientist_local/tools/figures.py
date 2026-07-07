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


def _figure_path(state: State, slug: str, figure_number: int) -> str:
    return state.project_path("papers", slug, "figures", str(figure_number))


def _figure_blob_path(state: State, slug: str, figure_number: int, ext: str) -> str:
    return state.project_path(
        "papers", slug, "figures", f"figure_{figure_number}.{ext.lstrip('.')}",
    )


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


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
        "prompt": prompt if prompt is not None
        else (existing.get("prompt") if existing else None),
        "style_applied": style_applied if style_applied is not None
        else (existing.get("style_applied") if existing else None),
        "aspect_ratio": aspect_ratio if aspect_ratio is not None
        else (existing.get("aspect_ratio") if existing else None),
        "quality": quality if quality is not None
        else (existing.get("quality") if existing else None),
        "rerender_pending": False,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
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
) -> dict:
    """Patch a figure's metadata; optionally replace the image bytes."""
    _ensure_paper(state, slug)
    path = _figure_path(state, slug, figure_number)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"figure {figure_number} not found for {slug!r}")

    fields: dict = {"updated_at": now_iso()}
    if title is not None: fields["title"] = title
    if caption is not None: fields["caption"] = caption
    if legend is not None: fields["legend"] = legend
    if status is not None: fields["status"] = status

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

    supplementary=False → main figures only (number < 101, default); True →
    SFigures only (number >= 101); None → all (main + supplementary).
    """
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(state.project_path("papers", slug, "figures"))
    figs = [data for _, data in pairs]
    if supplementary is not None:
        figs = [f for f in figs
                if (supplementary and f["figure_number"] >= SUPPLEMENTARY_NUMBER_OFFSET)
                or (not supplementary and f["figure_number"] < SUPPLEMENTARY_NUMBER_OFFSET)]
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

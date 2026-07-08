"""Project-scoped assets — a store for images/files that don't belong to a
paper (e.g. a video-only project's stills).

`generate_image` (no slug) drops results here at `projects/{pid}/assets/`; this
module lets an agent register a local file as an asset, list them, and — the gap
that forced a `state.backend.get_blob` workaround — download one back to disk so
tools that take local paths (ken_burns / montage) can consume it.

Paper-scoped assets (`papers/{slug}/assets/`) still live in images.py; pass a
`slug` to get_asset to reach those too.
"""
from __future__ import annotations

import pathlib

from ..state import State
from ..util import new_id, now_iso


def _assets_prefix(state: State, slug: str | None) -> tuple[str, ...]:
    return ("papers", slug, "assets") if slug else ("assets",)


def add_asset(state: State, local_path: str, *,
              filename: str | None = None, note: str | None = None) -> dict:
    """Register a local file as a PROJECT asset (uploads the bytes)."""
    p = pathlib.Path(local_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {local_path}")
    asset_id = new_id()
    name = filename or p.name
    blob_path = state.project_path("assets", name)
    state.backend.put_blob(blob_path, p.read_bytes())
    doc = {
        "asset_id": asset_id,
        "filename": name,
        "blob_path": blob_path,
        "size_bytes": p.stat().st_size,
        "note": note,
        "created_at": now_iso(),
    }
    state.backend.set_doc(state.project_path("assets", name), doc)
    return doc


def list_assets(state: State) -> list[dict]:
    """List PROJECT-scoped assets (projects/{pid}/assets/)."""
    pairs = state.backend.list_collection(state.project_path("assets"))
    items = [data for _, data in pairs]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def _find(state: State, key: str, slug: str | None) -> tuple[str, dict] | None:
    for filename, data in state.backend.list_collection(
        state.project_path(*_assets_prefix(state, slug))
    ):
        if data.get("asset_id") == key or filename == key:
            return filename, data
    return None


def get_asset(state: State, asset_id_or_filename: str, dest_path: str,
              *, slug: str | None = None) -> dict:
    """Download an asset's bytes to `dest_path` (creating parent dirs). Looks in
    the project store by default; pass `slug` for a paper's assets. Returns
    {dest_path, filename, size_bytes}."""
    found = _find(state, asset_id_or_filename, slug)
    if not found:
        scope = f"paper {slug!r}" if slug else "project"
        raise FileNotFoundError(f"asset {asset_id_or_filename!r} not found in {scope} assets")
    filename, data = found
    blob_path = data.get("blob_path")
    blob = state.backend.get_blob(blob_path) if blob_path else None
    if blob is None:
        raise FileNotFoundError(f"asset blob missing: {blob_path}")
    dest = pathlib.Path(dest_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return {"dest_path": str(dest), "filename": filename, "size_bytes": len(blob)}


def delete_asset(state: State, asset_id_or_filename: str) -> bool:
    """Delete a PROJECT asset (doc + blob) by asset_id or filename."""
    found = _find(state, asset_id_or_filename, None)
    if not found:
        return False
    filename, data = found
    if data.get("blob_path"):
        state.backend.delete_blob(data["blob_path"])
    state.backend.delete_doc(state.project_path("assets", filename))
    return True

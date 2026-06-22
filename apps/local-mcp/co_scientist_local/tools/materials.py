"""Reference materials: user-uploaded source files shared across a project.

These are the files a user drops into the dashboard for the agent to consult
while working — PDFs to read, datasets to analyze, prior drafts, notes, images.
They are PROJECT-level (shared by every paper in the project), distinct from
`references` (the bibliography of cited works): a material is a *file*, a
reference is a *citation*.

Paths:
    doc:  projects/{pid}/materials/{material_id}
    blob: projects/{pid}/materials/{material_id}__{filename}

The doc carries metadata (filename, content_type, size_bytes, description) and
a `blob_path`; the bytes live in Storage. `get_material` streams the bytes back
to the local disk so Claude Code can open the file directly.
"""
from __future__ import annotations

import pathlib
import re

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

# Filenames are user-supplied; keep only a safe basename for the blob key.
# Preserve Unicode letters/digits (Hangul etc.) — GCS/Storage object names
# are UTF-8, so only truly path-unsafe chars (spaces, slashes, punctuation)
# need replacing. Stripping all non-ASCII collapsed Korean names to "__md"
# (dev-todo P0-2).
_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def _safe_filename(name: str) -> str:
    base = pathlib.PurePosixPath(name).name or "file"
    cleaned = _UNSAFE.sub("_", base).strip("._") or "file"
    return cleaned[:120]


def _materials_collection(state: State) -> str:
    return state.project_path("materials")


def _material_path(state: State, material_id: str) -> str:
    return state.project_path("materials", material_id)


def add_material(
    state: State,
    *,
    local_path: str,
    ai_note: str | None = None,
    description: str | None = None,
) -> dict:
    """Upload a local file as a project reference material.

    Each material carries TWO separate notes, kept apart on purpose:
      - `user_note` — the user's own note, written ONLY from the dashboard.
        Agents must NEVER write or overwrite it.
      - `ai_note` — the agent's metadata about the file (what it is, columns,
        how it's relevant). Set it here or later with `update_material`.
    `description` is a legacy alias for `ai_note`."""
    p = pathlib.Path(local_path)
    if not p.is_file():
        raise FileNotFoundError(f"material file not found: {local_path}")

    data = p.read_bytes()
    material_id = new_id()
    # Keep the original UTF-8 name for display; only sanitize the blob key
    # (material_id already makes the key unique, so the safe name is cosmetic).
    filename = p.name
    blob_path = _material_path(state, f"{material_id}__{_safe_filename(p.name)}")
    state.backend.put_blob(blob_path, data)

    note = ai_note if ai_note is not None else description
    now = now_iso()
    doc = {
        "material_id": material_id,
        "filename": filename,
        "content_type": _guess_content_type(filename),
        "size_bytes": len(data),
        "blob_path": blob_path,
        "description": note,   # legacy field (mirrors ai_note for old readers)
        "ai_note": note,       # agent-authored metadata
        "user_note": None,     # user-authored; never set by the agent
        "uploaded_by": "agent",
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(_material_path(state, material_id), doc)
    return {**doc, "dashboard_url": state.dashboard_url("materials")}


def update_material(state: State, material_id: str, *, ai_note: str) -> dict:
    """Set/replace the agent's metadata note (`ai_note`) on a material — works
    on any material, including ones the user uploaded. ONLY touches `ai_note`;
    the user's `user_note` is never read or modified here, so the agent can't
    clobber what the user wrote. Returns the updated doc."""
    path = _material_path(state, material_id)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"material {material_id!r} not found")
    fields = {"ai_note": ai_note, "updated_at": now_iso()}
    state.backend.update_doc(path, fields)
    return {**existing, **fields}


def list_materials(state: State) -> list[dict]:
    """List the project's reference materials, newest first."""
    pairs = state.backend.list_collection(_materials_collection(state))
    mats = [data for _, data in pairs]
    mats.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return mats


def get_material(
    state: State,
    material_id: str,
    *,
    dest_dir: str = ".",
    dest_path: str | None = None,
) -> dict:
    """Download a material's bytes to local disk.

    Writes to `dest_path` if given, else `dest_dir`/<original-filename>.
    Returns {path, filename, size_bytes, content_type}.
    """
    doc = state.backend.get_doc(_material_path(state, material_id))
    if doc is None:
        raise NotFound(f"material {material_id!r} not found")
    blob_path = doc.get("blob_path")
    if not blob_path:
        raise NotFound(f"material {material_id!r} has no stored file")
    data = state.backend.get_blob(blob_path)
    if data is None:
        raise NotFound(f"material {material_id!r} blob missing at {blob_path}")

    if dest_path:
        out = pathlib.Path(dest_path).expanduser()
    else:
        out = pathlib.Path(dest_dir).expanduser() / doc.get("filename", material_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return {
        "path": str(out.resolve()),
        "filename": doc.get("filename"),
        "size_bytes": len(data),
        "content_type": doc.get("content_type"),
    }


def delete_material(state: State, material_id: str) -> bool:
    """Delete a material's doc + blob. Returns True if it existed."""
    path = _material_path(state, material_id)
    doc = state.backend.get_doc(path)
    if doc is None:
        return False
    if doc.get("blob_path"):
        state.backend.delete_blob(doc["blob_path"])
    state.backend.delete_doc(path)
    return True


_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "zip": "application/zip",
}


def _guess_content_type(filename: str) -> str:
    ext = pathlib.PurePosixPath(filename).suffix.lstrip(".").lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")

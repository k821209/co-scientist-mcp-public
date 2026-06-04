"""Backend protocol.

A Backend is the union of a document store (Firestore-ish) and a blob store
(Cloud-Storage-ish), addressed by slash-separated paths.

Paths are *all* of the form `users/{uid}/...` so that Firestore security rules
can enforce per-user isolation with a single rule. The tools layer always
prepends the active uid before calling the backend; the backend itself is
uid-agnostic and trusts whatever path it is given.

Doc paths have an even number of segments (collection/doc/collection/doc...).
Blob paths can be anything but conventionally end with a filename.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class NotFound(Exception):
    """Raised when a doc or blob does not exist and the caller required it."""


@runtime_checkable
class Backend(Protocol):
    # --- documents -----------------------------------------------------------

    def get_doc(self, path: str) -> dict | None:
        """Return the doc at `path` or None if it does not exist."""
        ...

    def set_doc(self, path: str, data: dict) -> None:
        """Create-or-replace the doc at `path` with `data`."""
        ...

    def set_doc_merge(self, path: str, data: dict) -> None:
        """Create-or-merge: existing fields not present in `data` are kept."""
        cur = self.get_doc(path) or {}
        cur.update(data)
        self.set_doc(path, cur)

    def update_doc(self, path: str, fields: dict) -> None:
        """Merge `fields` into the existing doc at `path`. Raises NotFound."""
        ...

    def delete_doc(self, path: str) -> bool:
        """Delete the doc at `path`. Returns True if it existed."""
        ...

    def list_collection(self, path: str) -> list[tuple[str, dict]]:
        """Return [(doc_id, data), ...] for direct children of `path`.

        `path` is a collection path (odd number of segments).
        """
        ...

    # --- blobs ---------------------------------------------------------------

    def put_blob(self, path: str, content: bytes | str) -> None:
        """Create-or-replace the blob at `path`."""
        ...

    def get_blob(self, path: str) -> bytes | None:
        """Return blob bytes at `path` or None if it does not exist."""
        ...

    def delete_blob(self, path: str) -> bool:
        """Delete the blob at `path`. Returns True if it existed."""
        ...

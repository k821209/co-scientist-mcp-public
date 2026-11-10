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


class CollectionWatch(Protocol):
    """What `watch_collection` hands back."""

    @property
    def alive(self) -> bool: ...

    def close(self) -> None: ...


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

    def query_collection(self, path: str, field: str, value,
                         op: str = "==") -> list[tuple[str, dict]]:
        """[(doc_id, data), ...] for children of `path` where `field op value`.

        Distinct from list_collection because the top-level `projects`
        collection is NOT listable: the security rule grants a project only to
        its owner, so an unfiltered stream is denied outright. The filter is
        what makes the query satisfiable, not merely tidier.

        `op` is a Firestore comparison — "==" or ">" are the ones in use. ">"
        exists so a caller can ask for what is NEW rather than reading a
        collection it has already read: the control-page poller was reading
        every message of the session again twice a second, which is 98% of this
        project's Firestore bill (measured 2026-10-10)."""
        ...

    def watch_collection(self, path: str, on_change) -> "CollectionWatch":
        """Be TOLD when a collection changes, instead of asking.

        `on_change(changes)` is called — from another thread — with
        `[(kind, doc_id, data), ...]`, kind in ADDED / MODIFIED / REMOVED;
        the first call carries every existing document as ADDED. The handle's
        `alive` says whether changes can still arrive, and `close()` stops it.

        This exists because asking is billed and being told is not. The
        control page's session side could only poll: six reads a time, twice a
        second, per session, for as long as the process lived — 34 million
        reads a day across 22 sessions that were mostly waiting for nobody
        (measured 2026-11-10). A listener is billed for the documents that
        change and nothing while they do not."""
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

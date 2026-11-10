"""In-memory backend used by tests and offline development.

Stores docs in a flat dict keyed by full path. Collection listing scans for
keys with the given prefix and exactly one more path segment.
"""
from __future__ import annotations

import copy

from .base import Backend, NotFound


def _split(path: str) -> list[str]:
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        raise ValueError("empty path")
    return parts


class _MemoryWatch:
    """The in-memory listener, with the one failure the real one has: it can
    stop delivering without saying so (`break_silently`), which is the case
    every caller has to survive."""

    def __init__(self, backend, path: str, on_change) -> None:
        self._backend, self.path, self.on_change = backend, path, on_change
        self._alive = True

    @property
    def alive(self) -> bool:
        return self._alive

    def close(self) -> None:
        self._alive = False

    def break_silently(self) -> None:
        self._alive = False


class InMemoryBackend(Backend):
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}
        self._blobs: dict[str, bytes] = {}
        self._watches: list["_MemoryWatch"] = []

    # --- documents -----------------------------------------------------------

    def get_doc(self, path: str) -> dict | None:
        _split(path)  # validate
        doc = self._docs.get(path)
        return copy.deepcopy(doc) if doc is not None else None

    def set_doc(self, path: str, data: dict) -> None:
        parts = _split(path)
        if len(parts) % 2 != 0:
            raise ValueError(f"doc path must have even segments: {path!r}")
        kind = "MODIFIED" if path in self._docs else "ADDED"
        self._docs[path] = copy.deepcopy(data)
        self._tell(path, kind)

    def update_doc(self, path: str, fields: dict) -> None:
        existing = self._docs.get(path)
        if existing is None:
            raise NotFound(f"doc not found: {path!r}")
        existing.update(copy.deepcopy(fields))
        self._tell(path, "MODIFIED")

    def delete_doc(self, path: str) -> bool:
        existed = self._docs.pop(path, None) is not None
        if existed:
            self._tell(path, "REMOVED")
        return existed

    # --- being told ----------------------------------------------------------

    def watch_collection(self, path: str, on_change) -> "_MemoryWatch":
        watch = _MemoryWatch(self, path.strip("/"), on_change)
        self._watches.append(watch)
        on_change([("ADDED", doc_id, data) for doc_id, data in self.list_collection(path)])
        return watch

    def _tell(self, path: str, kind: str) -> None:
        collection, _, doc_id = path.strip("/").rpartition("/")
        for watch in list(self._watches):
            if watch.alive and watch.path == collection:
                watch.on_change([(kind, doc_id, copy.deepcopy(self._docs.get(path) or {}))])

    def query_collection(self, path: str, field: str, value,
                         op: str = "==") -> list[tuple[str, dict]]:
        def keep(have) -> bool:
            if op == "==":
                return have == value
            if have is None:
                return False      # Firestore skips documents missing the field
            try:
                return have > value if op == ">" else have >= value
            except TypeError:
                return False
            
        if op not in ("==", ">", ">="):
            raise ValueError(f"unsupported operator: {op!r}")
        return [(k, v) for k, v in self.list_collection(path) if keep(v.get(field))]

    def list_collection(self, path: str) -> list[tuple[str, dict]]:
        parts = _split(path)
        if len(parts) % 2 == 0:
            raise ValueError(f"collection path must have odd segments: {path!r}")
        prefix = path.strip("/") + "/"
        out: list[tuple[str, dict]] = []
        for k, v in self._docs.items():
            if not k.startswith(prefix):
                continue
            tail = k[len(prefix):]
            if "/" in tail:
                continue  # belongs to a sub-collection
            out.append((tail, copy.deepcopy(v)))
        out.sort(key=lambda kv: kv[0])
        return out

    # --- blobs ---------------------------------------------------------------

    def put_blob(self, path: str, content: bytes | str) -> None:
        _split(path)
        if isinstance(content, str):
            content = content.encode("utf-8")
        self._blobs[path] = content

    def get_blob(self, path: str) -> bytes | None:
        _split(path)
        return self._blobs.get(path)

    def delete_blob(self, path: str) -> bool:
        return self._blobs.pop(path, None) is not None

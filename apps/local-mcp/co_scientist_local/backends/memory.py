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


class InMemoryBackend(Backend):
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}
        self._blobs: dict[str, bytes] = {}

    # --- documents -----------------------------------------------------------

    def get_doc(self, path: str) -> dict | None:
        _split(path)  # validate
        doc = self._docs.get(path)
        return copy.deepcopy(doc) if doc is not None else None

    def set_doc(self, path: str, data: dict) -> None:
        parts = _split(path)
        if len(parts) % 2 != 0:
            raise ValueError(f"doc path must have even segments: {path!r}")
        self._docs[path] = copy.deepcopy(data)

    def update_doc(self, path: str, fields: dict) -> None:
        existing = self._docs.get(path)
        if existing is None:
            raise NotFound(f"doc not found: {path!r}")
        existing.update(copy.deepcopy(fields))

    def delete_doc(self, path: str) -> bool:
        return self._docs.pop(path, None) is not None

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

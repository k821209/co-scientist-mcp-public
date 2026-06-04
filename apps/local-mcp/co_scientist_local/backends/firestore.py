"""Firestore + Cloud Storage backend.

Two auth modes, same `Backend` interface:

1. **User-token mode** (preferred, multi-user): pass `user_token_provider`,
   a callable that returns a valid Firebase ID token.
     - Firestore: google.cloud.firestore.Client with OAuth2 user creds.
       Firestore's API endpoint accepts Firebase Auth ID tokens.
     - Storage: **Firebase Storage REST API** (firebasestorage.googleapis.com).
       The GCS API (storage.googleapis.com) does NOT accept Firebase Auth
       tokens, so we go through Firebase's own endpoint which applies
       Storage security rules.

2. **Service-account mode** (developer / smoke / admin): pass `credentials_path`
   or rely on Application Default Credentials. Uses firebase-admin SDK.
   Bypasses security rules.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .base import Backend, NotFound


# ──────────────────────────────────────────────────────────────────────────────
# Firebase Storage REST client (used in user-token mode)
# ──────────────────────────────────────────────────────────────────────────────


class _FirebaseStorageBucket:
    """Bucket-compatible wrapper that talks to firebasestorage.googleapis.com
    with a Firebase Auth ID token; security rules apply.

    Mirrors `google.cloud.storage.Bucket.blob(path).{upload_from_string,
    exists, download_as_bytes, delete}` — the only methods our FirestoreBackend
    uses.
    """

    def __init__(self, bucket_name: str, token_provider: Callable[[], str]) -> None:
        self._bucket = bucket_name
        self._token = token_provider

    def blob(self, path: str) -> "_FirebaseStorageBlob":
        return _FirebaseStorageBlob(self._bucket, path, self._token)


class _FirebaseStorageBlob:
    def __init__(self, bucket: str, path: str, token_provider: Callable[[], str]) -> None:
        self._bucket = bucket
        self._path = path
        self._token = token_provider

    def _object_url(self) -> str:
        # Object path is URL-encoded with slashes preserved as %2F
        encoded = urllib.parse.quote(self._path, safe="")
        return f"https://firebasestorage.googleapis.com/v0/b/{self._bucket}/o/{encoded}"

    def upload_from_string(
        self, content: bytes | str,
        content_type: str = "application/octet-stream",
    ) -> None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        encoded = urllib.parse.quote(self._path, safe="")
        url = (
            f"https://firebasestorage.googleapis.com/v0/b/{self._bucket}/o"
            f"?name={encoded}&uploadType=media"
        )
        req = urllib.request.Request(
            url, data=content, method="POST",
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": content_type,
            },
        )
        try:
            urllib.request.urlopen(req, timeout=60).read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Storage upload failed (HTTP {e.code}): {body}") from e

    def exists(self) -> bool:
        req = urllib.request.Request(
            self._object_url(), method="GET",
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            raise

    def download_as_bytes(self) -> bytes:
        url = self._object_url() + "?alt=media"
        req = urllib.request.Request(
            url, method="GET",
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    def delete(self) -> None:
        req = urllib.request.Request(
            self._object_url(), method="DELETE",
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise


# ──────────────────────────────────────────────────────────────────────────────
# OAuth2 user credentials wrapper for Firestore client
# ──────────────────────────────────────────────────────────────────────────────


def _build_user_credentials(token_provider: Callable[[], str]):
    """Wrap a token-fetcher callable as a google.auth.credentials.Credentials.

    The wrapper's `refresh()` re-asks the provider for a fresh token; the
    provider (FirebaseAuthClient.get_id_token) handles expiry caching itself.
    """
    from google.oauth2 import credentials as gauth

    class _ProviderCredentials(gauth.Credentials):
        def __init__(self, provider: Callable[[], str]) -> None:
            super().__init__(token=provider())
            self._provider = provider

        @property
        def expired(self) -> bool:
            # ALWAYS report expired so google-auth calls refresh() before
            # every request. refresh() then asks the provider
            # (FirebaseAuthClient.get_id_token), which is itself cached —
            # it only does a network round-trip when the ID token is
            # actually near expiry, otherwise returns the cached token
            # instantly. So this is cheap per request.
            #
            # The previous value (False) was the bug: google-auth saw the
            # credential as permanently valid, never called refresh(), and
            # the Firestore client kept sending the construction-time token.
            # After ~1h that token expired and every call 401'd until the
            # process restarted.
            return True

        def refresh(self, request) -> None:  # noqa: ARG002
            self.token = self._provider()

    return _ProviderCredentials(token_provider)


# ──────────────────────────────────────────────────────────────────────────────
# FirestoreBackend
# ──────────────────────────────────────────────────────────────────────────────


class FirestoreBackend(Backend):
    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        *,
        credentials_path: str | None = None,
        user_token_provider: Callable[[], str] | None = None,
        app_name: str = "co-scientist-local",
    ) -> None:
        if user_token_provider is not None:
            # --- User-token mode -----------------------------------------
            from google.cloud import firestore as gcf
            creds = _build_user_credentials(user_token_provider)
            self._db = gcf.Client(project=project_id, credentials=creds)
            self._bucket = _FirebaseStorageBucket(bucket_name, user_token_provider)
        else:
            # --- Service-account mode ------------------------------------
            import firebase_admin
            from firebase_admin import credentials as fb_credentials
            from firebase_admin import firestore, storage

            if app_name in firebase_admin._apps:
                app = firebase_admin.get_app(app_name)
            else:
                if credentials_path:
                    cred = fb_credentials.Certificate(credentials_path)
                else:
                    cred = fb_credentials.ApplicationDefault()
                app = firebase_admin.initialize_app(
                    cred,
                    {"projectId": project_id, "storageBucket": bucket_name},
                    name=app_name,
                )
            self._app = app
            self._db = firestore.client(app=app)
            self._bucket = storage.bucket(name=bucket_name, app=app)

    # --- documents -----------------------------------------------------------

    def get_doc(self, path: str) -> dict | None:
        snap = self._db.document(path).get()
        return snap.to_dict() if snap.exists else None

    def set_doc(self, path: str, data: dict) -> None:
        self._db.document(path).set(data)

    def set_doc_merge(self, path: str, data: dict) -> None:
        self._db.document(path).set(data, merge=True)

    def update_doc(self, path: str, fields: dict) -> None:
        from google.api_core import exceptions as gax_exc
        try:
            self._db.document(path).update(fields)
        except gax_exc.NotFound as e:
            raise NotFound(f"doc not found: {path!r}") from e

    def delete_doc(self, path: str) -> bool:
        ref = self._db.document(path)
        snap = ref.get()
        if not snap.exists:
            return False
        ref.delete()
        return True

    def list_collection(self, path: str) -> list[tuple[str, dict]]:
        col = self._db.collection(path)
        out: list[tuple[str, dict]] = []
        for snap in col.stream():
            out.append((snap.id, snap.to_dict() or {}))
        out.sort(key=lambda kv: kv[0])
        return out

    # --- blobs ---------------------------------------------------------------

    def put_blob(self, path: str, content: bytes | str) -> None:
        blob = self._bucket.blob(path)
        if isinstance(content, str):
            blob.upload_from_string(content, content_type="text/markdown")
        else:
            blob.upload_from_string(content)

    def get_blob(self, path: str) -> bytes | None:
        blob = self._bucket.blob(path)
        if not blob.exists():
            return None
        return blob.download_as_bytes()

    def delete_blob(self, path: str) -> bool:
        blob = self._bucket.blob(path)
        if not blob.exists():
            return False
        blob.delete()
        return True

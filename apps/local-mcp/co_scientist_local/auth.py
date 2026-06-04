"""Firebase Auth for the local MCP.

Three pieces:

1. **TokenRefresher** — refresh_token → id_token via securetoken.googleapis.com.
   Used by `FirebaseAuthClient` for ongoing token renewal.

2. **CustomTokenSignIn** — customToken → idToken + refreshToken via
   identitytoolkit.googleapis.com. Bootstrap step that consumes the
   custom token minted by the /exchange_key Cloud Function.

3. **exchange_api_key** — calls our /exchange_key Cloud Function with the
   per-project API key, gets back a customToken + project/owner ids.

End-to-end MCP startup flow:
    api_key  ──exchange_api_key──►  customToken  ──CustomTokenSignIn──►  idToken
                                                                              │
                                                                              ▼
                                                       FirebaseAuthClient(refresh_token)
                                                              │
                                                              ▼
                                                       refreshed idToken every ~55min,
                                                       used for all Firestore + Storage
                                                       writes (security rules apply).

The web_api_key is NOT a secret — it identifies the Firebase project to client
SDKs and ships in every frontend bundle.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol


def _log(msg: str) -> None:
    """Surface auth events to stderr so a silent refresh failure is
    distinguishable from a code/permission bug."""
    print(f"co-scientist-local auth: {msg}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────────────
# /exchange_key call
# ──────────────────────────────────────────────────────────────────────────────


class ExchangeKeyError(Exception):
    """Raised when /exchange_key returns non-2xx."""


def _http_post_json(url: str, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = {"error": f"http {e.code}"}
        return e.code, payload


def exchange_api_key(
    *,
    api_key: str,
    exchange_url: str,
    poster: Callable[[str, dict, dict | None], tuple[int, dict]] | None = None,
) -> dict:
    """POST to /exchange_key. Returns {customToken, projectId, ownerUid}."""
    if not api_key:
        raise ValueError("api_key is required")
    if not exchange_url:
        raise ValueError("exchange_url is required")
    post = poster or _http_post_json
    status, body = post(exchange_url, {}, {"Authorization": f"Bearer {api_key}"})
    if status != 200:
        msg = body.get("error") or f"http {status}"
        raise ExchangeKeyError(msg)
    for field in ("customToken", "projectId", "ownerUid"):
        if field not in body:
            raise ExchangeKeyError(f"response missing {field!r}: {body!r}")
    return body


# ──────────────────────────────────────────────────────────────────────────────
# customToken → idToken (Identity Toolkit)
# ──────────────────────────────────────────────────────────────────────────────


class CustomTokenSignIn(Protocol):
    def sign_in(self, custom_token: str, web_api_key: str) -> dict:
        """Returns {idToken, refreshToken, expiresIn} (Identity Toolkit shape)."""
        ...


class HttpCustomTokenSignIn:
    URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"

    def sign_in(self, custom_token: str, web_api_key: str) -> dict:
        status, body = _http_post_json(
            f"{self.URL}?key={web_api_key}",
            {"token": custom_token, "returnSecureToken": True},
        )
        if status != 200:
            raise ExchangeKeyError(
                f"signInWithCustomToken failed: {body.get('error', f'http {status}')}"
            )
        return body


class FakeCustomTokenSignIn:
    """Test impl: returns canned id_token / refresh_token."""
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0
        self._expires_in = 3600

    def set_expires_in(self, seconds: int) -> None:
        self._expires_in = seconds

    def sign_in(self, custom_token: str, web_api_key: str) -> dict:
        self._counter += 1
        self.calls.append({"custom_token": custom_token, "web_api_key": web_api_key})
        return {
            "idToken": f"fake-id-{self._counter}",
            "refreshToken": f"fake-refresh-{self._counter}",
            "expiresIn": str(self._expires_in),
        }


# ──────────────────────────────────────────────────────────────────────────────
# refresh_token → id_token (caching client)
# ──────────────────────────────────────────────────────────────────────────────


class TokenRefresher(Protocol):
    def refresh(self, refresh_token: str, web_api_key: str) -> dict:
        """Exchange a refresh_token for an id_token.

        Returns a dict with keys at least: id_token, expires_in (str/int).
        """
        ...


class HttpTokenRefresher:
    BASE_URL = "https://securetoken.googleapis.com/v1/token"
    # Retry transient failures (5xx, network blips) — securetoken hiccups
    # usually clear within a second. 4xx (bad/expired refresh token) is
    # NOT retried; it won't fix itself.
    MAX_ATTEMPTS = 3
    BACKOFF_SECONDS = (0.5, 1.0, 2.0)

    def refresh(self, refresh_token: str, web_api_key: str) -> dict:
        from urllib.parse import urlencode

        url = f"{self.BASE_URL}?key={web_api_key}"
        data = urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode()
        last_err: Exception | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    # Permanent — bad/expired refresh token, etc.
                    try:
                        payload = json.loads(e.read())
                    except Exception:
                        payload = {"error": f"http {e.code}"}
                    raise RuntimeError(f"token refresh failed: {payload}") from e
                last_err = e  # 5xx — retryable
            except urllib.error.URLError as e:
                last_err = e  # network blip — retryable
            if attempt < self.MAX_ATTEMPTS - 1:
                _log(
                    f"token refresh attempt {attempt + 1}/{self.MAX_ATTEMPTS} "
                    f"failed ({last_err}); retrying"
                )
                time.sleep(self.BACKOFF_SECONDS[attempt])
        raise RuntimeError(
            f"token refresh failed after {self.MAX_ATTEMPTS} attempts: {last_err}"
        )


class FakeTokenRefresher:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._counter = 0
        self._expires_in = 3600
        self._fail_next = False
        self._rotate_refresh = False

    def set_expires_in(self, seconds: int) -> None:
        self._expires_in = seconds

    def fail_next(self) -> None:
        self._fail_next = True

    def rotate_refresh_token(self) -> None:
        self._rotate_refresh = True

    def refresh(self, refresh_token: str, web_api_key: str) -> dict:
        if self._fail_next:
            self._fail_next = False
            raise RuntimeError("simulated token refresh failure")
        self._counter += 1
        self.calls.append({"refresh_token": refresh_token, "web_api_key": web_api_key})
        out = {
            "id_token": f"fake-id-{self._counter}",
            "expires_in": str(self._expires_in),
        }
        if self._rotate_refresh:
            out["refresh_token"] = f"rotated-refresh-{self._counter}"
            self._rotate_refresh = False
        return out


class FirebaseAuthClient:
    """Caches an ID token until it's near expiry, then refreshes.

    Optionally seeded with an initial token (from CustomTokenSignIn) so the
    very first get_id_token() doesn't have to hit the network.
    """

    REFRESH_LEAD_SECONDS = 60

    def __init__(
        self,
        *,
        web_api_key: str,
        refresh_token: str,
        refresher: TokenRefresher | None = None,
        now_fn=None,
        initial_id_token: str | None = None,
        initial_expires_in: int | None = None,
    ) -> None:
        if not web_api_key:
            raise ValueError("web_api_key is required")
        if not refresh_token:
            raise ValueError("refresh_token is required")
        self._web_api_key = web_api_key
        self._refresh_token = refresh_token
        self._refresher = refresher or HttpTokenRefresher()
        self._now = now_fn or time.time
        self._id_token: str | None = initial_id_token
        self._expiry_epoch: float = (
            self._now() + int(initial_expires_in)
            if initial_id_token and initial_expires_in
            else 0.0
        )

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    def get_id_token(self) -> str:
        now = self._now()
        if self._id_token is None or now >= self._expiry_epoch - self.REFRESH_LEAD_SECONDS:
            resp = self._refresher.refresh(self._refresh_token, self._web_api_key)
            self._id_token = resp["id_token"]
            try:
                ttl = int(resp.get("expires_in", 3600))
            except (TypeError, ValueError):
                ttl = 3600
            self._expiry_epoch = now + ttl
            new_refresh = resp.get("refresh_token")
            if new_refresh:
                self._refresh_token = new_refresh
        return self._id_token

    def invalidate(self) -> None:
        self._id_token = None
        self._expiry_epoch = 0.0

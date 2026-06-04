"""Firebase email+password sign-in.

POSTs to identitytoolkit (the same endpoint the web SDK uses) to exchange
credentials for an idToken + refreshToken. The refreshToken is what the
local MCP stores in ~/.co-scientist/config.toml; subsequent calls go
through auth.py (in the local MCP package) to refresh ID tokens on demand.

Uses urllib so the CLI has no third-party runtime deps. The HTTP layer is
injectable for tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable


class SignInError(Exception):
    """Raised when Firebase returns a non-2xx for sign-in."""


SIGNIN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"


class _Response:
    __slots__ = ("status_code", "_body")
    def __init__(self, status_code: int, body: bytes | str) -> None:
        self.status_code = status_code
        self._body = body
    def json(self) -> dict:
        if isinstance(self._body, bytes):
            return json.loads(self._body.decode("utf-8"))
        return json.loads(self._body)


HttpPost = Callable[[str, dict], _Response]


def _real_http_post(url: str, body: dict) -> _Response:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _Response(resp.status, resp.read())
    except urllib.error.HTTPError as e:
        return _Response(e.code, e.read())


def sign_in_email_password(
    *,
    email: str,
    password: str,
    web_api_key: str,
    http_post: HttpPost | None = None,
) -> dict:
    """Sign in to Firebase Auth and return the parsed response.

    On success, the response includes localId (uid), idToken, refreshToken,
    expiresIn, email, displayName.
    """
    if not email or not password or not web_api_key:
        raise ValueError("email, password, and web_api_key are all required")
    post = http_post or _real_http_post
    resp = post(
        f"{SIGNIN_URL}?key={web_api_key}",
        {"email": email, "password": password, "returnSecureToken": True},
    )
    body = resp.json()
    if resp.status_code != 200:
        msg = (body.get("error") or {}).get("message") or f"http {resp.status_code}"
        raise SignInError(msg)
    return body

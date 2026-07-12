"""Account-wide integration secrets — one store per USER, shared across all of
their projects, readable only by them.

Lives at `users/{uid}/secrets/{key}` (Firestore rule: owner-only). The MCP
authenticates as the project owner, so it reads/writes the signed-in user's own
secrets regardless of which project the session is in — set a token once (e.g.
`zenodo_token`) and every project on every machine can use it, without putting
it in git or a project doc.

Not for project-scoped data — that's project memory / settings. This is for the
user's cross-project credentials.
"""
from __future__ import annotations

from ..state import State
from ..util import now_iso


def _secret_path(state: State, key: str) -> str:
    return f"users/{state.owner_uid}/secrets/{key}"


def _norm_key(key: str) -> str:
    k = (key or "").strip()
    if not k or "/" in k:
        raise ValueError("secret key must be non-empty and contain no '/'")
    return k


def set_user_secret(state: State, key: str, value: str) -> dict:
    """Store (or replace) an account-wide secret for the signed-in user. Prefer
    setting secrets in the dashboard (Account tab) so the value isn't pasted into
    a chat transcript."""
    key = _norm_key(key)
    if value is None or value == "":
        raise ValueError("value is required")
    state.backend.set_doc(_secret_path(state, key), {
        "key": key, "value": value, "updated_at": now_iso(),
    })
    return {"key": key, "set": True}


def get_user_secret(state: State, key: str) -> str | None:
    """Return the secret's value (for use at call time), or None if unset."""
    doc = state.backend.get_doc(_secret_path(state, _norm_key(key)))
    return doc.get("value") if doc else None


def list_user_secrets(state: State) -> list[dict]:
    """List secret keys the user has stored — NAMES + updated_at only, never the
    values (so a listing can't leak them)."""
    pairs = state.backend.list_collection(f"users/{state.owner_uid}/secrets")
    out = [{"key": data.get("key", cid), "updated_at": data.get("updated_at")}
           for cid, data in pairs]
    out.sort(key=lambda s: s["key"])
    return out


def delete_user_secret(state: State, key: str) -> bool:
    """Delete an account-wide secret. Returns whether it existed."""
    path = _secret_path(state, _norm_key(key))
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

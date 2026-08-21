"""Publish a page at an unlisted URL, optionally behind passcodes.

    doc: projects/{pid}/publications/{pub_id}
    doc: projects/{pid}/publications/{pub_id}/passcodes/{code_id}
    doc: projects/{pid}/publications/{pub_id}/{collection}/{doc_id}   ← the page's data

The audience is people with no dashboard account: an external reviewer, a
collaborator at another institute. They get a link; the link is the secret.

Three things this module is careful about.

**A passcode is stored as a hash, never as itself.** The dashboard shows a code
exactly once, at creation. If codes were readable, anyone who could read the
project could impersonate any reviewer — and impersonation is the one thing the
codes exist to prevent, because WHICH code was used is how responses are
attributed to a person.

**Attribution is server-side.** The code's label rides in the minted token as a
claim, and the security rules require a response's `reviewer` field to equal it.
A page cannot write a response as somebody else, however it is edited.

**Unpublishing is instant and total.** `active: false` is checked when the token
is minted, so revoking a link stops the next visitor even though links already
handed out cannot be recalled.
"""
from __future__ import annotations

import hashlib
import secrets

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

# PBKDF2-HMAC-SHA256. The verifier in the Cloud Function uses these same
# numbers; changing one without the other silently locks every existing code
# out, so they are named here and referenced there.
PBKDF2_ROUNDS = 200_000
SALT_BYTES = 16
# Human-typed, so no look-alikes: no O/0, I/l/1.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 10


def hash_passcode(code: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", code.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS,
    ).hex()


def generate_passcode() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(CODE_LEN))


def _pub_path(state: State, pub_id: str) -> str:
    return state.project_path("publications", pub_id)


def _code_path(state: State, pub_id: str, code_id: str) -> str:
    return state.project_path("publications", pub_id, "passcodes", code_id)


def _require(state: State, pub_id: str) -> dict:
    doc = state.backend.get_doc(_pub_path(state, pub_id))
    if doc is None:
        raise NotFound(f"publication {pub_id!r} not found")
    return doc


def publish_page(
    state: State,
    *,
    title: str,
    html: str | None = None,
    material_id: str | None = None,
    require_passcode: bool = True,
    description: str | None = None,
) -> dict:
    """Publish a page and return its unlisted URL.

    Give either `html` (the page source) or `material_id` (an HTML material
    already uploaded). `require_passcode=True` is the default on purpose: a
    link with no gate is one forwarded email away from being public, and the
    default should be the safe one, not the convenient one.
    """
    if not (title or "").strip():
        raise ValueError("title is required")
    if bool(html) == bool(material_id):
        raise ValueError("give exactly one of html= or material_id=")

    body = html
    if material_id:
        from . import materials as _materials
        doc = state.backend.get_doc(
            state.project_path("materials", material_id))
        if doc is None:
            raise NotFound(f"material {material_id!r} not found")
        blob = state.backend.get_blob(doc.get("blob_path") or "")
        if blob is None:
            raise NotFound(f"material {material_id!r} has no stored file")
        body = blob.decode("utf-8", errors="replace")
        del _materials

    pub_id = new_id()
    now = now_iso()
    state.backend.put_blob(
        state.project_path("publications", pub_id, "page.html"),
        (body or "").encode("utf-8"),
    )
    doc = {
        "pub_id": pub_id,
        "title": title.strip(),
        "description": (description or "").strip() or None,
        "active": True,
        "require_passcode": bool(require_passcode),
        "source_material_id": material_id,
        "blob_path": state.project_path("publications", pub_id, "page.html"),
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(_pub_path(state, pub_id), doc)
    return {**doc, "url": _public_url(state, pub_id)}


def _public_url(state: State, pub_id: str) -> str:
    from ..state import DASHBOARD_BASE_URL
    return f"{DASHBOARD_BASE_URL}/p/{state.project_id}/{pub_id}"


def update_publication(
    state: State,
    pub_id: str,
    *,
    html: str | None = None,
    title: str | None = None,
    active: bool | None = None,
    require_passcode: bool | None = None,
) -> dict:
    """Amend a publication. `active=False` unpublishes it."""
    doc = _require(state, pub_id)
    fields: dict = {"updated_at": now_iso()}
    if title is not None:
        fields["title"] = title.strip()
    if active is not None:
        fields["active"] = bool(active)
    if require_passcode is not None:
        fields["require_passcode"] = bool(require_passcode)
    if html is not None:
        state.backend.put_blob(doc["blob_path"], html.encode("utf-8"))
    state.backend.update_doc(_pub_path(state, pub_id), fields)
    return {**doc, **fields, "url": _public_url(state, pub_id)}


def list_publications(state: State) -> list[dict]:
    """Every published page in this project, newest first."""
    rows = [d for _, d in state.backend.list_collection(
        state.project_path("publications"))]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return [{**r, "url": _public_url(state, r.get("pub_id", ""))} for r in rows]


# ─────────────────────────── passcodes ───────────────────────────


def add_passcode(state: State, pub_id: str, *, label: str) -> dict:
    """Issue a passcode for one person, and return it ONCE.

    `label` is how their responses are attributed — a name, an initial, a role.
    It is written into the token when they sign in and the rules require it to
    match what a response claims, so two reviewers can never be confused for
    each other and neither can write as the other.

    The plaintext is in this return value and nowhere else. It is not stored,
    so it cannot be recovered: if it is lost, revoke and issue another."""
    _require(state, pub_id)
    text = (label or "").strip()
    if not text:
        raise ValueError("label is required — it is how responses are attributed")
    existing = list_passcodes(state, pub_id)
    if any(c["label"] == text and c.get("active") for c in existing):
        raise ValueError(
            f"an active passcode is already labelled {text!r} — two codes with "
            "one label would make responses ambiguous"
        )
    code = generate_passcode()
    salt = secrets.token_hex(SALT_BYTES)
    code_id = new_id()
    state.backend.set_doc(_code_path(state, pub_id, code_id), {
        "code_id": code_id,
        "label": text,
        "salt": salt,
        "hash": hash_passcode(code, salt),
        "rounds": PBKDF2_ROUNDS,
        "active": True,
        "use_count": 0,
        "last_used_at": None,
        "created_at": now_iso(),
    })
    return {
        "code_id": code_id,
        "label": text,
        "passcode": code,
        "url": _public_url(state, pub_id),
        "note": "shown once — it is stored only as a hash and cannot be recovered",
    }


def list_passcodes(state: State, pub_id: str) -> list[dict]:
    """Issued passcodes — labels and usage, never the codes themselves."""
    _require(state, pub_id)
    rows = [d for _, d in state.backend.list_collection(
        state.project_path("publications", pub_id, "passcodes"))]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return [{k: v for k, v in r.items() if k not in ("hash", "salt")} for r in rows]


def revoke_passcode(state: State, pub_id: str, code_id: str) -> dict:
    """Deactivate one passcode. The responses it produced are kept — the person
    stops getting in; what they already judged is evidence."""
    if state.backend.get_doc(_code_path(state, pub_id, code_id)) is None:
        raise NotFound(f"passcode {code_id!r} not found")
    state.backend.update_doc(_code_path(state, pub_id, code_id), {
        "active": False, "revoked_at": now_iso(),
    })
    return {"code_id": code_id, "active": False}


# ─────────────────────────── responses ───────────────────────────


def list_responses(
    state: State, pub_id: str, *, collection: str = "responses",
) -> list[dict]:
    """What the published page has written back, oldest first.

    Each carries the `reviewer` label of the passcode used, enforced at write
    time by the rules — so two independent reviewers' judgements can be split
    apart and compared without trusting anything the page said about itself."""
    _require(state, pub_id)
    rows = [d for _, d in state.backend.list_collection(
        state.project_path("publications", pub_id, collection))]
    rows.sort(key=lambda r: r.get("created_at") or r.get("updated_at") or "")
    return rows


def put_page_data(
    state: State, pub_id: str, *, collection: str, doc_id: str, data: dict,
) -> dict:
    """Write a document the published page will READ (the items to review).

    Anything under a publication is published — that is the whole rule, and it
    is why the page's data lives here rather than being granted piecemeal out of
    the project."""
    _require(state, pub_id)
    if collection in ("passcodes",):
        raise ValueError("passcodes are not writable this way")
    payload = {**data, "updated_at": now_iso()}
    state.backend.set_doc(
        state.project_path("publications", pub_id, collection, doc_id), payload)
    return {"collection": collection, "doc_id": doc_id, **payload}

"""Papers other people shared with this account, read from a session.

A manuscript author can link a co-author to a Scivo account; once the invite is
accepted the paper shows up on that account's Projects page under "Shared with
me" and opens in the `/shared/{pid}/{slug}/{shareId}` reader. All of that was
browser-only, so a session could not read a paper a collaborator had shared —
the obvious thing to want when they ask you to look at it (user, 2026-10-11).

The grant this uses is the one that already exists, not a wider one:

  - `users/{uid}/shared_papers` is readable by that user, and the MCP signs in
    as the account that owns its project (exchange_key mints the custom token
    with `owner_uid`), so this side can list what it was given.
  - `/exchange_share_token` turns a shareId into a token whose claim is
    `share_paper = "{pid}/{slug}"`. A co-author share carries `bound_uid`, and
    the function refuses it unless the caller proves with an ID token that they
    ARE that uid — so the link is not forwardable and this is not a way around
    anything.
  - The rules then open exactly six things for that claim: the paper document,
    its sections, figures, tables, references and exports, plus its comments.
    Not the project's servers, memory, materials or other papers. "Read-only,
    that paper only" is the rule's own shape, not something enforced here.

Comments can be CREATED by a share holder (`source: external`, `status: open`)
and that is deliberately not exposed: leaving remarks on someone else's
manuscript is a thing to do on purpose, from a tool that says so.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..backends.base import NotFound
from ..state import State

EXCHANGE_URL_TEMPLATE = (
    "https://us-central1-{project_id}.cloudfunctions.net/exchange_share_token"
)
_READ_URL = ("https://firestore.googleapis.com/v1/projects/{project}/databases/"
             "(default)/documents/{path}")
# What the rules open to a share claim, and therefore all this reads.
SHARED_COLLECTIONS = ("sections", "figures", "tables", "references", "exports", "reviews")


def _shared_path(state: State, key: str | None = None) -> str:
    base = f"users/{state.owner_uid}/shared_papers"
    return f"{base}/{key}" if key else base


def list_shared_papers(state: State, *, include_pending: bool = False) -> list[dict]:
    """Papers other accounts have shared with this one.

    Accepted invitations only, unless `include_pending`. Each row says where
    the paper lives and who owns it, which is what `read_shared_paper` needs.
    """
    rows = []
    for key, doc in state.backend.list_collection(_shared_path(state)):
        status = doc.get("status") or "accepted"
        if status != "accepted" and not include_pending:
            continue
        rows.append({
            "key": key,
            "pid": doc.get("pid"),
            "slug": doc.get("slug"),
            "paper_title": doc.get("paper_title"),
            "project_name": doc.get("project_name"),
            "owner_name": doc.get("owner_name"),
            "status": status,
            "scope": doc.get("scope"),
            "invited_at": doc.get("invited_at"),
            "responded_at": doc.get("responded_at"),
        })
    rows.sort(key=lambda r: r.get("responded_at") or r.get("invited_at") or "")
    return rows


def _find_share(state: State, pid: str, slug: str) -> dict:
    for _key, doc in state.backend.list_collection(_shared_path(state)):
        if doc.get("pid") == pid and doc.get("slug") == slug:
            return doc
    raise NotFound(
        f"no paper shared with this account at {pid}/{slug} — "
        "list_shared_papers() shows what there is. If a colleague just sent an "
        "invitation, it has to be accepted in the dashboard first.")


def _share_identity(state: State, pid: str, slug: str, share_id: str) -> str:
    """An ID token scoped to this one shared paper.

    Two hops, the same two the browser makes: our Cloud Function checks the
    share and mints a custom token, then Firebase turns that into an ID token.
    The Authorization header on the first hop is THIS account's own token —
    a co-author share is addressed to a uid and the function will not mint
    anything for a caller who cannot show it is that person.
    """
    from .. import auth as _auth
    from ..constants import DEFAULT_FIREBASE_WEB_API_KEY
    import os

    if state.get_id_token is None:
        raise RuntimeError(
            "this session has no account token, so it cannot open a shared paper — "
            "it is running on a service account or in-memory backend rather than "
            "through the usual API-key sign-in")
    fb_project = os.environ.get("FIREBASE_PROJECT_ID", "co-scientist-5af1a")
    status, body = _auth._http_post_json(
        EXCHANGE_URL_TEMPLATE.format(project_id=fb_project),
        {"pid": pid, "slug": slug, "shareId": share_id},
        {"Authorization": f"Bearer {state.get_id_token()}"},
    )
    if status != 200 or not body.get("customToken"):
        raise RuntimeError(
            f"the share link for {pid}/{slug} was refused: "
            f"{body.get('error') or f'http {status}'}")
    web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", DEFAULT_FIREBASE_WEB_API_KEY)
    signed = _auth.HttpCustomTokenSignIn().sign_in(body["customToken"], web_api_key)
    return signed["idToken"]


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise RuntimeError(f"reading the shared paper failed: http {e.code}") from e


def _plain(value: dict):
    """One Firestore REST value as an ordinary Python one."""
    for key in ("stringValue", "booleanValue", "timestampValue"):
        if key in value:
            return value[key]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "nullValue" in value:
        return None
    if "arrayValue" in value:
        return [_plain(v) for v in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {k: _plain(v) for k, v in value["mapValue"].get("fields", {}).items()}
    return value


def _doc(raw: dict) -> dict:
    return {k: _plain(v) for k, v in (raw.get("fields") or {}).items()}


def read_shared_paper(
    state: State, pid: str, slug: str, *, include_comments: bool = True,
) -> dict:
    """Read a paper another account shared with this one.

    Returns the paper document, its sections in order, and its figures, tables
    and references — the six things the share grant opens, and nothing else.
    `include_comments` adds the review thread, which is usually the point when
    a colleague asks you to look at a draft.
    """
    import os
    share = _find_share(state, pid, slug)
    share_id = share.get("share_id")
    if not share_id:
        raise NotFound(f"the share record for {pid}/{slug} carries no share_id")
    if (share.get("status") or "accepted") != "accepted":
        raise RuntimeError(
            f"the invitation for {pid}/{slug} is {share.get('status')!r} — "
            "accept it in the dashboard first")
    token = _share_identity(state, pid, slug, share_id)
    fb_project = os.environ.get("FIREBASE_PROJECT_ID", "co-scientist-5af1a")
    base = f"projects/{pid}/papers/{slug}"
    url = lambda path: _READ_URL.format(project=fb_project, path=path)  # noqa: E731

    paper = _doc(_get(url(base), token))
    out: dict = {
        "pid": pid, "slug": slug,
        "paper": paper,
        "shared_by": share.get("owner_name") or share.get("owner_uid"),
        "project_name": share.get("project_name"),
        # Said plainly because a session reading someone else's manuscript
        # should not try to edit it and then report a permission error: the
        # grant is read-only by construction.
        "access": "read-only; this account was given this one paper",
    }
    wanted = SHARED_COLLECTIONS if include_comments else \
        tuple(c for c in SHARED_COLLECTIONS if c != "reviews")
    for collection in wanted:
        docs = _get(url(f"{base}/{collection}"), token).get("documents", [])
        rows = [{"id": d["name"].rsplit("/", 1)[-1], **_doc(d)} for d in docs]
        if collection == "sections":
            rows.sort(key=lambda r: r.get("sort_order", 999))
        elif collection == "figures":
            rows.sort(key=lambda r: r.get("figure_number", 0))
        elif collection == "tables":
            rows.sort(key=lambda r: r.get("table_number", 0))
        out[collection] = rows
    return out

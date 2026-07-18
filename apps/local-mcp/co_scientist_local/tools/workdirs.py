"""Per-project working directories on registered servers.

The account server registry (`users/{uid}/servers`) describes the *machines*.
A project binds, per server it uses, the directory where THIS project's work
lives — plus a description of what's in it — at:

    projects/{pid}/server_workdirs/{server_alias}

This is the link between the account-wide server registry and project-specific
analysis provenance: `submit_remote_job` uses the project binding as the base
directory (falling back to the server's `default_workdir`), so each project's
runs land in — and are documented against — a clearly-described location.
"""
from __future__ import annotations

from ..state import State
from ..util import now_iso


def _wd_col(state: State) -> str:
    return state.project_path("server_workdirs")


def _wd_path(state: State, alias: str) -> str:
    a = (alias or "").strip()
    if not a or "/" in a:
        raise ValueError("server alias must be non-empty and contain no '/'")
    return state.project_path("server_workdirs", a)


def set_project_workdir(state: State, server_alias: str, workdir: str,
                        description: str = "", env_name: str = "") -> dict:
    """Bind (or update) how this project uses `server_alias`: `workdir` is the
    absolute path on that server where the project's data/code/outputs live,
    `description` says what's in it, and `env_name` is the conda/venv/module
    environment this project uses there (submit_remote_job activates it by
    default). Returns the binding doc."""
    path = _wd_path(state, server_alias)
    if not (workdir or "").strip():
        raise ValueError("workdir is required")
    now = now_iso()
    existing = state.backend.get_doc(path) or {}
    doc = {
        "server_alias": server_alias.strip(),
        "workdir": workdir.strip(),
        "description": (description or "").strip(),
        "env_name": (env_name or "").strip(),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def get_project_workdir(state: State, server_alias: str) -> dict | None:
    """This project's working-directory binding for `server_alias`, or None."""
    return state.backend.get_doc(_wd_path(state, server_alias))


def list_project_workdirs(state: State) -> list[dict]:
    """All of this project's server working-directory bindings, by alias."""
    out = [{"server_alias": aid, **data}
           for aid, data in state.backend.list_collection(_wd_col(state))]
    out.sort(key=lambda w: w.get("server_alias", ""))
    return out


def delete_project_workdir(state: State, server_alias: str) -> bool:
    """Remove this project's working-directory binding for `server_alias`."""
    path = _wd_path(state, server_alias)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

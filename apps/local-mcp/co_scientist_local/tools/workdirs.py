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


def project_slug(state: State) -> str:
    """The project's directory name on a server: its name, slugified; the id
    when the name has no letters or cannot be read."""
    from ..util import slugify
    try:
        proj = state.backend.get_doc(f"projects/{state.project_id}") or {}
    except Exception:
        proj = {}
    return slugify(proj.get("name") or "") or state.project_id


def project_root(state: State, server: dict) -> dict:
    """Where THIS project's work lives on `server` — the one rule for remote
    directories (feedback: work on servers was landing in folders made up on
    the spot, with no project in the path).

    An explicit binding (`set_project_workdir`) wins. Otherwise the root is
    `<server.default_workdir>/<project-slug>`, so two projects sharing a
    machine never share a directory and a directory listing on the server
    reads as a list of projects. Everything else — analyses, envs, downloads,
    scratch — goes UNDER this root: `submit_remote_job` creates
    `<root>/analysis/<name>`, and the ssh guard blocks a `mkdir`/`rsync` on a
    registered server that targets a path outside it.

    Returns {root, source: "binding"|"convention"|None, project_slug,
    env_name}; `root` is None when the server has no default_workdir either.
    """
    alias = server.get("alias") or ""
    binding = get_project_workdir(state, alias) or {} if alias else {}
    slug = project_slug(state)
    if (binding.get("workdir") or "").strip():
        return {"root": binding["workdir"].strip().rstrip("/") or "/",
                "source": "binding", "project_slug": slug,
                "env_name": (binding.get("env_name") or "").strip() or None}
    base = (server.get("default_workdir") or "").strip().rstrip("/")
    if not base:
        return {"root": None, "source": None, "project_slug": slug, "env_name": None}
    return {"root": f"{base}/{slug}", "source": "convention",
            "project_slug": slug, "env_name": None}


def analysis_dir(root: str, analysis: str) -> str:
    return f"{root.rstrip('/')}/analysis/{analysis}"


def delete_project_workdir(state: State, server_alias: str) -> bool:
    """Remove this project's working-directory binding for `server_alias`."""
    path = _wd_path(state, server_alias)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

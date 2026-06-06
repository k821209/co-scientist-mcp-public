"""Compute-server registry: user's HPC nodes and workstations.

Paths:
    doc:  projects/{pid}/servers/{alias}
    sub:  projects/{pid}/servers/{alias}/envs/{env_name}

`alias` is the natural key — same string the user puts in `~/.ssh/config`.

**Important security boundary:** the `ssh_key` field stores a *path on the
user's disk* (e.g. `~/.ssh/id_ed25519`), never the private key material
itself. The SSH executor (in `ssh_ops.py`) reads keys from disk on the
user's laptop — they never touch Firestore.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso


def _server_path(state: State, alias: str) -> str:
    return state.project_path("servers", alias)


def _env_path(state: State, alias: str, env_name: str) -> str:
    return state.project_path("servers", alias, "envs", env_name)


_VALID_ENV_TYPES = {"conda", "venv", "module"}


def add_server(
    state: State,
    *,
    alias: str,
    host: str,
    user: str,
    cores: int = 1,
    memory_gb: int | None = None,
    gpus: int = 0,
    ssh_key: str | None = None,
    conda_root: str | None = None,
    default_workdir: str | None = None,
    polite_max_cores_pct: int = 50,
    notes: str | None = None,
) -> dict:
    """Register a compute server. `alias` must be unique per user."""
    if not alias.strip():
        raise ValueError("alias is required")
    if not host.strip():
        raise ValueError("host is required")
    if not user.strip():
        raise ValueError("user is required")
    if not (1 <= polite_max_cores_pct <= 100):
        raise ValueError("polite_max_cores_pct must be in [1, 100]")
    path = _server_path(state, alias)
    if state.backend.get_doc(path) is not None:
        raise ValueError(f"server {alias!r} already exists")
    now = now_iso()
    doc = {
        "alias": alias, "host": host, "user": user,
        "cores": cores, "memory_gb": memory_gb, "gpus": gpus,
        "ssh_key": ssh_key, "conda_root": conda_root,
        "default_workdir": default_workdir,
        "polite_max_cores_pct": polite_max_cores_pct,
        "notes": notes, "active": True,
        "created_at": now, "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def list_servers(state: State, *, active_only: bool = True) -> list[dict]:
    """List registered servers, sorted by alias."""
    pairs = state.backend.list_collection(state.project_path("servers"))
    servers = [data for _, data in pairs]
    if active_only:
        servers = [s for s in servers if s.get("active", True)]
    servers.sort(key=lambda s: s.get("alias", ""))
    return servers


def get_server(state: State, alias: str) -> dict:
    doc = state.backend.get_doc(_server_path(state, alias))
    if doc is None:
        raise NotFound(f"server {alias!r} not registered")
    return doc


def update_server(
    state: State,
    alias: str,
    *,
    host: str | None = None,
    user: str | None = None,
    cores: int | None = None,
    memory_gb: int | None = None,
    gpus: int | None = None,
    ssh_key: str | None = None,
    conda_root: str | None = None,
    default_workdir: str | None = None,
    polite_max_cores_pct: int | None = None,
    notes: str | None = None,
    active: bool | None = None,
) -> dict:
    path = _server_path(state, alias)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"server {alias!r} not registered")
    fields: dict = {"updated_at": now_iso()}
    if host is not None: fields["host"] = host
    if user is not None: fields["user"] = user
    if cores is not None: fields["cores"] = cores
    if memory_gb is not None: fields["memory_gb"] = memory_gb
    if gpus is not None: fields["gpus"] = gpus
    if ssh_key is not None: fields["ssh_key"] = ssh_key
    if conda_root is not None: fields["conda_root"] = conda_root
    if default_workdir is not None: fields["default_workdir"] = default_workdir
    if polite_max_cores_pct is not None:
        if not (1 <= polite_max_cores_pct <= 100):
            raise ValueError("polite_max_cores_pct must be in [1, 100]")
        fields["polite_max_cores_pct"] = polite_max_cores_pct
    if notes is not None: fields["notes"] = notes
    if active is not None: fields["active"] = active
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def delete_server(state: State, alias: str) -> bool:
    path = _server_path(state, alias)
    if state.backend.get_doc(path) is None:
        return False
    # Cascade-delete envs
    for env_id, _ in state.backend.list_collection(state.project_path("servers", alias, "envs")):
        state.backend.delete_doc(_env_path(state, alias, env_id))
    state.backend.delete_doc(path)
    return True


def add_server_env(
    state: State,
    alias: str,
    *,
    env_name: str,
    env_type: str = "conda",
    python_version: str | None = None,
    key_packages: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Register a conda/venv/module env on a known server."""
    if state.backend.get_doc(_server_path(state, alias)) is None:
        raise NotFound(f"server {alias!r} not registered")
    if env_type not in _VALID_ENV_TYPES:
        raise ValueError(f"env_type must be one of {_VALID_ENV_TYPES}")
    path = _env_path(state, alias, env_name)
    now = now_iso()
    doc = {
        "env_name": env_name, "env_type": env_type,
        "python_version": python_version,
        "key_packages": list(key_packages) if key_packages else None,
        "notes": notes,
        "created_at": now,
    }
    state.backend.set_doc(path, doc)  # idempotent (replace)
    return doc


def list_server_envs(state: State, alias: str) -> list[dict]:
    if state.backend.get_doc(_server_path(state, alias)) is None:
        raise NotFound(f"server {alias!r} not registered")
    pairs = state.backend.list_collection(state.project_path("servers", alias, "envs"))
    envs = [data for _, data in pairs]
    envs.sort(key=lambda e: e.get("env_name", ""))
    return envs


def delete_server_env(state: State, alias: str, env_name: str) -> bool:
    if state.backend.get_doc(_server_path(state, alias)) is None:
        raise NotFound(f"server {alias!r} not registered")
    path = _env_path(state, alias, env_name)
    if state.backend.get_doc(path) is None:
        return False
    state.backend.delete_doc(path)
    return True

"""Nextflow pipeline registry — ACCOUNT-wide, versioned.

Paths:
    doc: users/{uid}/pipelines/{pipeline}
    doc: users/{uid}/pipelines/{pipeline}/versions/{version}

Account-wide for the same reason the servers registry is: a pipeline is a tool
you own, not a fact about one manuscript. The same `rnaseq` workflow feeds every
project you run it in, and re-registering it per project would guarantee the
copies drift.

A pipeline record is the stable identity (name, repo, description). Everything
that can change between runs — the process graph, the parameters, the file
formats moving between steps — belongs to a VERSION, because "which version
produced this figure" is the question a methods section has to answer. Editing a
version in place would destroy exactly that.

The graph is stored as processes + edges rather than as the .nf source: the
dashboard draws it, `check_requirements`-style tooling can read it, and a methods
paragraph can be generated from it. Keeping the source instead would mean every
consumer has to parse Nextflow.
"""
from __future__ import annotations

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso, slugify


def _pipelines_path(state: State) -> str:
    return f"users/{state.owner_uid}/pipelines"


def _pipeline_path(state: State, name: str) -> str:
    return f"{_pipelines_path(state)}/{name}"


def _versions_path(state: State, name: str) -> str:
    return f"{_pipeline_path(state, name)}/versions"


def _version_path(state: State, name: str, version: str) -> str:
    return f"{_versions_path(state, name)}/{version}"


def _norm(name: str, what: str = "name") -> str:
    if not name or not str(name).strip():
        raise ValueError(f"{what} is required")
    return slugify(str(name)) or str(name).strip()


def register_pipeline(
    state: State,
    *,
    name: str,
    description: str | None = None,
    repo: str | None = None,
    notes: str | None = None,
) -> dict:
    """Create or update the pipeline's stable identity (not its graph).

    `repo` is where it comes from — `nf-core/rnaseq`, a git URL, or a local path.
    """
    pid = _norm(name)
    path = _pipeline_path(state, pid)
    existing = state.backend.get_doc(path)
    now = now_iso()
    doc = {
        "name": pid,
        "display_name": str(name).strip(),
        "description": description if description is not None
        else (existing or {}).get("description"),
        "repo": repo if repo is not None else (existing or {}).get("repo"),
        "notes": notes if notes is not None else (existing or {}).get("notes"),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    return doc


def _norm_processes(processes) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for p in processes or []:
        if isinstance(p, str):
            p = {"name": p}
        if not isinstance(p, dict):
            continue
        pname = _norm(p.get("name", ""), "process name")
        if pname in seen:
            raise ValueError(f"duplicate process {pname!r}")
        seen.add(pname)
        out.append({
            "name": pname,
            "label": str(p.get("label") or p.get("name") or pname).strip(),
            "description": (str(p["description"]).strip()
                            if p.get("description") else None),
            "container": (str(p["container"]).strip()
                          if p.get("container") else None),
            "tool": str(p["tool"]).strip() if p.get("tool") else None,
        })
    return out


def _norm_edges(edges, process_names: set[str]) -> list[dict]:
    """Normalize edges and REJECT ones that point at a process that isn't there.

    A dangling edge would silently vanish from the drawing, leaving a graph that
    looks complete and is not — the failure mode being avoided everywhere else in
    this codebase. Better to refuse the write.
    """
    out: list[dict] = []
    for e in edges or []:
        if not isinstance(e, dict):
            continue
        src = _norm(e.get("from", ""), "edge 'from'")
        dst = _norm(e.get("to", ""), "edge 'to'")
        for endpoint in (src, dst):
            if endpoint not in process_names:
                raise ValueError(
                    f"edge {src!r} → {dst!r} references unknown process "
                    f"{endpoint!r}; declare it in `processes` first")
        out.append({
            "from": src,
            "to": dst,
            # What actually moves along this edge. The point of showing it.
            "format": (str(e["format"]).strip() if e.get("format") else None),
            "label": str(e["label"]).strip() if e.get("label") else None,
        })
    return out


def _norm_params(params) -> list[dict]:
    out: list[dict] = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        pname = str(p.get("name") or "").strip()
        if not pname:
            continue
        out.append({
            "name": pname,
            "default": p.get("default"),
            "type": str(p["type"]).strip() if p.get("type") else None,
            "description": (str(p["description"]).strip()
                            if p.get("description") else None),
            "required": bool(p.get("required", False)),
        })
    return out


def topological_order(processes: list[dict], edges: list[dict]) -> list[str]:
    """Process names in dependency order; raises on a cycle.

    Nextflow DAGs are acyclic, so a cycle means the registration is wrong — and a
    layered drawing would loop forever or silently drop nodes. Fail at write time
    where the message can name the processes involved.
    """
    names = [p["name"] for p in processes]
    incoming = {n: 0 for n in names}
    downstream: dict[str, list[str]] = {n: [] for n in names}
    for e in edges:
        downstream[e["from"]].append(e["to"])
        incoming[e["to"]] += 1
    queue = [n for n in names if incoming[n] == 0]
    order: list[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in downstream[n]:
            incoming[m] -= 1
            if incoming[m] == 0:
                queue.append(m)
    if len(order) != len(names):
        stuck = sorted(set(names) - set(order))
        raise ValueError(
            f"the process graph has a cycle involving: {', '.join(stuck)}")
    return order


def register_pipeline_version(
    state: State,
    name: str,
    version: str,
    *,
    processes: list | None = None,
    edges: list | None = None,
    params: list | None = None,
    nextflow_version: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Register one version's process graph, edge formats and parameters.

    A version is IMMUTABLE by default — `overwrite=True` is required to replace
    one. "Which version produced this figure" is a methods-section question, and
    quietly editing a released version's graph makes every past answer wrong.
    """
    pid = _norm(name)
    if state.backend.get_doc(_pipeline_path(state, pid)) is None:
        raise NotFound(f"pipeline not found: {pid!r} — call register_pipeline first")
    vid = str(version).strip()
    if not vid:
        raise ValueError("version is required")
    vkey = slugify(vid) or vid
    path = _version_path(state, pid, vkey)
    existing = state.backend.get_doc(path)
    if existing is not None and not overwrite:
        raise ValueError(
            f"version {vid!r} of {pid!r} already exists — versions are immutable "
            f"so a recorded run keeps meaning what it meant; pass overwrite=True "
            f"only to fix a mis-registration")

    procs = _norm_processes(processes)
    edge_list = _norm_edges(edges, {p["name"] for p in procs})
    topological_order(procs, edge_list)      # raises on a cycle

    now = now_iso()
    doc = {
        "version": vid,
        "pipeline": pid,
        "description": description,
        "nextflow_version": nextflow_version,
        "processes": procs,
        "edges": edge_list,
        "params": _norm_params(params),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    state.backend.update_doc(_pipeline_path(state, pid),
                             {"latest_version": vid, "updated_at": now})
    return doc


def list_pipelines(state: State) -> list[dict]:
    rows = [d for _, d in state.backend.list_collection(_pipelines_path(state))]
    rows.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return rows


def list_pipeline_versions(state: State, name: str) -> list[dict]:
    pid = _norm(name)
    rows = [d for _, d in state.backend.list_collection(_versions_path(state, pid))]
    rows.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return rows


def get_pipeline(state: State, name: str, version: str | None = None) -> dict:
    pid = _norm(name)
    doc = state.backend.get_doc(_pipeline_path(state, pid))
    if doc is None:
        raise NotFound(f"pipeline not found: {pid!r}")
    versions = list_pipeline_versions(state, pid)
    if version is None:
        wanted = doc.get("latest_version")
        current = next((v for v in versions if v["version"] == wanted),
                       versions[0] if versions else None)
    else:
        vkey = slugify(str(version)) or str(version)
        current = state.backend.get_doc(_version_path(state, pid, vkey))
        if current is None:
            raise NotFound(f"version {version!r} of {pid!r} not found")
    return {**doc, "versions": [v["version"] for v in versions], "current": current}


def delete_pipeline_version(state: State, name: str, version: str) -> bool:
    pid = _norm(name)
    vkey = slugify(str(version)) or str(version)
    return state.backend.delete_doc(_version_path(state, pid, vkey))


def delete_pipeline(state: State, name: str) -> bool:
    pid = _norm(name)
    for v in list_pipeline_versions(state, pid):
        delete_pipeline_version(state, pid, v["version"])
    return state.backend.delete_doc(_pipeline_path(state, pid))

"""Workflow pipeline registry — ACCOUNT-wide, versioned.

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

# What runs the workflow. Nextflow was the first case, but the processes/edges/
# params model turned out to fit a plain bash or python pipeline just as well —
# recording the edge formats and parameter defaults is exactly what makes those
# re-runnable. Registering them meant writing "NOT a Nextflow pipeline" in the
# notes of every one, which is a field pretending to be prose (feedback
# 3f65f2e18dd5). The record states it instead.
EXECUTORS = ("nextflow", "snakemake", "script", "wdl", "cwl", "make", "other")


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
    public_notes: str | None = None,
    executor: str | None = None,
    license: str | None = None,
    derived_from: dict | None = None,
) -> dict:
    """Create or update the pipeline's stable identity (not its graph).

    `repo` is where it comes from — `nf-core/rnaseq`, a git URL, or a local path.
    `executor` is what runs it (see EXECUTORS); defaults to "nextflow" for a new
    record, and is left alone on an update that does not mention it.

    TWO note fields, deliberately separate rather than one field with a mode:

      `notes`        — private, never leaves the account. Machine-specific facts
                       belong here ("egress to EBI 43 B/s, don't download here").
      `public_notes` — published with the pipeline. What someone adopting it needs
                       to know: resource requirements, what it was tested against,
                       known limitations.

    One field with a "share this?" flag would put the private text one wrong
    argument away from being published. Two fields cannot be confused by a typo.
    """
    pid = _norm(name)
    if executor is not None and executor not in EXECUTORS:
        raise ValueError(f"executor must be one of {EXECUTORS}, got {executor!r}")
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
        # Published with the pipeline (see PUBLIC_FIELDS); `notes` never is.
        "public_notes": public_notes if public_notes is not None
        else (existing or {}).get("public_notes"),
        # Terms an adopter is bound by, and whose work this started from. Both
        # published; both empty by default.
        "license": license if license is not None
        else (existing or {}).get("license"),
        "derived_from": derived_from if derived_from is not None
        else (existing or {}).get("derived_from"),
        "executor": executor if executor is not None
        else (existing or {}).get("executor") or "nextflow",
        # Private unless explicitly published. Never flipped by a plain update.
        "published": bool((existing or {}).get("published", False)),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    if doc["published"]:
        _sync_public(state, pid)
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
            # WHICH MACHINE it runs on. `repo` is a path, and a path alone does
            # not say whose disk it is on — a pipeline that hops between a
            # laptop, a GPU node and a render box reads as one filesystem
            # without this, and the reader cannot re-run a single step.
            # Hostnames were being stuffed into `container`, which is for the
            # image, not the host.
            "host": str(p["host"]).strip() if p.get("host") else None,
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
            # A REPEAT, not a circular dependency. A pipeline that generates 65
            # frames at a time and feeds the last five into the next call is six
            # passes over the same processes with a different offset each time;
            # nothing waits on its own output. Refusing it forced the loop to be
            # folded into one opaque box, which removed from the graph the one
            # thing the graph was there to show.
            "loop_back": bool(e.get("loop_back")),
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
    engine_version: str | None = None,
    nextflow_version: str | None = None,
    description: str | None = None,
    commit: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Register one version's process graph, edge formats and parameters.

    A version is IMMUTABLE by default — `overwrite=True` is required to replace
    one. "Which version produced this figure" is a methods-section question, and
    quietly editing a released version's graph makes every past answer wrong.

    When is overwrite legitimate? While NOTHING has referenced the version yet.
    Filling in a field you forgot minutes after registering is fine — no run, no
    figure and no methods paragraph points at it, so nothing that was true
    becomes false. Once a run record or a manuscript names the version, register
    a NEW one instead: the old answer has to keep meaning what it meant.
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
    # Loop-back edges are excluded: they are the only edges allowed to close a
    # cycle, and they are declared, not inferred. Every other edge is still
    # checked, so a genuine circular dependency is still refused.
    topological_order(procs, [e for e in edge_list if not e.get("loop_back")])

    now = now_iso()
    doc = {
        "version": vid,
        "pipeline": pid,
        "description": description,
        # One field for "which version of the thing that runs this".
        # `nextflow_version=` is still accepted so records written before the
        # registry covered other executors keep working.
        "engine_version": engine_version or nextflow_version,
        # The commit that IS this version. `repo` names a path; a path is
        # mutable, so without this the record silently stops describing the code
        # that produced the result the moment anyone edits the repo. Stored
        # rather than copied: a second copy of the code in the dashboard is the
        # drift this is meant to prevent.
        "commit": str(commit).strip() if commit else None,
        "processes": procs,
        "edges": edge_list,
        "params": _norm_params(params),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, doc)
    state.backend.update_doc(_pipeline_path(state, pid),
                             {"latest_version": vid, "updated_at": now})
    _sync_public(state, pid)      # no-op unless published
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


# ── publishing ────────────────────────────────────────────────────────────────
#
# A published pipeline is a CURATED COPY at /public_pipelines/{uid}__{name}, not a
# security rule opened onto the private record. Two reasons, and the second is the
# one that decides it:
#
#  1. `notes` must not go out. The guide tells users to keep measured
#     infrastructure facts there ("egress to EBI 43 B/s, don't download here"),
#     which is exactly what you do not hand to strangers.
#  2. With a rule on the private doc, EVERY field is public — including every
#     field added later. Publishing would then retroactively expose things nobody
#     considered at the time. An explicit allowlist fails the other way: a new
#     field stays private until someone adds it here on purpose.
#
# Same reasoning as the co-author share grant, where enumerating the readable
# collections beat a recursive wildcard.
PUBLIC_FIELDS = ("name", "display_name", "description", "repo", "executor",
                 # The note written FOR adopters. Its private sibling `notes`
                 # is absent by design — see the docstring below.
                 "public_notes",
                 # Attribution. `derived_from` HAS to be published: the first
                 # version of import recorded provenance as prose in the private
                 # `notes`, which is the one field that never goes out — so
                 # improving someone's pipeline and republishing it presented
                 # their work as original. A structured field in the public
                 # projection makes the lineage travel with the copy.
                 "derived_from", "license")
_MAX_PUBLIC_VERSIONS = 20


def _public_id(uid: str, name: str) -> str:
    return f"{uid}__{name}"


def _public_path(uid: str, name: str) -> str:
    return f"public_pipelines/{_public_id(uid, name)}"


def _search_terms(pipeline: dict, versions: list[dict]) -> list[str]:
    """Lowercased tokens an agent might search on: the name, the repo, the words
    of the description, and every tool/process name in the graph. Stored so a
    search does not have to fetch and scan every published pipeline."""
    words: set[str] = set()
    for field in ("name", "display_name", "repo", "description", "executor"):
        for tok in str(pipeline.get(field) or "").lower().replace("/", " ").split():
            tok = tok.strip(".,;:()[]\"'")
            if len(tok) >= 2:
                words.add(tok)
    for v in versions:
        for proc in v.get("processes") or []:
            for key in ("name", "tool"):
                val = str(proc.get(key) or "").lower().strip()
                if len(val) >= 2:
                    words.add(val)
    return sorted(words)


def _public_doc(state: State, pipeline: dict, versions: list[dict]) -> dict:
    """The public projection. Only PUBLIC_FIELDS plus the graphs — never `notes`."""
    kept = versions[:_MAX_PUBLIC_VERSIONS]
    doc = {k: pipeline.get(k) for k in PUBLIC_FIELDS}
    doc.update({
        "owner_uid": state.owner_uid,
        "latest_version": pipeline.get("latest_version"),
        "versions": [
            {
                "version": v.get("version"),
                "description": v.get("description"),
                "engine_version": v.get("engine_version"),
                "processes": v.get("processes") or [],
                "edges": v.get("edges") or [],
                "params": v.get("params") or [],
            }
            for v in kept
        ],
        "version_count": len(versions),
        # Never truncate silently: if the cap bites, the copy says so.
        "versions_truncated": len(versions) > len(kept),
        "search_terms": _search_terms(pipeline, kept),
        "updated_at": now_iso(),
    })
    return doc


def _sync_public(state: State, name: str) -> dict | None:
    """Refresh the public copy if this pipeline is published; remove it if not.

    Called from register_pipeline / register_pipeline_version so a published
    pipeline's copy cannot silently fall behind the record it claims to mirror —
    the standing hazard of any denormalised copy.
    """
    pipeline = state.backend.get_doc(_pipeline_path(state, name))
    if pipeline is None:
        return None
    path = _public_path(state.owner_uid, name)
    if not pipeline.get("published"):
        state.backend.delete_doc(path)
        return None
    versions = list_pipeline_versions(state, name)
    doc = _public_doc(state, pipeline, versions)
    existing = state.backend.get_doc(path)
    doc["published_at"] = (existing or {}).get("published_at") or doc["updated_at"]
    state.backend.set_doc(path, doc)
    return doc


def publish_pipeline(state: State, name: str, *, published: bool = True,
                     public_notes: str | None = None,
                     license: str | None = None) -> dict:
    """Make a pipeline visible to other accounts, or take it back private.

    Private is the default and stays the default. Publishing copies only
    PUBLIC_FIELDS and the process graphs — `notes` is never included, because
    that is where machine-specific facts live.

    `public_notes` is the note written FOR adopters (resource requirements, what
    it was tested against, limitations) and IS published. The reply reports
    whether one is set, since a pipeline published with nothing said to whoever
    picks it up is usually an oversight rather than a decision.
    """
    pid = _norm(name)
    path = _pipeline_path(state, pid)
    if state.backend.get_doc(path) is None:
        raise NotFound(f"pipeline not found: {pid!r}")
    patch: dict = {"published": bool(published), "updated_at": now_iso()}
    if public_notes is not None:
        patch["public_notes"] = public_notes
    if license is not None:
        patch["license"] = license
    state.backend.update_doc(path, patch)
    public = _sync_public(state, pid)
    record = state.backend.get_doc(path) or {}
    has_public_note = bool((record.get("public_notes") or "").strip())
    derived = record.get("derived_from") or None
    out = {
        "name": pid,
        "published": bool(published),
        "public_id": _public_id(state.owner_uid, pid) if published else None,
        "shared_fields": list(PUBLIC_FIELDS) + ["versions (graph/params)"],
        "withheld": ["notes"],
        "public_notes_set": has_public_note,
        "derived_from": derived,
        "license": record.get("license"),
        "version_count": (public or {}).get("version_count", 0),
    }
    notes: list[str] = []
    if published and not has_public_note:
        notes.append(
            "No public_notes set. Whoever adopts this sees the graph and the "
            "parameters but nothing about resource requirements, what it was "
            "tested against, or known limitations. Add one with "
            "publish_pipeline(name, public_notes=...) — it does NOT touch your "
            "private notes.")
    if published and derived:
        # Republishing someone else's work with improvements. The attribution
        # rides along automatically; the two things a human still has to decide
        # are the terms and whether the inherited note still describes the thing.
        notes.append(
            f"This is a derivative of {derived.get('public_id')} and is published "
            f"WITH that attribution. Confirm the original's license permits it — "
            f"this record says "
            f"{record.get('license') or 'nothing about a license'} — and check "
            f"that `public_notes` describes YOUR version, since it was inherited "
            f"from the original author.")
    if notes:
        out["suggestion"] = " ".join(notes)
    return out


def search_public_pipelines(
    state: State,
    query: str | None = None,
    *,
    executor: str | None = None,
    include_own: bool = False,
    limit: int = 25,
) -> list[dict]:
    """Search pipelines other accounts have published.

    Matching is done here rather than in the query because Firestore cannot do
    substrings: every term of `query` must appear in the pipeline's name, repo,
    description or in one of its process/tool names. Returns summaries; call
    `get_public_pipeline` for the full graph.
    """
    rows = [d for _, d in state.backend.list_collection("public_pipelines")]
    if not include_own:
        rows = [d for d in rows if d.get("owner_uid") != state.owner_uid]
    if executor:
        rows = [d for d in rows if (d.get("executor") or "nextflow") == executor]
    if query and query.strip():
        for term in query.lower().split():
            rows = [d for d in rows
                    if any(term in t for t in (d.get("search_terms") or []))]
    rows.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    out = []
    for d in rows[:limit]:
        latest = next((v for v in d.get("versions") or []
                       if v.get("version") == d.get("latest_version")),
                      (d.get("versions") or [None])[0])
        out.append({
            "public_id": _public_id(d.get("owner_uid", ""), d.get("name", "")),
            "name": d.get("name"),
            "display_name": d.get("display_name"),
            "description": d.get("description"),
            "repo": d.get("repo"),
            "executor": d.get("executor"),
            "public_notes": d.get("public_notes"),
            "latest_version": d.get("latest_version"),
            "version_count": d.get("version_count"),
            "process_count": len((latest or {}).get("processes") or []),
            "mine": d.get("owner_uid") == state.owner_uid,
        })
    return out


def get_public_pipeline(state: State, public_id: str) -> dict:
    doc = state.backend.get_doc(f"public_pipelines/{public_id.strip()}")
    if doc is None:
        raise NotFound(f"published pipeline not found: {public_id!r}")
    return {**doc, "public_id": public_id.strip(),
            "mine": doc.get("owner_uid") == state.owner_uid}


def import_public_pipeline(
    state: State, public_id: str, *, name: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Copy a published pipeline into your own account, PRIVATE.

    A copy, deliberately, not a reference: the original owner can unpublish or
    change it at any time, and a workflow you have run against needs to keep
    meaning what it meant. The copy starts unpublished — republishing someone
    else's work is a decision, not a side effect of adopting it.
    """
    src = get_public_pipeline(state, public_id)
    target = _norm(name or src.get("name") or "imported")
    if state.backend.get_doc(_pipeline_path(state, target)) is not None and not overwrite:
        raise ValueError(
            f"pipeline {target!r} already exists — pass name= or overwrite=True")
    register_pipeline(
        state, name=target,
        description=src.get("description"),
        repo=src.get("repo"),
        executor=src.get("executor") or "nextflow",
        # The author's note to adopters is exactly what a copy should keep.
        public_notes=src.get("public_notes"),
        license=src.get("license"),
        # Structured, and in PUBLIC_FIELDS — so if this copy is improved and
        # republished, the attribution goes with it. Recording it as prose in the
        # private `notes` (the first version of this) meant a republished
        # derivative carried no credit at all.
        derived_from={
            "public_id": public_id.strip(),
            "owner_uid": src.get("owner_uid"),
            "name": src.get("name"),
            "version": src.get("latest_version"),
            "imported_at": now_iso(),
        },
    )
    imported = []
    for v in src.get("versions") or []:
        register_pipeline_version(
            state, target, v.get("version") or "1.0",
            processes=v.get("processes"), edges=v.get("edges"),
            params=v.get("params"), engine_version=v.get("engine_version"),
            description=v.get("description"), overwrite=overwrite,
        )
        imported.append(v.get("version"))
    return {
        "name": target, "imported_versions": imported,
        "published": False, "source": public_id,
        "license": src.get("license"),
        "note": (
            "Private copy. If you improve it and publish, the attribution to "
            f"{public_id} travels with it automatically (derived_from). Review "
            "`public_notes` before republishing — it is currently the ORIGINAL "
            "author's note and may not describe your changes."
            + ("" if src.get("license") else
               " The original states no license, so ask the owner before "
               "republishing a derivative.")),
    }

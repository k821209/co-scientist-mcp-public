"""Node-edge-node graphs, stored as `.graph.json` MATERIALS.

The dashboard has a hand-drawing editor for these (apps/web/src/lib/graphDoc.ts,
components/GraphEditor.tsx). This module is the agent's side of the same file:
read a graph the user drew as structured data, and write or amend one.

Two invariants are the whole reason this module exists instead of telling the
agent to `add_material` a JSON file it wrote itself:

1.  **The reader refuses a broken document, whole.** `parseGraph` returns null —
    no editor, no partial load — if a node id repeats or an edge points at a
    node that isn't there, because half-loading a graph and then saving it would
    silently delete the other half. So a writer that can emit a dangling edge
    can produce a file the user can never open again. Every path here validates
    before it writes, and removing a node cascades to its edges.

2.  **Positions are content.** The arrangement a person drew is part of what
    they meant, so an edit never re-flows existing nodes; only nodes that have
    no position get one, placed clear of everything already on the canvas.
"""
from __future__ import annotations

import json
import re

from ..backends.base import NotFound
from ..state import State
from ..util import new_id, now_iso

GRAPH_SUFFIX = ".graph.json"
GRAPH_CONTENT_TYPE = "application/json"
GRAPH_SCHEMA = 1

# Must match GRAPH_NODE_W/H in apps/web/src/lib/graphDoc.ts, or a graph written
# here would overlap boxes when the editor draws it.
NODE_W = 132
NODE_H = 48
_COL_STEP = NODE_W + 88
_ROW_STEP = NODE_H + 36
_ORIGIN_X = 40
_ORIGIN_Y = 40

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(label: str) -> str:
    return _SLUG.sub("-", (label or "").lower()).strip("-")[:24]


def _material_path(state: State, material_id: str) -> str:
    return state.project_path("materials", material_id)


# ─────────────────────────── validation ───────────────────────────


def _norm_nodes(raw: list[dict], *, taken: set[str] | None = None) -> list[dict]:
    """Normalize incoming node dicts, minting ids for the ones without them.

    Agents describe nodes by label ("Raw reads", "Trimming"); ids are plumbing.
    An id is derived from the label so the graph stays readable when a human
    opens the JSON, with a short random tail when the slug is already taken.
    """
    used = set(taken or ())
    out: list[dict] = []
    for i, n in enumerate(raw or []):
        if not isinstance(n, dict):
            raise ValueError(f"node #{i + 1} is not an object: {n!r}")
        label = str(n.get("label") or "").strip()
        if not label:
            raise ValueError(f"node #{i + 1} has no label")
        nid = str(n.get("id") or "").strip()
        if not nid:
            nid = _slug(label) or "n"
            if nid in used:
                nid = f"{nid}-{new_id()[:4]}"
        if nid in used:
            raise ValueError(
                f"duplicate node id {nid!r} — ids must be unique within a graph"
            )
        used.add(nid)
        node = {"id": nid, "label": label, "kind": n.get("kind") or None}
        # Absent position means "place it for me"; an explicitly given one is
        # honoured exactly, including 0.
        for axis in ("x", "y"):
            if isinstance(n.get(axis), (int, float)):
                node[axis] = float(n[axis])
        out.append(node)
    return out


def _resolve(ref: str, nodes: list[dict], *, where: str) -> str:
    """Turn an edge endpoint into a node id, accepting a label too.

    Agents that just wrote `{"label": "Trimming"}` will write
    `{"from": "Trimming"}` next. Accepting only ids would make that a dangling
    edge — the failure this module exists to prevent — so labels resolve, and an
    ambiguous label is an error rather than a coin flip.
    """
    ref = str(ref or "").strip()
    if not ref:
        raise ValueError(f"{where}: empty endpoint")
    for n in nodes:
        if n["id"] == ref:
            return n["id"]
    hits = [n for n in nodes if n["label"] == ref]
    if len(hits) == 1:
        return hits[0]["id"]
    if len(hits) > 1:
        raise ValueError(
            f"{where}: {ref!r} matches {len(hits)} nodes by label — use the node id"
        )
    known = ", ".join(f"{n['id']} ({n['label']})" for n in nodes) or "(none)"
    raise ValueError(f"{where}: no node {ref!r}. Nodes: {known}")


def _norm_edges(raw: list[dict], nodes: list[dict],
                *, taken: set[str] | None = None) -> list[dict]:
    used = set(taken or ())
    out: list[dict] = []
    for i, e in enumerate(raw or []):
        if not isinstance(e, dict):
            raise ValueError(f"edge #{i + 1} is not an object: {e!r}")
        where = f"edge #{i + 1}"
        src = _resolve(e.get("from"), nodes, where=f"{where} from")
        dst = _resolve(e.get("to"), nodes, where=f"{where} to")
        eid = str(e.get("id") or "").strip() or f"e{new_id()[:8]}"
        if eid in used:
            eid = f"e{new_id()[:8]}"
        used.add(eid)
        out.append({
            "id": eid, "from": src, "to": dst,
            "label": (str(e["label"]).strip() or None) if e.get("label") else None,
        })
    return out


def _check(nodes: list[dict], edges: list[dict]) -> None:
    """Last line of defence: exactly what the web reader rejects."""
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate node ids: {', '.join(dupes)}")
    known = set(ids)
    for e in edges:
        for end in ("from", "to"):
            if e[end] not in known:
                raise ValueError(
                    f"edge {e['id']} points at missing node {e[end]!r} — the "
                    "dashboard would refuse to open this graph"
                )


# ─────────────────────────── layout ───────────────────────────


def _layout(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Give a position to every node that lacks one, left-to-right by depth.

    Nodes that already have coordinates keep them untouched, and the newly
    placed block starts below the lowest of them, so amending a graph the user
    arranged never shuffles their drawing or lands a new box on top of an old
    one.
    """
    placed = [n for n in nodes if "x" in n and "y" in n]
    fresh = [n for n in nodes if not ("x" in n and "y" in n)]
    if not fresh:
        return nodes

    base_y = _ORIGIN_Y
    if placed:
        base_y = max(n["y"] + NODE_H for n in placed) + _ROW_STEP

    fresh_ids = {n["id"] for n in fresh}
    # Longest-path depth over edges among the new nodes; an edge from an
    # already-placed node contributes no depth (its column is fixed elsewhere).
    preds: dict[str, list[str]] = {n["id"]: [] for n in fresh}
    for e in edges:
        if e["to"] in fresh_ids and e["from"] in fresh_ids:
            preds[e["to"]].append(e["from"])

    depth: dict[str, int] = {}

    def walk(nid: str, seen: frozenset[str]) -> int:
        if nid in depth:
            return depth[nid]
        if nid in seen:            # a cycle is legal in a drawing; stop unrolling
            return 0
        d = 0
        for p in preds[nid]:
            d = max(d, walk(p, seen | {nid}) + 1)
        depth[nid] = d
        return d

    for n in fresh:
        walk(n["id"], frozenset())

    per_col: dict[int, int] = {}
    for n in fresh:
        col = depth[n["id"]]
        row = per_col.get(col, 0)
        per_col[col] = row + 1
        n["x"] = float(_ORIGIN_X + col * _COL_STEP)
        n["y"] = float(base_y + row * _ROW_STEP)
    return nodes


# ─────────────────────────── read / write ───────────────────────────


def _load(state: State, material_id: str) -> tuple[dict, dict]:
    doc = state.backend.get_doc(_material_path(state, material_id))
    if doc is None:
        raise NotFound(f"material {material_id!r} not found")
    if not str(doc.get("filename", "")).endswith(GRAPH_SUFFIX):
        raise ValueError(
            f"material {material_id!r} is {doc.get('filename')!r}, not a "
            f"{GRAPH_SUFFIX} graph"
        )
    blob_path = doc.get("blob_path")
    data = state.backend.get_blob(blob_path) if blob_path else None
    if data is None:
        raise NotFound(f"graph {material_id!r} blob missing at {blob_path}")
    try:
        graph = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"graph {material_id!r} is not valid JSON: {exc}") from exc
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise ValueError(f"graph {material_id!r} has no nodes array")
    graph.setdefault("edges", [])
    return doc, graph


def _serialize(title: str | None, nodes: list[dict], edges: list[dict]) -> bytes:
    payload = {
        "schema": GRAPH_SCHEMA,
        "title": title,
        "nodes": nodes,
        "edges": edges,
        "updated_at": now_iso(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _filename(title: str | None) -> str:
    return f"{_slug(title or '') or 'graph'}{GRAPH_SUFFIX}"


def read_graph(state: State, material_id: str) -> dict:
    """Read a graph material as structured data: nodes, edges, and the
    adjacency an agent actually wants (`incoming`/`outgoing` per node)."""
    doc, graph = _load(state, material_id)
    nodes, edges = graph["nodes"], graph["edges"]
    out_by: dict[str, list[dict]] = {n.get("id"): [] for n in nodes}
    in_by: dict[str, list[dict]] = {n.get("id"): [] for n in nodes}
    for e in edges:
        if e.get("from") in out_by:
            out_by[e["from"]].append({"to": e.get("to"), "label": e.get("label")})
        if e.get("to") in in_by:
            in_by[e["to"]].append({"from": e.get("from"), "label": e.get("label")})
    return {
        "material_id": material_id,
        "filename": doc.get("filename"),
        "title": graph.get("title"),
        "nodes": [
            {**n,
             "outgoing": out_by.get(n.get("id"), []),
             "incoming": in_by.get(n.get("id"), [])}
            for n in nodes
        ],
        "edges": edges,
        "user_note": doc.get("user_note"),
        "ai_note": doc.get("ai_note"),
        "updated_at": graph.get("updated_at") or doc.get("updated_at"),
    }


def list_graphs(state: State) -> list[dict]:
    """List the project's graph materials (the `.graph.json` ones), newest
    first — without downloading them."""
    pairs = state.backend.list_collection(state.project_path("materials"))
    graphs = [
        {
            "material_id": data.get("material_id"),
            "filename": data.get("filename"),
            "user_note": data.get("user_note"),
            "ai_note": data.get("ai_note"),
            "updated_at": data.get("updated_at"),
        }
        for _, data in pairs
        if str(data.get("filename", "")).endswith(GRAPH_SUFFIX)
    ]
    graphs.sort(key=lambda g: g.get("updated_at") or "", reverse=True)
    return graphs


def write_graph(
    state: State,
    *,
    title: str,
    nodes: list[dict],
    edges: list[dict] | None = None,
    ai_note: str | None = None,
) -> dict:
    """Create a new graph material from nodes and edges."""
    ns = _norm_nodes(nodes)
    if not ns:
        raise ValueError("a graph needs at least one node")
    es = _norm_edges(edges or [], ns)
    _check(ns, es)
    _layout(ns, es)

    material_id = new_id()
    filename = _filename(title)
    blob_path = _material_path(state, f"{material_id}__{filename}")
    data = _serialize(title, ns, es)
    state.backend.put_blob(blob_path, data)

    now = now_iso()
    doc = {
        "material_id": material_id,
        "filename": filename,
        "content_type": GRAPH_CONTENT_TYPE,
        "size_bytes": len(data),
        "blob_path": blob_path,
        "description": ai_note,
        "ai_note": ai_note,
        "user_note": None,
        "uploaded_by": "agent",
        "created_at": now,
        "updated_at": now,
    }
    state.backend.set_doc(_material_path(state, material_id), doc)
    return {
        "material_id": material_id,
        "filename": filename,
        "title": title,
        "nodes": ns,
        "edges": es,
        "dashboard_url": state.dashboard_url("materials"),
    }


def edit_graph(
    state: State,
    material_id: str,
    *,
    title: str | None = None,
    add_nodes: list[dict] | None = None,
    rename_nodes: dict | None = None,
    remove_nodes: list[str] | None = None,
    add_edges: list[dict] | None = None,
    remove_edges: list[dict] | None = None,
    ai_note: str | None = None,
) -> dict:
    """Amend an existing graph in place, leaving everything not mentioned alone.

    `rename_nodes` maps node id (or current label) → new label, or → a dict of
    fields (`label`, `kind`). `remove_edges` entries are `{"from","to"}` pairs
    or `{"id"}`. Removing a node also removes every edge touching it.
    """
    doc, graph = _load(state, material_id)
    nodes = _norm_nodes(graph["nodes"])
    edges = _norm_edges(graph["edges"], nodes)

    if remove_nodes:
        gone = {_resolve(r, nodes, where="remove_nodes") for r in remove_nodes}
        nodes = [n for n in nodes if n["id"] not in gone]
        # Cascade. An edge left pointing at a deleted node is precisely what
        # makes the whole file unopenable, so this is not optional cleanup.
        edges = [e for e in edges
                 if e["from"] not in gone and e["to"] not in gone]

    if rename_nodes:
        for ref, val in rename_nodes.items():
            nid = _resolve(ref, nodes, where="rename_nodes")
            target = next(n for n in nodes if n["id"] == nid)
            patch = val if isinstance(val, dict) else {"label": val}
            if patch.get("label"):
                target["label"] = str(patch["label"]).strip()
            if "kind" in patch:
                target["kind"] = patch["kind"] or None

    if add_nodes:
        nodes = nodes + _norm_nodes(add_nodes, taken={n["id"] for n in nodes})

    if remove_edges:
        for spec in remove_edges:
            if not isinstance(spec, dict):
                raise ValueError(f"remove_edges entry is not an object: {spec!r}")
            if spec.get("id"):
                edges = [e for e in edges if e["id"] != spec["id"]]
                continue
            src = _resolve(spec.get("from"), nodes, where="remove_edges from")
            dst = _resolve(spec.get("to"), nodes, where="remove_edges to")
            edges = [e for e in edges
                     if not (e["from"] == src and e["to"] == dst)]

    if add_edges:
        edges = edges + _norm_edges(add_edges, nodes,
                                    taken={e["id"] for e in edges})

    if not nodes:
        raise ValueError(
            "that edit would empty the graph — delete the material instead"
        )
    _check(nodes, edges)
    _layout(nodes, edges)

    new_title = title if title is not None else graph.get("title")
    data = _serialize(new_title, nodes, edges)
    state.backend.put_blob(doc["blob_path"], data)
    fields = {"size_bytes": len(data), "updated_at": now_iso()}
    if ai_note is not None:
        fields["ai_note"] = ai_note
        fields["description"] = ai_note
    state.backend.update_doc(_material_path(state, material_id), fields)
    return {
        "material_id": material_id,
        "filename": doc.get("filename"),
        "title": new_title,
        "nodes": nodes,
        "edges": edges,
        "dashboard_url": state.dashboard_url("materials"),
    }

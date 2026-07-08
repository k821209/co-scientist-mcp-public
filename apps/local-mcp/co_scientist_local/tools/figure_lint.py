"""Deterministic layout linter for CODE-generated figures (matplotlib/graphviz
schematics), so the model iterates on a spec instead of eyeballing PNGs.

Represent the figure as a spec — nodes (boxes) + edges (arrows) on a canvas —
and lint the geometry BEFORE rendering (feedback ec879d1d0e17):

  1. box_overlap     — two node rects intersect (with a configurable min_gap).
  2. out_of_canvas   — a node rect leaves [0,W] x [0,H].
  3. arrow_crosses_box — an edge segment passes through an UNRELATED node rect
     (Liang-Barsky). This is the highest-value check — it catches crossings a
     visual review misses.

Coordinates: (x, y) is a box's BOTTOM-LEFT corner, w x h its size, y-up, canvas
[0,W] x [0,H] — matplotlib data-coordinate convention.

NOT covered here: label overflow. Doing it right needs the renderer's actual
text extent (matplotlib `Text.get_window_extent`), NOT a len(chars)*fontsize
heuristic (which mis-fires). Check that at render time — see the /scientific-image
skill.
"""
from __future__ import annotations

_SIDES = {"center", "top", "bottom", "left", "right"}


def _rect(n: dict) -> tuple[float, float, float, float]:
    """Node → (xmin, ymin, xmax, ymax)."""
    x, y, w, h = float(n["x"]), float(n["y"]), float(n["w"]), float(n["h"])
    return x, y, x + w, y + h


def _anchor(n: dict, side: str | None) -> tuple[float, float]:
    xmin, ymin, xmax, ymax = _rect(n)
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return {
        "center": (cx, cy),
        "top": (cx, ymax),
        "bottom": (cx, ymin),
        "left": (xmin, cy),
        "right": (xmax, cy),
    }.get(side or "center", (cx, cy))


def _boxes_overlap(a: dict, b: dict, min_gap: float) -> bool:
    ax0, ay0, ax1, ay1 = _rect(a)
    bx0, by0, bx1, by1 = _rect(b)
    # inflate a by min_gap on every side, then test intersection
    return not (ax1 + min_gap <= bx0 or bx1 <= ax0 - min_gap
                or ay1 + min_gap <= by0 or by1 <= ay0 - min_gap)


def _segment_crosses_rect(x0, y0, x1, y1, rect, eps=1e-9) -> bool:
    """Liang-Barsky: does segment (x0,y0)-(x1,y1) pass through the rect interior
    for a portion of positive length?"""
    xmin, ymin, xmax, ymax = rect
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - xmin, xmax - x0, y0 - ymin, ymax - y0)
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < eps:
            if qi < 0:                # parallel and outside this edge
                return False
            continue
        t = qi / pi
        if pi < 0:
            if t > t1:
                return False
            if t > t0:
                t0 = t
        else:
            if t < t0:
                return False
            if t < t1:
                t1 = t
    return (t1 - t0) > eps            # positive-length overlap inside the rect


def lint_layout(
    nodes: list[dict],
    edges: list[dict] | None = None,
    *,
    canvas_w: float,
    canvas_h: float,
    min_gap: float = 0.0,
) -> dict:
    """Lint a figure layout spec. Returns
    {ok: bool, issues: [{type, ...}], counts: {...}}.

    nodes: [{id, x, y, w, h, ...}]  — (x,y)=bottom-left, y-up.
    edges: [{src, dst, src_side?, dst_side?}] — sides in center|top|bottom|left|right.
    """
    edges = edges or []
    by_id = {n["id"]: n for n in nodes}
    issues: list[dict] = []

    # 1. box overlaps (each unordered pair once)
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if _boxes_overlap(nodes[i], nodes[j], min_gap):
                issues.append({
                    "type": "box_overlap",
                    "nodes": [nodes[i]["id"], nodes[j]["id"]],
                })

    # 2. out of canvas
    for n in nodes:
        x0, y0, x1, y1 = _rect(n)
        if x0 < 0 or y0 < 0 or x1 > canvas_w or y1 > canvas_h:
            issues.append({
                "type": "out_of_canvas",
                "node": n["id"],
                "rect": [x0, y0, x1, y1],
                "canvas": [canvas_w, canvas_h],
            })

    # 3. arrow crosses an unrelated box
    for e in edges:
        src, dst = by_id.get(e["src"]), by_id.get(e["dst"])
        if not src or not dst:
            issues.append({"type": "dangling_edge", "edge": [e.get("src"), e.get("dst")]})
            continue
        x0, y0 = _anchor(src, e.get("src_side"))
        x1, y1 = _anchor(dst, e.get("dst_side"))
        for n in nodes:
            if n["id"] in (e["src"], e["dst"]):
                continue
            if _segment_crosses_rect(x0, y0, x1, y1, _rect(n)):
                issues.append({
                    "type": "arrow_crosses_box",
                    "edge": [e["src"], e["dst"]],
                    "crosses": n["id"],
                })

    counts: dict[str, int] = {}
    for it in issues:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
    return {"ok": not issues, "issues": issues, "counts": counts}

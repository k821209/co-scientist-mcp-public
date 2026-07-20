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

  4. label_overflow — a node's text doesn't fit inside its box (feedback
     f10b60c89067, parity with the deck linter). Box w/h are DATA units and
     font_size is POINTS, so this needs the figure size (`figure_w_in`,
     `figure_h_in`) to map data-units↔points — that mapping is the part a naive
     len(chars)*fontsize heuristic gets wrong. Pass a node `label` + `font_size`
     (pt) [+ `padding` in data units, `wrap`], and the figure size, and it flags
     labels whose estimated extent exceeds the box interior, with the measured
     vs available size + a suggested max font / min box. The text extent is a
     CJK-aware char-advance ESTIMATE (no renderer), so borderline cases still
     merit a render check; clear overflows it catches deterministically.
"""
from __future__ import annotations

_SIDES = {"center", "top", "bottom", "left", "right"}

# Per-character advance as a fraction of the em (font size), by rough class.
# A CJK/Hangul/Kana glyph is ~full-width; Latin varies a lot by letter.
def _char_em(ch: str) -> float:
    o = ord(ch)
    if o >= 0x1100 and (0x1100 <= o <= 0x11FF or 0x2E80 <= o <= 0xA4CF
                        or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF
                        or 0xFF00 <= o <= 0xFF60 or 0x3000 <= o <= 0x303F):
        return 1.0                       # full-width CJK / Hangul / kana / CJK punct
    if ch in "MWＭＷ@%—":
        return 0.90
    if ch in "mw&":
        return 0.80
    if ch == " ":
        return 0.30
    if ch in "iIl.,;:'!|jtf()[]-":
        return 0.33
    if ch.isupper() or ch.isdigit():
        return 0.62
    return 0.52


def _text_width_pt(text: str, font_pt: float) -> float:
    return font_pt * sum(_char_em(c) for c in text)


def _wrap_lines(text: str, max_w_pt: float, font_pt: float) -> list[str]:
    """Greedy word-wrap to `max_w_pt`. Also splits on existing newlines. A single
    word wider than the box stays on its own (over-wide) line."""
    out: list[str] = []
    for raw in (text or "").split("\n"):
        line = ""
        for word in raw.split(" "):
            cand = word if not line else f"{line} {word}"
            if _text_width_pt(cand, font_pt) <= max_w_pt or not line:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


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
    figure_w_in: float | None = None,
    figure_h_in: float | None = None,
) -> dict:
    """Lint a figure layout spec. Returns
    {ok: bool, issues: [{type, ...}], counts: {...}}.

    nodes: [{id, x, y, w, h, label?, font_size?, padding?, wrap?}] —
        (x,y)=bottom-left, y-up. `label`+`font_size` (pt) enable the
        label_overflow check; `padding` (data units, default 0) is the interior
        inset; `wrap`=True checks wrapped height instead of single-line width.
    edges: [{src, dst, src_side?, dst_side?}] — sides in center|top|bottom|left|right.
    figure_w_in/figure_h_in: figure size in inches — REQUIRED for label_overflow
        (maps data units ↔ points). Omit to skip the label check.
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

    # 4. label overflow (needs the figure size to map data units ↔ points)
    _TOL = 1.02   # 2% slack so a label that just touches the edge doesn't fire
    labelled = [n for n in nodes if str(n.get("label", "")).strip() and n.get("font_size")]
    if labelled and (figure_w_in and figure_h_in and canvas_w > 0 and canvas_h > 0):
        ppx = (figure_w_in * 72.0) / canvas_w      # points per data-unit, x
        ppy = (figure_h_in * 72.0) / canvas_h
        for n in labelled:
            text = str(n["label"])
            fs = float(n["font_size"])
            pad = float(n.get("padding", 0) or 0)
            avail_w = max(0.0, (float(n["w"]) - 2 * pad) * ppx)
            avail_h = max(0.0, (float(n["h"]) - 2 * pad) * ppy)
            if n.get("wrap"):
                lines = _wrap_lines(text, avail_w, fs)
                meas_w = max(_text_width_pt(ln, fs) for ln in lines)   # widest (unbreakable) line
                meas_h = len(lines) * fs * 1.25
            else:
                meas_w = _text_width_pt(text, fs)
                meas_h = fs * 1.2                                       # single-line cap+descender
            over_w = meas_w > avail_w * _TOL
            over_h = meas_h > avail_h * _TOL
            if over_w or over_h:
                axis = "both" if over_w and over_h else ("width" if over_w else "height")
                fit_font = fs
                if meas_w > 0 and meas_h > 0:
                    fit_font = round(fs * min(avail_w / meas_w, avail_h / meas_h), 1)
                issues.append({
                    "type": "label_overflow",
                    "node": n["id"],
                    "axis": axis,
                    "measured_pt": {"w": round(meas_w, 1), "h": round(meas_h, 1)},
                    "available_pt": {"w": round(avail_w, 1), "h": round(avail_h, 1)},
                    "suggested_max_font": fit_font,
                    "suggested_min_box": {
                        "w": round(meas_w / ppx + 2 * pad, 3),
                        "h": round(meas_h / ppy + 2 * pad, 3),
                    },
                    "note": "estimated extent (CJK-aware char-advance, no renderer) — "
                            "shrink the font, enlarge the box, or set wrap=True",
                })
    elif labelled:
        issues.append({
            "type": "label_check_skipped",
            "reason": "pass figure_w_in + figure_h_in (figure size in inches) to "
                      "enable label_overflow — box w/h are data units, font_size is points.",
            "labelled_nodes": [n["id"] for n in labelled],
        })

    counts: dict[str, int] = {}
    for it in issues:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
    # A skipped label check is informational, not a failure.
    ok = not [it for it in issues if it["type"] != "label_check_skipped"]
    return {"ok": ok, "issues": issues, "counts": counts}

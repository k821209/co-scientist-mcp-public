"""What each dashboard tab is for — read from packages/tab_roles.json.

One source, two readers: the dashboard (the line under the tab bar and the
"What each tab is for" panel) and project_guide(). A researcher opening the
project and an agent calling the MCP see the same sentence for the same tab,
so neither has to infer from a tab's contents what it was meant to hold.
"""
from __future__ import annotations

import json
import pathlib

_PKG_DIR = pathlib.Path(__file__).resolve().parent


def find_tab_roles_file() -> pathlib.Path | None:
    bundled = _PKG_DIR / "tab_roles.json"          # wheel / pip-only install
    if bundled.is_file():
        return bundled
    repo = _PKG_DIR.parents[2] / "packages" / "tab_roles.json"   # editable / clone
    return repo if repo.is_file() else None


def load_tab_roles() -> list[dict]:
    f = find_tab_roles_file()
    if f is None:
        return []
    try:
        return list((json.loads(f.read_text(encoding="utf-8")) or {}).get("tabs") or [])
    except (OSError, ValueError):
        return []


def render_tab_roles(tabs: list[dict] | None = None, *, include_video: bool = True) -> str:
    """The guide section. Empty string when the file is missing, so the guide
    never fails on it. `include_video=False` drops the Video tab, as the guide
    drops the video skills: a session cannot be told about tools it cannot
    call (tests/test_features.py)."""
    tabs = load_tab_roles() if tabs is None else tabs
    if not include_video:
        tabs = [t for t in tabs if t.get("key") != "video"]
    if not tabs:
        return ""
    lines = ["## The dashboard, tab by tab", "",
             "What each tab is FOR — the same sentences the researcher sees under the",
             "tab bar. Write to the tab whose role fits; the \"not\" says where the",
             "neighbouring thing goes.", ""]
    for t in tabs:
        tools = ", ".join(f"`{x}`" for x in t.get("tools") or [])
        lines.append(f"- **{t['label']}** — {t['role']}")
        lines.append(f"  Holds: {t['holds']}. Not: {t['not']}." + (f" Tools: {tools}." if tools else ""))
    return "\n".join(lines) + "\n"

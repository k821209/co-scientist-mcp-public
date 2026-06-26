#!/usr/bin/env python3
"""SessionStart hook: detect the active paper from cwd, surface a banner.

In the v0 cloud architecture the banner is minimal — it points the user
at the MCP tools that show current state (paper list, open comments).
A future refinement is to fetch live state from Firestore directly via
a cached refresh token, but that requires hook → network access which
we want to avoid for fast startup.

Paper detection: walks up from cwd looking for a `.co-scientist-paper`
file (single line: slug) or a `manuscript.md` (slug = dir name).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def detect_paper(cwd: Path) -> str | None:
    for ancestor in [cwd, *cwd.parents]:
        marker = ancestor / ".co-scientist-paper"
        if marker.is_file():
            return marker.read_text().strip() or ancestor.name
        if (ancestor / "manuscript.md").is_file():
            return ancestor.name
    return None


def build_banner(paper_slug: str | None) -> str:
    if paper_slug:
        return (
            f"📝 co-scientist: working on paper {paper_slug!r}\n"
            f"\n"
            f"Quick start:\n"
            f"  /paper-writing             — write/update sections\n"
            f"  /paper-revision            — address open user comments\n"
            f"\n"
            f"Status: call mcp__co_scientist__count_open_user_comments({paper_slug!r}) "
            f"to see how many comments the dashboard has waiting for you."
        )
    return (
        "co-scientist: no paper detected in the current directory.\n"
        "Run `mcp__co_scientist__list_papers` to see your papers, "
        "or `mcp__co_scientist__create_paper` to start one."
    )


def version_warning() -> str:
    """Best-effort 'your MCP is out of date' nudge. Fully guarded: if
    co_scientist_local isn't importable in this env, or the network probe
    fails/times out, returns '' so the hook never slows or breaks startup."""
    try:
        from co_scientist_local.version_check import check_version
        v = check_version(timeout=1.5)
        if v.get("update_available"):
            return "\n\n⚠️  " + v.get("update_hint", "co-scientist-local is out of date — update it.")
    except Exception:
        pass
    return ""


def main() -> None:
    cwd = Path.cwd()
    paper = detect_paper(cwd)
    banner = build_banner(paper) + version_warning()
    print(json.dumps({"additionalContext": banner}))


if __name__ == "__main__":
    main()

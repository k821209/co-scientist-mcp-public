"""The MCP tools a Pi session gets as DIRECT tools.

Everything else stays reachable through the adapter's `mcp({ tool, args })`
proxy, under the same name.

Why a list and not `true`: every direct tool costs ~150–300 tokens of system
prompt on every turn, and the server registers some 240. The adapter's own
README says direct exposure is "good for targeted sets of 5–20 tools; for
servers with 75+ tools, stick with the proxy or pick specific tools". It was
`directTools: true` once, called non-negotiable — and on the ~100k-context
models Pi is usually run with, roughly half the window was gone before the
first message.

Why THESE: not taste. The rule is "the five session-start tools, plus every
tool that two or more skills call" — computed from the skill files, and
`tests/test_skill_audit.py` fails if this list drifts from that computation.
Change the rule there, then regenerate here.

This list lived in the dashboard (apps/web/src/lib/piDirectTools.ts) until
2026-11-16, because the Setup tab's by-hand steps generated Pi's config. The
one-line install wrote a plain `.mcp.json` and so a Pi installed that way had
neither this list nor `toolPrefix` — it lives here now, where `wire` writes it.
"""
from __future__ import annotations

PI_DIRECT_TOOLS: tuple[str, ...] = (
    "add_figure",
    "add_reference_by_doi",
    "add_review",
    "add_section",
    "add_table",
    "add_video",
    "attach_export",
    "compare_run_params",
    "count_open_user_comments",
    "generate_image",
    "get_manuscript",
    "get_section",
    "get_paper_state",
    "get_project_memory",
    "get_submission",
    "lint_manuscript",
    "list_analyses",
    "list_analysis_runs",
    "list_figures",
    "list_papers",
    "list_references",
    "list_reviews",
    "list_submissions",
    "list_tables",
    "prepare_export",
    "project_guide",
    "reconcile_review_anchors",
    "register_submission",
    "reorder_supplementary",
    "resolve_paper_comment",
    "review_triage_summary",
    "update_analysis",
    "update_review",
    "update_section",
    "whoami",
    "create_paper",
    "join_video_chunks",
    "list_paper_comments",
    "search_works",
)

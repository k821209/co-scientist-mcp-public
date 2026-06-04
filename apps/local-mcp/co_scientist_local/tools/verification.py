"""Verification findings: persistent log of CrossRef DOI checks.

The dashboard's "Sync DOIs" button writes one finding doc per checked
DOI. Claude Code can then read those findings in later sessions via
`list_verification_findings(slug)` — surfaces hallucinations the user
already spotted in the dashboard so the agent can fix them.

Paths:
    projects/{pid}/papers/{slug}/verification_findings/{doi_safe_id}

The doc ID is a sanitized version of the DOI (alphanumeric + underscore)
so the same DOI's verdict is overwritten on re-sync rather than appended.
"""
from __future__ import annotations

import re

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from .papers import _paper_path


def _findings_path(state: State, slug: str) -> str:
    return state.project_path("papers", slug, "verification_findings")


def _finding_doc_path(state: State, slug: str, doi_safe: str) -> str:
    return state.project_path("papers", slug, "verification_findings", doi_safe)


def _doi_safe_id(doi: str) -> str:
    """Sanitize a DOI for use as a Firestore doc ID."""
    return re.sub(r"[^a-z0-9]+", "_", (doi or "").lower()).strip("_") or "_"


def _ensure_paper(state: State, slug: str) -> None:
    if state.backend.get_doc(_paper_path(state, slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")


def list_verification_findings(
    state: State,
    slug: str,
    *,
    only_unacknowledged: bool = True,
    only_problems: bool = True,
) -> list[dict]:
    """List verification findings for a paper.

    Defaults filter for what an agent actually needs to act on:
      - only_unacknowledged=True: skip ones the user/agent already marked
        as handled
      - only_problems=True: skip 'resolved' findings (no action needed)

    Set both to False to get the full audit log.
    """
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(_findings_path(state, slug))
    items = [data for _, data in pairs]
    if only_unacknowledged:
        items = [i for i in items if not i.get("acknowledged")]
    if only_problems:
        items = [i for i in items if i.get("kind") not in ("resolved",)]
    items.sort(key=lambda x: (x.get("kind") or "", x.get("detected_at") or ""))
    return items


def acknowledge_finding(
    state: State,
    slug: str,
    doi: str,
    *,
    verdict: str | None = None,
    actor: str = "agent",
    note: str | None = None,
) -> dict:
    """Record the agent's (or user's) judgment on one finding.

    `verdict` is the context-check decision the SERVER refuses to make:

      - "approved"  — agent confirms the cited paper fits the manuscript
                      context. Sets context_verified=True.
      - "rejected"  — agent confirms the citation is wrong (hallucinated
                      paper assignment). Sets context_verified=False.
      - None        — no verdict change; just mark acknowledged.

    Either way, the finding is marked acknowledged so it stops surfacing
    in `list_verification_findings()` defaults.
    """
    _ensure_paper(state, slug)
    doc_path = _finding_doc_path(state, slug, _doi_safe_id(doi))
    if state.backend.get_doc(doc_path) is None:
        raise NotFound(f"finding for doi {doi!r} not found")
    fields: dict = {
        "acknowledged": True,
        "acknowledged_at": now_iso(),
        "acknowledged_by": actor,
    }
    if verdict is not None:
        if verdict not in ("approved", "rejected"):
            raise ValueError("verdict must be 'approved', 'rejected', or None")
        fields["context_verified"] = (verdict == "approved")
        fields["context_checked_at"] = now_iso()
        fields["context_checked_by"] = actor
        fields["agent_verdict"] = verdict
    if note is not None:
        fields["acknowledged_note"] = note
    state.backend.update_doc(doc_path, fields)
    return state.backend.get_doc(doc_path)


def clear_findings(state: State, slug: str) -> int:
    """Delete all findings for a paper. Call before rerunning a full sync
    if you want a clean slate (otherwise re-sync just overwrites per-DOI).
    Returns the number of findings deleted.
    """
    _ensure_paper(state, slug)
    pairs = state.backend.list_collection(_findings_path(state, slug))
    count = 0
    for doc_id, _ in pairs:
        state.backend.delete_doc(_finding_doc_path(state, slug, doc_id))
        count += 1
    return count

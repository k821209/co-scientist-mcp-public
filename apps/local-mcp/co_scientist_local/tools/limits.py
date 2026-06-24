"""Flat per-container creation caps — abuse ceilings, not plan tiers.

The local MCP can't reliably read the user's plan (a project doc's plan_id
isn't synced on upgrade), so these are uniform, generous limits that no real
manuscript reaches but that stop a script from creating thousands of papers /
decks / figures in a single project.
"""
from __future__ import annotations

PAPERS_PER_PROJECT = 50
DECKS_PER_PAPER = 20
FIGURES_PER_PAPER = 300
TABLES_PER_PAPER = 200


def enforce_cap(count: int, cap: int, what: str) -> None:
    """Raise if creating one more would exceed `cap`. `what` names the item
    (e.g. "papers per project") for the message."""
    if count >= cap:
        raise ValueError(
            f"{what} limit reached ({cap}). Delete unused ones first — this is "
            f"an anti-abuse guard, not a subscription limit."
        )

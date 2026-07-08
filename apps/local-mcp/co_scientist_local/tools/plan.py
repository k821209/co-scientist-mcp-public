"""Report the project owner's subscription plan + its limits.

The AUTHORITATIVE plan lives on the user doc (`users/{uid}`), written by the
billing Cloud Functions (activate / renew / trial / expire). The MCP is
authenticated as the project owner, so it can read `users/{owner_uid}` directly
— unlike the project doc's `plan_id`, which isn't kept in sync (see limits.py).

Numbers mirror the web `plans.ts` / the generate-image Cloud Function's
PLAN_QUOTAS — keep them in sync when the tiers change.
"""
from __future__ import annotations

from ..state import State

# tier -> limits. project_cap None = unlimited.
_PLAN_LIMITS = {
    "free": {"image_quota_month": 0, "upload_limit_mb": 50, "project_cap": 3, "storage_gb": 0.2},
    "pro": {"image_quota_month": 200, "upload_limit_mb": 500, "project_cap": None, "storage_gb": 20},
    "max": {"image_quota_month": 2000, "upload_limit_mb": 1000, "project_cap": None, "storage_gb": 200},
}


def _tier(plan_id: str) -> str:
    p = (plan_id or "free").lower()
    if p in ("max", "enterprise"):   # enterprise = legacy alias for max
        return "max"
    return "pro" if p == "pro" else "free"


def get_plan(state: State) -> dict:
    """Return the owner's current plan + limits:
    {plan_id, tier, subscription_status, billing_period, plan_expires_at,
     next_billing_at, is_trial, can_generate_images, limits{...}}.

    Reads the authoritative `users/{owner_uid}` doc; defaults to free if it
    can't be read (e.g. no billing state yet)."""
    doc: dict = {}
    try:
        doc = state.backend.get_doc(f"users/{state.owner_uid}") or {}
    except Exception:
        doc = {}
    raw = doc.get("plan_id") or "free"
    tier = _tier(raw)
    limits = _PLAN_LIMITS[tier]
    status = doc.get("subscription_status")
    return {
        "plan_id": raw,
        "tier": tier,
        "subscription_status": status,
        "billing_period": doc.get("billing_period"),
        "plan_expires_at": doc.get("plan_expires_at"),
        "next_billing_at": doc.get("next_billing_at"),
        "is_trial": status == "trialing",
        "can_generate_images": limits["image_quota_month"] > 0,
        "limits": dict(limits),
    }

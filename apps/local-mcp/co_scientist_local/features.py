"""Feature gates — which optional tool families this MCP process registers.

The tool surface is the expensive part of an MCP: every registered tool's name,
description and parameter schema is loaded into the agent's context at session
start, for every session, whether or not the session ever calls it. At 173 tools
that cost ~19k tokens before any work happens, and the video/YouTube family was
~1.5k of it on machines that never touch video.

Gates therefore decide REGISTRATION, not permission — a hidden tool family simply
does not exist for the session. Detection must be zero-config for the machines
that genuinely use the feature, because a capability silently vanishing after an
upgrade is a worse failure than a fat context.
"""
from __future__ import annotations

import os


def video_enabled() -> bool:
    """Whether the video/YouTube tool family (and its guide section) loads.

    Order:
      1. `CO_SCIENTIST_ENABLE_VIDEO=1` / `=0` — explicit override, both ways.
         The escape hatch for a fresh video machine that has no token yet
         (`youtube_connect` itself is gated, so the first-ever connect on a new
         box needs the env var once; after that the token file auto-enables).
      2. The YouTube token file existing on THIS machine — the zero-config
         signal. A machine that has connected a channel does video work; one
         that never has, doesn't. Uses the same path resolution as the token
         store itself (`CO_SCIENTIST_YOUTUBE_TOKEN` respected).
    """
    override = os.environ.get("CO_SCIENTIST_ENABLE_VIDEO")
    if override is not None:
        return override.strip().lower() in ("1", "true", "yes", "on")
    try:
        from .tools.youtube import _token_path
        return _token_path().is_file()
    except Exception:
        return False

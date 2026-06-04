#!/usr/bin/env python3
"""PostToolUse hook — almost a no-op in the cloud architecture.

The original ran 4 fan-out syncs after every MCP call (sync_sections,
sync_supplementary, sync_figures, sync_deck). In the new model the cloud
MCP is self-syncing: every write is transactional with the manuscript
blob upload, so the dashboard sees consistent state immediately.

We keep the hook as a hand-off point for future:
- mirror manuscript.md back to a local working copy for offline reading
- log MCP tool usage to a local audit file
- refresh the ssh-nohup hook's server cache after add_server/update_server

For v0 the hook just consumes stdin so Claude Code doesn't deadlock and
exits with 0.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        pass
    # Intentionally no-op


if __name__ == "__main__":
    main()

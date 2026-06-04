"""`co-scientist auth {whoami,logout}` — inspect / clear stored credentials."""
from __future__ import annotations

import sys
import tomllib

from .init_cmd import DEFAULT_CONFIG_PATH


def whoami_command(_args) -> int:
    if not DEFAULT_CONFIG_PATH.is_file():
        print("(not signed in)")
        return 1
    try:
        with open(DEFAULT_CONFIG_PATH, "rb") as f:
            cfg = tomllib.load(f)
    except Exception as e:
        print(f"✗ Could not read {DEFAULT_CONFIG_PATH}: {e}", file=sys.stderr)
        return 1
    uid = cfg.get("uid") or "(missing)"
    proj = cfg.get("project_id") or "(missing)"
    print(f"uid:        {uid}")
    print(f"project_id: {proj}")
    print(f"config:     {DEFAULT_CONFIG_PATH}")
    return 0


def logout_command(_args) -> int:
    if not DEFAULT_CONFIG_PATH.is_file():
        print("(already signed out)")
        return 0
    DEFAULT_CONFIG_PATH.unlink()
    print(f"✓ Removed {DEFAULT_CONFIG_PATH}")
    return 0

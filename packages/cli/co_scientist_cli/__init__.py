"""co-scientist CLI — install & link the local MCP into Claude Code projects."""
from pathlib import Path

__version__ = "0.0.1"


def repo_root() -> Path:
    """Return the co-scientist repo root.

    Resolves from this module's __file__ location:
        packages/cli/co_scientist_cli/__init__.py → repo/

    For a `pip install -e packages/cli/` install (the v0 distribution), this
    works because setuptools editable installs preserve the source layout.
    """
    return Path(__file__).resolve().parent.parent.parent.parent

"""Detect when the installed co-scientist-local is behind the latest build.

The recurring failure mode: an agent runs a months-old install, hits a bug
that was already fixed upstream, and files a duplicate report (and the new
forcing-function gates never fire because they ship in newer versions). This
surfaces a 'you're out of date — update' nudge at session start.

How the comparison works:
  - The public package is stamped 0.1.YYYYMMDD on every publish
    (scripts/publish-public.sh); the private dev tree stays at 0.0.1.
  - We fetch the latest pyproject.toml from the public GitHub mirror and
    compare the YYYYMMDD integers.
  - update_available is True ONLY when both versions parse as published
    0.1.YYYYMMDD builds and installed < latest. A dev install (0.0.1) or any
    network/parse failure yields False, so we never nag on a false signal.

Everything here is best-effort and never raises. Set the env var
CO_SCIENTIST_SKIP_VERSION_CHECK=1 to skip the network probe (used by tests).
"""
from __future__ import annotations

import os
import re
import urllib.request

_PYPROJECT_URL = (
    "https://raw.githubusercontent.com/k821209/co-scientist-mcp-public/"
    "main/apps/local-mcp/pyproject.toml"
)
_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_PUB_RE = re.compile(r"^0\.1\.(\d{8})$")  # published builds: 0.1.YYYYMMDD


def _checkout_version() -> str | None:
    """Version stamped in the pyproject.toml ON DISK next to this package.

    For an editable install this is the truthful one: `git pull` updates it,
    while `importlib.metadata` is frozen at install time and keeps reporting
    whatever it saw then (0.0.1 for a source install). Reading the file is what
    makes staleness detectable for editable checkouts — see installed_version.
    """
    import pathlib
    pkg_dir = pathlib.Path(__file__).resolve().parent
    for cand in (pkg_dir.parent / "pyproject.toml",          # apps/local-mcp/
                 pkg_dir.parent.parent / "pyproject.toml"):
        try:
            m = _VERSION_RE.search(cand.read_text(encoding="utf-8"))
        except OSError:
            continue
        if m:
            return m.group(1)
    return None


def installed_version() -> str | None:
    """The version this process is actually RUNNING.

    Prefers a published stamp found in the checkout's pyproject.toml over the
    install metadata: an editable install reports the metadata frozen at install
    time (0.0.1), which made `update_available` report False even when the
    checkout was commits behind — the flag then told the user there was nothing
    to pull (feedback 8ddaa8fe8506)."""
    disk = _checkout_version()
    if disk and _PUB_RE.match(disk):
        return disk
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            meta = version("co-scientist-local")
        except PackageNotFoundError:
            meta = None
    except Exception:
        meta = None
    # A published metadata version beats an unstamped dev pyproject.
    if meta and _PUB_RE.match(meta):
        return meta
    return disk or meta


_GIT_SHA_CACHE: str | None | bool = False   # False = not computed yet


def git_sha() -> str | None:
    """Short git sha of the checkout this package is installed from (editable
    installs), else None. The pyproject version is uninformative for source
    installs (always 0.0.1) and collides for same-day publishes — the sha
    pins the exact build. Cached; best-effort."""
    global _GIT_SHA_CACHE
    if _GIT_SHA_CACHE is not False:
        return _GIT_SHA_CACHE  # type: ignore[return-value]
    sha: str | None = None
    try:
        import pathlib
        import subprocess
        pkg_dir = pathlib.Path(__file__).resolve().parent
        out = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            sha = out.stdout.strip() or None
    except Exception:
        sha = None
    _GIT_SHA_CACHE = sha
    return sha


def fetch_latest_version(timeout: float = 2.0) -> str | None:
    try:
        req = urllib.request.Request(
            _PYPROJECT_URL,
            headers={"User-Agent": "co-scientist-version-check/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed trusted URL
            text = resp.read().decode("utf-8")
    except Exception:
        return None
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None


def _date_int(v: str | None) -> int | None:
    if not v:
        return None
    m = _PUB_RE.match(v.strip())
    return int(m.group(1)) if m else None


def _compare(installed: str | None, latest: str | None) -> dict:
    """Pure staleness decision — no network, no env. Always returns a dict.

    `update_available` is True when both sides parse as published builds and
    installed < latest; **None (unknown)** when the installed side can't be
    read as a published build — an unstamped/editable install. Returning False
    there was actively misleading: it said "nothing to update" while the
    checkout was commits behind, so the user's `git pull` looked broken
    (feedback 8ddaa8fe8506). False now means "checked, and current"."""
    inst_d = _date_int(installed)
    late_d = _date_int(latest)
    if inst_d is None:
        # Can't compare — say so instead of implying "current".
        out: dict = {
            "installed_version": installed,
            "latest_version": latest,
            "update_available": None,
        }
        if latest:
            out["update_hint"] = (
                f"can't tell whether this install is current: it reports "
                f"{installed!r}, not a published 0.1.YYYYMMDD build (typical of "
                f"an editable/source install, where `pip install --upgrade` is a "
                f"no-op). Latest published is {latest}. Check the checkout "
                f"itself: `cd ~/co-scientist-mcp-public && git status -sb && "
                f"git pull`, then restart this session. `git_sha` in whoami is "
                f"the reliable identifier for a source install."
            )
        return out
    update = late_d is not None and inst_d < late_d
    out = {
        "installed_version": installed,
        "latest_version": latest,
        "update_available": bool(update),
    }
    if update:
        out["update_hint"] = (
            f"co-scientist-local is out of date (installed {installed}, "
            f"latest {latest}). Recently-reported bugs may already be fixed "
            "upstream. Update before working: "
            "`cd ~/co-scientist-mcp-public && git pull && "
            "pip install -e apps/local-mcp`, then restart this session."
        )
    return out


def check_version(timeout: float = 2.0) -> dict:
    """Best-effort staleness check. Never raises; degrades to
    update_available=False on any failure or when the skip env var is set."""
    if os.environ.get("CO_SCIENTIST_SKIP_VERSION_CHECK"):
        return _compare(installed_version(), None)
    return _compare(installed_version(), fetch_latest_version(timeout=timeout))

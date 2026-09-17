"""Detect when the installed co-scientist-local is behind the latest build.

The recurring failure mode: an agent runs a months-old install, hits a bug
that was already fixed upstream, and files a duplicate report (and the new
forcing-function gates never fire because they ship in newer versions). This
surfaces a 'you're out of date — update' nudge at session start.

How the comparison works:
  - The public package is stamped 0.1.YYYYMMDD on every publish
    (scripts/publish-public.sh); the private dev tree stays at 0.0.1. A SECOND
    build on the same day gets a PEP 440 post-release suffix — 0.1.YYYYMMDD.post1,
    .post2, … — because a date alone made a same-day rebuild invisible: whoami
    reported "checked, and current" to a checkout that was commits behind, which
    is the exact false reassurance this module exists to prevent.
  - We fetch the latest pyproject.toml from the public GitHub mirror and compare
    (date, post) — as a TUPLE, not as strings: lexicographically ".post10" sorts
    before ".post9".
  - update_available is True ONLY when both versions parse as published builds
    and installed < latest. A dev install (0.0.1) or any network/parse failure
    yields False/None, so we never nag on a false signal.

Everything here is best-effort and never raises. Set the env var
CO_SCIENTIST_SKIP_VERSION_CHECK=1 to skip the network probe (used by tests).
"""
from __future__ import annotations

import pathlib

import os
import re
import urllib.request

_PYPROJECT_URL = (
    "https://raw.githubusercontent.com/k821209/co-scientist-mcp-public/"
    "main/apps/local-mcp/pyproject.toml"
)
_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
# Published builds: 0.1.YYYYMMDD, plus .postN for the Nth rebuild that same day.
_PUB_RE = re.compile(r"^0\.1\.(\d{8})(?:\.post(\d+))?$")


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


def runtime_info() -> dict:
    """WHERE this code is running from, and under which interpreter.

    `pip show` reports the metadata frozen at install time — for an editable
    install that is 0.0.1 forever, no matter how many times the checkout is
    pulled. So the user updates the source, believes they are on the new build,
    and keeps running whatever the session actually imported. There was no way
    to answer "what is running right now?" from inside a session at all, and on
    a remote session there is no terminal to go and check with
    (feedback 70b9a76cb2cf).

    Three facts settle it: the directory the module was imported from, the
    interpreter that imported it, and whether that is an editable checkout or a
    copy in site-packages. With `git_sha` alongside, "is my update live?" is a
    single tool call."""
    import pathlib as _pl
    import sys

    pkg_dir = _pl.Path(__file__).resolve().parent
    editable = (pkg_dir.parent / "pyproject.toml").exists()
    out = {
        "package_path": str(pkg_dir),
        "python_executable": sys.executable,
        "install_mode": "editable" if editable else "site-packages",
    }
    if editable:
        # The interpreter is what .mcp.json's `command` has to name. A bare
        # `python3` resolves through PATH, so the server silently fails to start
        # under any shell whose PATH finds a different interpreter — and the
        # user sees "it worked yesterday".
        out["mcp_json_command"] = sys.executable
    else:
        checkout = find_checkout()
        out["dedicated_venv"] = dedicated_venv()
        if checkout is not None:
            out["checkout_on_disk"] = str(checkout)
            w = install_warning("site-packages", str(checkout), sys.executable,
                                dedicated=out["dedicated_venv"])
            if w:
                out["install_warning"] = w
            else:
                out["install_note"] = install_note(str(checkout), sys.executable)
    return out


def dedicated_venv(prefix: str | None = None, base_prefix: str | None = None) -> bool:
    """Is this interpreter a virtualenv of its own — not the base interpreter,
    not a conda env? A pip install into a dedicated venv cannot overwrite what
    other projects run, so a snapshot there is the normal state, not a flip."""
    import sys
    prefix = prefix or sys.prefix
    base = base_prefix or sys.base_prefix
    if prefix == base:
        return False
    return not (pathlib.Path(prefix) / "conda-meta").exists()


def install_note(checkout: str, python: str) -> str:
    """The quiet form of path (a): a checkout exists on this disk, this
    interpreter runs its own copy, and that is by design (a dedicated venv,
    e.g. the harness's). Informational; nothing to restore."""
    return (f"{python} runs its own copy of co-scientist-local (a dedicated venv); "
            f"the checkout at {checkout} is not what runs here, by design. Nothing "
            f"to restore.")


def find_checkout() -> "pathlib.Path | None":
    """A source checkout of the MCP on this machine, if one exists: the
    directory `$CO_SCIENTIST_CHECKOUT` names, else the documented clone path
    `~/co-scientist-mcp-public`. Returns the path holding `apps/local-mcp`."""
    import os
    import pathlib as _pl
    cands = []
    env = os.environ.get("CO_SCIENTIST_CHECKOUT")
    if env:
        cands.append(_pl.Path(env).expanduser())
    cands.append(_pl.Path.home() / "co-scientist-mcp-public")
    for c in cands:
        if (c / "apps" / "local-mcp" / "co_scientist_local" / "__init__.py").is_file():
            return c
    return None


def install_warning(install_mode: str, checkout: str | None, python: str,
                    previous_mode: str | None = None, previous_path: str | None = None,
                    dedicated: bool = False) -> str | None:
    """The line whoami and the session banner print when a snapshot in
    site-packages is what runs while a source checkout sits on disk.

    A `pip install` naming the package's git URL — a dependent's install, a
    second setup, a reinstall after an error — pulls a non-editable snapshot
    and uninstalls the editable one in the same step, reported as success.
    Every project whose .mcp.json names that interpreter then runs the frozen
    copy: edits to the checkout stop taking effect and git_sha goes to None,
    and nothing said so (feedback 30be02eb90d6). None when nothing is wrong.

    Two paths. (b) this project last ran an editable install and now runs
    site-packages: the precise signal, always a warning. (a) site-packages
    while a checkout sits on disk: a warning only in a SHARED environment
    (base interpreter, conda env), where a pip install overwrites what other
    projects run. In a dedicated venv a checkout on the disk is a consumer
    clone or someone else's workflow, and (a) fired on every project set up
    there, every session — which trains people to ignore (b) too (feedback
    c6a20dc0936e). There it is install_note instead."""
    if install_mode == "editable":
        return None
    if previous_mode != "editable" and (not checkout or dedicated):
        return None
    where = checkout or (previous_path and str(pathlib.Path(previous_path).parents[2])) or "<checkout>"
    flip = ""
    if previous_mode == "editable":
        flip = (f" This project last ran an EDITABLE install"
                f"{' at ' + previous_path if previous_path else ''}; the flip was silent.")
    return (f"{python} is running a site-packages SNAPSHOT of co-scientist-local while a "
            f"source checkout exists at {where}.{flip} Edits to the checkout do not take "
            f"effect and git_sha is lost. Restore with: "
            f"{python} -m pip install -e {where}/apps/local-mcp --no-deps  "
            f"(then restart the session). Cause is usually a `pip install` of something "
            f"that names the MCP's git URL, into this environment.")


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


def _version_key(v: str | None) -> tuple[int, int] | None:
    """(YYYYMMDD, post) for a published build, else None.

    A tuple, not an int: two builds published on the same day differ only in the
    post-release number, and comparing dates alone reported them as equal.
    """
    if not v:
        return None
    m = _PUB_RE.match(v.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0))


def _compare(installed: str | None, latest: str | None) -> dict:
    """Pure staleness decision — no network, no env. Always returns a dict.

    `update_available` is True when both sides parse as published builds and
    installed < latest; **None (unknown)** when the installed side can't be
    read as a published build — an unstamped/editable install. Returning False
    there was actively misleading: it said "nothing to update" while the
    checkout was commits behind, so the user's `git pull` looked broken
    (feedback 8ddaa8fe8506). False now means "checked, and current"."""
    inst_d = _version_key(installed)
    late_d = _version_key(latest)
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
                f"{installed!r}, not a published 0.1.YYYYMMDD[.postN] build "
                f"(typical of "
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

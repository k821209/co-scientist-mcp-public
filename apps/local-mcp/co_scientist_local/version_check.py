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
import time as _time
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

# When this module was imported, i.e. when this process fixed the code it runs.
# An editable install resolves to the working tree AT IMPORT TIME and Python
# does not re-import a changed module, so everything shipped after this instant
# is inert for this session — invisibly, because the tools keep answering.
_IMPORTED_AT = _time.time()


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


def live_git_sha(pkg_dir: "pathlib.Path | None" = None) -> str | None:
    """HEAD of the checkout as it is RIGHT NOW — the uncached counterpart to
    `git_sha()`, which answers "what did this session start on?"."""
    import pathlib as _pl
    import subprocess
    pkg_dir = pkg_dir or _pl.Path(__file__).resolve().parent
    try:
        out = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return (out.stdout.strip() or None) if out.returncode == 0 else None
    except Exception:
        return None


def stale_process(
    pkg_dir: "pathlib.Path | None" = None,
    *,
    imported_at: float | None = None,
    baseline_sha: str | None = None,
    current_sha: str | None = None,
) -> dict:
    """Whether this process is still running the code that is on disk.

    The failure this exists for: a session's MCP process started 2026-10-11
    15:39 and the deck-lint fixes landed at 16:32 and 22:05. An editable
    install binds the working tree at import, and a Python process does not
    re-import a changed module, so for three days every lint call returned the
    pre-fix answer — empty warning lists — while `whoami` reported
    `installed_version == latest_version`, `update_available: false`. The deck
    skill treats an empty warning list as a done-gate, so the agent concluded a
    deck with a data row printed underneath a callout was finished, and the
    author had to be the overlap detector again (feedback 3a0bfead07c3).

    The version check structurally cannot see this: it compares the version on
    disk against the published one, and both are the new one. What is stale is
    the PROCESS. Two signals say so, and either is enough:

      - a module file is newer than the moment this module was imported;
      - the checkout's HEAD has moved since the sha this session captured.

    Returns `{}` when there is no checkout to compare against (a site-packages
    install cannot drift this way — its files only change when pip rewrites
    them, which is also true and worth saying, so this still reports).
    """
    import datetime
    import pathlib as _pl
    pkg_dir = pkg_dir or _pl.Path(__file__).resolve().parent
    imported_at = _IMPORTED_AT if imported_at is None else imported_at
    reasons: list[str] = []

    newest_at, newest_name, changed = 0.0, None, 0
    try:
        for path in pkg_dir.rglob("*.py"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            # 1s of slack: files written moments before the import that loaded
            # them are the normal install, not a change.
            if mtime > imported_at + 1.0:
                changed += 1
                if mtime > newest_at:
                    newest_at, newest_name = mtime, path.name
    except OSError:
        pass
    if changed:
        when = datetime.datetime.fromtimestamp(
            newest_at, datetime.timezone.utc).isoformat(timespec="seconds")
        reasons.append(
            f"{changed} module file{'s' if changed > 1 else ''} on disk "
            f"{'are' if changed > 1 else 'is'} newer than this process "
            f"(newest: {newest_name} at {when})")

    baseline = git_sha() if baseline_sha is None else baseline_sha
    current = live_git_sha(pkg_dir) if current_sha is None else current_sha
    if baseline and current and baseline != current:
        reasons.append(f"the checkout is at {current}; this session imported {baseline}")

    imported_iso = datetime.datetime.fromtimestamp(
        imported_at, datetime.timezone.utc).isoformat(timespec="seconds")
    if not reasons:
        return {"stale_process": False}
    return {
        "stale_process": True,
        "stale_hint": (
            f"This session imported the tools at {imported_iso} and has been running "
            f"them ever since: " + "; ".join(reasons) + ". Python cannot re-import a "
            "changed module, so every fix shipped since then is inert HERE while the "
            "tools keep answering normally — an empty warning list from a lint may "
            "mean old code, not a clean result. Tell the user to restart the session; "
            "nothing else clears it. Until they do, treat lint and check results from "
            "this session as unreliable rather than as passes."),
    }


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
        # An editable install is the one that can drift under a live process,
        # and the version check cannot see it. Always report the boolean, so
        # `false` is a statement ("checked, the process matches the disk")
        # rather than an absence.
        out.update(stale_process(pkg_dir))
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


def update_command(python: str | None = None) -> str:
    """The one command that updates this install, whatever kind it is.

    Named here so the hint, the guide and the docs cannot drift from what the
    CLI actually accepts. It takes the interpreter explicitly because the hint
    is read inside a session whose MCP may run under a different one than the
    user's shell — naming the wrong python is how an update lands in an
    environment nothing is wired to.
    """
    import sys
    return f"{python or sys.executable} -m co_scientist_local update"


def _compare(installed: str | None, latest: str | None,
             install_mode: str | None = None, python: str | None = None) -> dict:
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
            # Only an editable install has a checkout to pull; for any other
            # install this reads as a promise about a directory that is not
            # there.
            pull = (" — it pulls the checkout this runs from, since pip "
                    "cannot" if install_mode == "editable" else "")
            out["update_hint"] = (
                f"can't tell whether this install is current: it reports "
                f"{installed!r}, not a published 0.1.YYYYMMDD[.postN] build "
                f"(typical of an editable/source install, where `pip install "
                f"--upgrade` is a no-op). Latest published is {latest}. Update "
                f"with `{update_command(python)}`{pull} — then restart this "
                f"session. `git_sha` in whoami is the reliable identifier for "
                f"a source install."
            )
        return out
    update = late_d is not None and inst_d < late_d
    out = {
        "installed_version": installed,
        "latest_version": latest,
        "update_available": bool(update),
    }
    if update:
        # The hint used to be `cd ~/co-scientist-mcp-public && git pull && pip
        # install -e apps/local-mcp`, which is the recipe for a SOURCE install.
        # A user installed from the one-liner has no such clone, so the only
        # instruction the session ever gave them named a chore that did not
        # apply — and cloning the repo to satisfy it leaves a second copy that
        # then shadows the install (install_warning's whole subject).
        out["update_hint"] = (
            f"co-scientist-local is out of date (installed {installed}, "
            f"latest {latest}). Recently-reported bugs may already be fixed "
            f"upstream. Update before working: `{update_command(python)}`, "
            f"then restart this session."
        )
    return out


def check_version(timeout: float = 2.0) -> dict:
    """Best-effort staleness check. Never raises; degrades to
    update_available=False on any failure or when the skip env var is set."""
    import sys
    mode = "editable" if (pathlib.Path(__file__).resolve().parent.parent
                          / "pyproject.toml").exists() else "site-packages"
    if os.environ.get("CO_SCIENTIST_SKIP_VERSION_CHECK"):
        return _compare(installed_version(), None, mode, sys.executable)
    return _compare(installed_version(), fetch_latest_version(timeout=timeout),
                    mode, sys.executable)

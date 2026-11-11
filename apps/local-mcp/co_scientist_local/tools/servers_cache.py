"""The offline cache the ssh guard reads: `~/.co-scientist/cache/servers.json`.

The guard hook (packages/hooks/pretool_block_ssh_nohup.py, and its Pi port)
reads this FILE instead of the registry so that a Bash call never waits on a
network round-trip. The hook, the Pi extension and the docs all said the MCP
writes it at startup and after add_server/update_server. Nothing did. So the
guard has been failing open on every machine since the cloud rewrite — every
raw `ssh alias "nohup …"` went through — and nobody could see it, because
fail-open is silent by design.

Shape:
    {
      "servers":  [{"alias", "host", "user"}, …],            # account-wide
      "projects": {"<project id>": {"<alias>": "<root>"}},   # per project
      "updated_at": "…"
    }

`projects` carries this project's remote root per server (workdirs.project_root),
which is what lets the guard say "that mkdir is outside this project's
directory". Other projects' entries are kept, so a machine that serves several
projects has all of them.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from ..state import State
from ..util import now_iso


def cache_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CO_SCIENTIST_SERVERS_CACHE",
        str(pathlib.Path.home() / ".co-scientist" / "cache" / "servers.json")))


def build_cache(state: State) -> dict:
    from . import servers as _servers
    from . import workdirs as _workdirs
    servers = _servers.list_servers(state, active_only=True)
    roots = {}
    for s in servers:
        r = _workdirs.project_root(state, s)
        if r.get("root"):
            roots[s["alias"]] = r["root"]
    return {
        "servers": [{"alias": s.get("alias"), "host": s.get("host"), "user": s.get("user")}
                    for s in servers],
        "projects": {state.project_id: roots},
    }


def write_servers_cache(state: State) -> pathlib.Path | None:
    """Merge this project's view into the cache file. Best-effort: never raises
    (a hook that fails open is better than an MCP that fails to start), but
    says so on stderr."""
    path = cache_path()
    try:
        fresh = build_cache(state)
        existing: dict = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError):
                existing = {}
        projects = dict(existing.get("projects") or {})
        projects.update(fresh["projects"])
        doc = {"servers": fresh["servers"], "projects": projects, "updated_at": now_iso()}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
    except Exception as e:
        print(f"co-scientist-local: servers cache not written ({e}) — the ssh guard "
              f"fails open", file=sys.stderr)
        return None


def write_servers_cache_soon(state: State):
    """Write the cache on a background thread; return the thread.

    At startup. Building the cache reads the registry — 0.8 s measured against
    the real backend — and it used to run before the server could answer its
    first request, on every start (a scivo-harness session starts two
    servers). Nothing needs it finished by then: the guard reads the FILE, a
    file from the last session is already there, and the first Bash call of a
    session is seconds away. The same reasoning as the reaper's sweep, a few
    lines below this call in `__main__`.

    Not silent: `write_servers_cache` reports a failure on stderr itself, and
    a thread that dies for another reason says so here.
    """
    import threading

    def run() -> None:
        try:
            write_servers_cache(state)
        except Exception as exc:  # noqa: BLE001
            print(f"co-scientist-local: servers cache not written ({type(exc).__name__}: {exc}) — "
                  "the ssh guard keeps the previous file, or fails open if there is none",
                  file=sys.stderr)

    thread = threading.Thread(target=run, name="servers-cache", daemon=True)
    thread.start()
    return thread

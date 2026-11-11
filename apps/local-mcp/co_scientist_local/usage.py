"""Which tools and skills actually get called — counted, on this machine.

A review on 2026-11-11 asked whether 239 tools and 32 skills were the right
set, and could not say: nothing records what a session uses. The transcripts
on the maintainer's machine were six sessions, all of them development. So
"which of these could go" had no evidence under it, and neither did "which of
these should be loaded first".

One line per call, appended to a file under `~/.co-scientist/usage/`, one file
per month:

    2026-11-11T06:12:03Z <TAB> tool <TAB> update_section <TAB> <project id> <TAB> <host>

What a line carries: when, that it was a tool (or a skill — scivo-harness
writes those, since a skill is read by the host and never reaches this
server), its NAME, the project and the machine. What it never carries: an
argument, a result, a path, a word of anyone's manuscript. It stays on this
machine; nothing here sends it anywhere.

`start` lines say whether a server process was counting at all. A report over
a month in which some servers could not count says so, because "never called"
from a process that was not looking is not a finding.

On by default (`SCIVO_USAGE=off` turns it off) and it never raises: a tool
call that failed because its tally could not be written would be the wrong
way round.
"""
from __future__ import annotations

import ast
import datetime as _dt
import json
import os
import pathlib
import socket
import sys
from collections import Counter

_OFF = ("off", "0", "no", "false")


def enabled() -> bool:
    return (os.environ.get("SCIVO_USAGE", "").strip().lower() or "on") not in _OFF


def directory() -> pathlib.Path:
    override = os.environ.get("SCIVO_USAGE_DIR")
    if override:
        return pathlib.Path(override)
    return pathlib.Path.home() / ".co-scientist" / "usage"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def record(kind: str, name: str, project: str = "", *, when: _dt.datetime | None = None) -> None:
    """Append one line. Never raises, never blocks on anything but a local write."""
    if not enabled():
        return
    try:
        when = when or _now()
        clean = lambda s: str(s).replace("\t", " ").replace("\n", " ")[:120]  # noqa: E731
        line = "\t".join([when.strftime("%Y-%m-%dT%H:%M:%SZ"), clean(kind), clean(name),
                          clean(project), clean(socket.gethostname())]) + "\n"
        folder = directory()
        folder.mkdir(parents=True, exist_ok=True)
        # O_APPEND: several servers write here at once (one per session), and a
        # short line appended in one write does not interleave with another.
        with open(folder / f"{when:%Y-%m}.log", "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:  # noqa: BLE001 — see the module docstring
        pass


def count_calls(mcp, project_id: str, version: str = "") -> bool:
    """Count every tool call this server dispatches. True if it is counting.

    At the one place every call passes: the tool manager's `call_tool`. Not a
    wrapper round each of the 239 functions — the server reads each function's
    signature to build its schema, and a wrapper is a way to get that subtly
    wrong 239 times. The attribute is the library's own and private, so its
    absence is handled: the server runs, nothing is counted, and a `start`
    line says so, which the report then repeats.
    """
    if not enabled():
        return False
    manager = getattr(mcp, "_tool_manager", None)
    dispatch = getattr(manager, "call_tool", None)
    if dispatch is None:
        record("start", "not-counting: this mcp library has no tool manager to count at",
               project_id)
        return False

    # Who is calling. A session's model is "tool". A host that makes calls of
    # its own on a connection of its own — scivo-harness gathering the briefing,
    # or waiting on its web page — says so with SCIVO_USAGE_AS, so that
    # plumbing does not read as a model reaching for `list_servers` forty
    # times a day.
    kind = (os.environ.get("SCIVO_USAGE_AS") or "tool").strip().lower()
    if kind not in ("tool", "harness"):
        kind = "tool"

    async def call_tool(name, *args, **kwargs):
        record(kind, name, project_id)
        return await dispatch(name, *args, **kwargs)

    manager.call_tool = call_tool
    record("start", f"counting {version}".strip(), project_id)
    return True


# ── reading it back ───────────────────────────────────────────────────────

def read(days: int = 30, *, now: _dt.datetime | None = None) -> list[tuple[str, str, str, str, str]]:
    """Lines from the last `days` days: (when, kind, name, project, host)."""
    now = now or _now()
    since = (now - _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    folder = directory()
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("*.log")):
        if path.stem < since[:7]:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0] >= since:
                parts += [""] * (5 - len(parts))
                rows.append(tuple(parts[:5]))
    return rows


def registered_tools() -> set[str]:
    """Every tool the server can register, read from its source."""
    source = pathlib.Path(__file__).with_name("mcp_server.py").read_text(encoding="utf-8")
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool"
                for d in node.decorator_list):
            names.add(node.name)
    return names


def installed_skills() -> set[str]:
    try:
        from .skills_install import find_skills_source
        source = find_skills_source()
    except Exception:  # noqa: BLE001
        source = None
    if not source:
        return set()
    return {p.parent.name for p in pathlib.Path(source).glob("*/SKILL.md")}


def summary(days: int = 30, *, now: _dt.datetime | None = None) -> dict:
    rows = read(days, now=now)
    tools = Counter(name for _, kind, name, _, _ in rows if kind == "tool")
    plumbing = Counter(name for _, kind, name, _, _ in rows if kind == "harness")
    skills = Counter(name for _, kind, name, _, _ in rows if kind == "skill")
    starts = [name for _, kind, name, _, _ in rows if kind == "start"]
    known_tools, known_skills = registered_tools(), installed_skills()
    return {
        "days": days,
        "directory": str(directory()),
        "enabled": enabled(),
        "lines": len(rows),
        "first": min((r[0] for r in rows), default=None),
        "last": max((r[0] for r in rows), default=None),
        "hosts": sorted({r[4] for r in rows if r[4]}),
        "projects": len({r[3] for r in rows if r[3]}),
        "server_starts": len(starts),
        "server_starts_not_counting": sum(1 for s in starts if s.startswith("not-counting")),
        "tools": dict(tools.most_common()),
        # Calls a host made for itself (briefing, page channel). Not the
        # model's choice, so not in `tools` — but a tool the host depends on is
        # not unused either, so it is kept out of "never called".
        "harness_calls": dict(plumbing.most_common()),
        "tools_never_called": sorted(known_tools - set(tools) - set(plumbing)),
        "tools_registered": len(known_tools),
        # A name in the log that the server no longer has: renamed or removed
        # since, and worth seeing rather than silently dropping.
        "tools_called_but_unknown": sorted(set(tools) - known_tools),
        "skills": dict(skills.most_common()),
        # Only a harness session writes skill lines. With none, "never
        # invoked" is not known — the list is None, not every skill.
        "skills_never_invoked": sorted(known_skills - set(skills)) if skills else None,
        "skills_installed": len(known_skills),
    }


def render(s: dict) -> str:
    out = [f"Usage on this machine, last {s['days']} days — {s['directory']}"]
    if not s["enabled"]:
        out.append("Counting is OFF here (SCIVO_USAGE). What follows is what was recorded before.")
    if not s["lines"]:
        out.append("Nothing recorded in that period. That is not 'nothing was used': counting "
                   "starts with the first session on an MCP from 2026-11-11 or later.")
        return "\n".join(out)
    out.append(f"{s['first']} → {s['last']} · {s['server_starts']} server start(s) · "
               f"{s['projects']} project(s) · host(s): {', '.join(s['hosts']) or '?'}")
    if s["server_starts_not_counting"]:
        out.append(f"⚠ {s['server_starts_not_counting']} of those starts could NOT count calls — "
                   "'never called' below is an under-count of use by that much.")
    calls = sum(s["tools"].values())
    out += ["", f"Tools: {len(s['tools'])} of {s['tools_registered']} called, {calls} call(s)"]
    out += [f"  {n:6d}  {name}" for name, n in list(s["tools"].items())[:40]]
    if len(s["tools"]) > 40:
        out.append(f"  …and {len(s['tools']) - 40} more (--json for all)")
    if s["harness_calls"]:
        out += ["", f"Called by the harness itself (briefing, web page), not by a model: "
                    f"{sum(s['harness_calls'].values())} call(s) to "
                    + ", ".join(list(s["harness_calls"])[:12])
                    + (" …" if len(s["harness_calls"]) > 12 else "")]
    never = s["tools_never_called"]
    out += ["", f"Never called here in this period: {len(never)} of {s['tools_registered']}"]
    if len(never) > 60:
        # Early on this is nearly everything, and 250 names is a wall, not a
        # finding. The whole list is one flag away.
        out.append("  " + ", ".join(never[:30]) + f", … and {len(never) - 30} more (--json for all)")
    else:
        out.append("  " + ", ".join(never) if never else "  (none)")
    if s["tools_called_but_unknown"]:
        out += ["", "Called, but not in this server's source (renamed or removed since): "
                + ", ".join(s["tools_called_but_unknown"])]
    out.append("")
    if s["skills_never_invoked"] is None:
        out.append("Skills: COULD NOT ASSESS — no skill invocation is recorded. Skills are counted "
                   "by scivo-harness sessions only; a plain Claude Code or Codex session reads a "
                   "skill without this server seeing it.")
    else:
        out.append(f"Skills: {len(s['skills'])} of {s['skills_installed']} invoked "
                   f"(counted in scivo-harness sessions only)")
        out += [f"  {n:6d}  {name}" for name, n in s["skills"].items()]
        out.append("Never invoked: " + (", ".join(s["skills_never_invoked"]) or "(none)"))
    out += ["", "One machine, one period. A tool nobody called HERE may be the one another "
                "machine's projects depend on — run this there before removing anything."]
    return "\n".join(out)


def cli(argv: list[str]) -> int:
    """`co-scientist-local usage` — what this machine's sessions called."""
    import argparse

    p = argparse.ArgumentParser(
        prog="co-scientist-local usage",
        description="Which tools and skills sessions on this machine called. "
                    "Names and counts only; nothing leaves the machine.")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--json", action="store_true", help="the whole summary as JSON")
    args = p.parse_args(argv)
    s = summary(args.days)
    print(json.dumps(s, indent=2, ensure_ascii=False) if args.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))

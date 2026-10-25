"""`python -m co_scientist_local update` — bring this install up to date.

The package is shipped by continuously republishing a git repository, so every
install goes stale, and until now the only thing that could update one was the
harness (`scivo update`). A Claude Code or Codex user was told, by whoami's own
`update_hint`, to `cd ~/co-scientist-mcp-public && git pull && pip install -e
apps/local-mcp` — a clone the one-line installer never makes and most users do
not have. The nudge named a chore that did not apply to them.

What this does instead is ask the install what it is and do the matching thing:

  - a **site-packages** install (what the one-liner makes) is replaced by a
    pip upgrade from git. No clone, no `-e`, nothing to keep.
  - an **editable** install is a checkout, where `pip install --upgrade` is a
    no-op that reports success — the single most expensive wrong instruction we
    have shipped. There the update is `git pull` in that tree.

Then it re-links the skills, because a new build usually carries new or renamed
skill bundles and the symlinks point at the old package directory.

It upgrades the interpreter the HOST CONFIG names, not the one running this
command. Those differ exactly when it matters: a user runs `pip install -U`
in whatever shell they have, it lands in a different environment, and the
session keeps importing the old copy — "I updated and nothing changed".

The running process cannot swap its own imported modules, so every path ends
by saying to restart the session. That is not a limitation worth hiding: the
version check compares the files on disk, and a session that was not restarted
reports the new version while running the old code.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

DEFAULT_REPO = "https://github.com/k821209/co-scientist-mcp-public.git"


def repo_url() -> str:
    """The git URL to upgrade from. `SCIVO_MCP_REPO` so a fork — and a test —
    can point this at another remote without editing the package."""
    return os.environ.get("SCIVO_MCP_REPO", DEFAULT_REPO)


def pip_spec(repo: str | None = None) -> str:
    """The PEP 508 spec the installer uses, kept identical to install.sh so an
    update cannot land a different distribution than the install did."""
    return (f"co-scientist-local @ git+{repo or repo_url()}"
            "#subdirectory=apps/local-mcp")


def config_interpreter(root: pathlib.Path) -> tuple[str | None, str | None]:
    """(interpreter, which file said so) for the MCP wired into `root`.

    Both host config formats are read: `.mcp.json` (Claude Code, Pi, the
    harness) and `.codex/config.toml`. The TOML is read with a regex rather
    than a parser because tomllib is stdlib only from 3.11 and this has to
    work when run by whatever python the user happens to have — including the
    one that cannot import this package.
    """
    mcp_json = root / ".mcp.json"
    if mcp_json.is_file():
        try:
            servers = (json.loads(mcp_json.read_text(encoding="utf-8")) or {}
                       ).get("mcpServers") or {}
            for key in ("scivo", "co_scientist"):
                cmd = (servers.get(key) or {}).get("command")
                if cmd:
                    return str(cmd), str(mcp_json)
        except (OSError, ValueError):
            pass
    toml = root / ".codex" / "config.toml"
    if toml.is_file():
        try:
            text = toml.read_text(encoding="utf-8")
        except OSError:
            text = ""
        block = re.split(r"^\[mcp_servers\.(?:scivo|co_scientist)\]",
                         text, maxsplit=1, flags=re.M)
        if len(block) > 1:
            m = re.search(r'^\s*command\s*=\s*"([^"]+)"', block[1], re.M)
            if m:
                return m.group(1), str(toml)
    return None, None


def _env() -> dict:
    """The environment for every subprocess here, with PYTHONPATH removed.

    PYTHONPATH is inherited, and it names a DIFFERENT checkout than the
    interpreter's own install — that is what it is for. So the probe of a
    freshly installed venv came back reporting the dev tree it was launched
    from: "editable, sha db0ad55d", for an interpreter holding a published
    site-packages build. It would then have run `git pull` in someone else's
    repository instead of upgrading the install that is actually wired up.

    The question asked here is only ever "what does THIS interpreter have",
    so the path that answers a different question is dropped.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def probe(interpreter: str) -> dict:
    """What that interpreter's install is: install_mode, package_path, version.

    Asked OF that interpreter, in a subprocess — the whole point is that it is
    not this process. A failure here is reported, never guessed at: an
    interpreter that cannot import the package is a broken config, which is a
    different problem from a stale one and wants a different message.
    """
    # `live_git_sha` reads the tree on disk, which for an editable install is
    # the ONLY thing that moves: its version string stays unstamped forever, so
    # comparing versions before and after a `git pull` reports "already
    # current" on a pull that fetched twenty commits.
    code = (
        "import json;"
        "from co_scientist_local.version_check import ("
        "runtime_info, installed_version, live_git_sha);"
        "print(json.dumps(runtime_info() | "
        "{'version': installed_version(), 'git_sha': live_git_sha(), 'ok': True}))"
    )
    done = subprocess.run([interpreter, "-c", code], capture_output=True,
                          text=True, env=_env())
    if done.returncode != 0:
        return {"ok": False, "error": (done.stderr or done.stdout).strip()[-400:]}
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "error": f"unreadable probe output: {done.stdout[-200:]}"}


def upgrade_commands(info: dict, interpreter: str, repo: str | None = None) -> list[dict]:
    """The commands that update THIS install, with why each one.

    Pure, so the branch that matters — editable must not be pip-upgraded — is
    testable without a network or a second environment.
    """
    if info.get("install_mode") == "editable":
        pkg = pathlib.Path(info.get("package_path", "."))
        # …/<checkout>/apps/local-mcp/co_scientist_local → <checkout>
        checkout = pkg.parent.parent.parent
        return [{
            "argv": ["git", "-C", str(checkout), "pull", "--ff-only"],
            "why": f"editable install over {checkout}; pip --upgrade is a no-op here",
        }]
    return [{
        "argv": [interpreter, "-m", "pip", "install", "--upgrade", pip_spec(repo)],
        "why": "site-packages install; replaced from git",
    }]


def relink_commands(interpreter: str, root: pathlib.Path, hosts: list[str]) -> list[dict]:
    """Re-link skills (and Codex's hooks) for the hosts wired into `root`.

    A new build is where new skill bundles arrive, and the symlinks in
    .claude/skills point into the package directory that was just replaced.
    Pi is deliberately absent: it loads skills from the package itself, and
    linking Claude Code's path into a Pi project leaves a directory nothing
    reads (the same mistake `wire --host pi` was making).
    """
    out = []
    for host in hosts:
        if host not in ("claude", "codex"):
            continue
        out.append({"argv": [interpreter, "-m", "co_scientist_local",
                             "install-skills", "--host", host, "--dir", str(root)],
                    "why": f"skills for {host}"})
        if host == "codex":
            out.append({"argv": [interpreter, "-m", "co_scientist_local",
                                 "install-hooks", "--host", "codex", "--dir", str(root)],
                        "why": "Codex hooks (session banner, ssh provenance guard)"})
    return out


def cli(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m co_scientist_local update",
        description="update the Scivo MCP this project runs, and re-link its skills")
    p.add_argument("--dir", default=".", help="the project directory (default: cwd)")
    p.add_argument("--python", help="the interpreter to update "
                                    "(default: the one this project's config names)")
    p.add_argument("--check", action="store_true",
                   help="say what would run and what is installed; change nothing")
    p.add_argument("--no-skills", action="store_true",
                   help="update the package only, leaving the skill links alone")
    args = p.parse_args(argv)

    root = pathlib.Path(args.dir).expanduser().resolve()
    interpreter, source = (args.python, "--python") if args.python else config_interpreter(root)
    if not interpreter:
        # Falling back silently to sys.executable is how an update lands in the
        # wrong environment, so say which one is being used and why.
        interpreter, source = sys.executable, "no host config here; this interpreter"
    print(f"interpreter  {interpreter}\n             ({source})")

    info = probe(interpreter)
    if not info.get("ok"):
        print(f"\n  !! {interpreter} cannot import co_scientist_local:\n"
              f"     {info.get('error', '')}\n"
              "     That is a broken config rather than a stale install. Re-run the\n"
              "     installer, or pass --python with the interpreter that has it.",
              file=sys.stderr)
        return 1
    print(f"installed    {info.get('version')} ({info.get('install_mode')})"
          + (f" sha {info['git_sha'][:8]}" if info.get("git_sha") else ""))

    steps = upgrade_commands(info, interpreter)
    if not args.no_skills:
        from .skills_install import hosts_to_refresh
        steps += relink_commands(interpreter, root, hosts_to_refresh(root))

    if args.check:
        print("\nwould run:")
        for step in steps:
            print(f"  {shlex.join(step['argv'])}\n    — {step['why']}")
        return 0

    print()
    failed = 0
    for step in steps:
        done = subprocess.run(step["argv"], capture_output=True, text=True,
                              env=_env())
        mark = "✓" if done.returncode == 0 else "✗"
        print(f"{mark} {step['why']}")
        if done.returncode != 0:
            failed += 1
            print("    " + (done.stderr or done.stdout).strip()[-300:].replace("\n", "\n    "))

    after = probe(interpreter)
    if after.get("ok"):
        same = after.get("version") == info.get("version") and \
            after.get("git_sha") == info.get("git_sha")
        print(f"\nnow          {after.get('version')}"
              + (f" sha {after['git_sha'][:8]}" if after.get("git_sha") else "")
              + ("  (already current)" if same else "  (updated)"))
    # Said on every path, including "already current": the files on disk are
    # what the version check reads, and a live session is still running what it
    # imported at startup.
    print("\nRestart your session for this to take effect.")
    return 1 if failed else 0

"""Install the bundled Claude Code subagent definitions into `.claude/agents/`.

The sibling of `skills_install`, and deliberately separate from it: skills are
DIRECTORIES containing a SKILL.md, agents are FLAT `.md` files, so the discovery
predicate and the link step differ.

Why agents ship at all: `/reviewer-frame-check` needs a subagent whose isolation
is a *capability boundary* rather than a request. Its definition declares
`tools: Read`, so the reviewing agent cannot list a directory or grep the tree and
therefore cannot wander into the analysis outputs that would destroy the check. If
the calling agent hand-assembles that prompt each time, the only thing protecting
the check is the caller's attention — and the caller is, by construction, the agent
that already knows every contaminating fact. Shipping the definition moves the
boundary somewhere it holds without anyone remembering it.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

_PKG_DIR = pathlib.Path(__file__).resolve().parent


def _has_any_agent(d: pathlib.Path) -> bool:
    return d.is_dir() and any(c.suffix == ".md" and c.is_file() for c in d.iterdir())


def find_agents_source() -> pathlib.Path | None:
    """Locate the canonical agents directory — bundled first, then the repo.

    Mirrors `skills_install.find_skills_source`: a wheel / `pip install git+…`
    carries `co_scientist_local/agents/`, while an editable install or a repo
    cloned into the project resolves `packages/agents` two levels up.
    """
    bundled = _PKG_DIR / "agents"
    if _has_any_agent(bundled):
        return bundled
    repo_agents = _PKG_DIR.parents[2] / "packages" / "agents"
    if _has_any_agent(repo_agents):
        return repo_agents
    return None


def _agent_names(source: pathlib.Path) -> list[str]:
    return sorted(c.name for c in source.iterdir()
                  if c.suffix == ".md" and c.is_file())


def install_agents(
    project_dir: pathlib.Path | str = ".",
    *,
    source: pathlib.Path | None = None,
    strategy: str = "symlink",  # or "copy"
) -> dict:
    """Link/copy each bundled agent into `<project_dir>/.claude/agents/`.

    Replaces an existing entry for any of *our* agent names so an upgrade is
    reflected; names outside our set are never touched.
    """
    project_dir = pathlib.Path(project_dir).resolve()
    source = source or find_agents_source()
    # Also covers an explicitly-passed path that does not exist or holds no
    # definitions: iterating it would raise FileNotFoundError instead of
    # returning the documented error dict.
    if source is None or not _has_any_agent(pathlib.Path(source)):
        return {"installed": [], "skipped": [], "source": None,
                "error": "no agents source found"}

    dest_root = project_dir / ".claude" / "agents"
    dest_root.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    skipped: list[str] = []
    for name in _agent_names(source):
        src = source / name
        dst = dest_root / name
        try:
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            elif dst.is_dir():
                shutil.rmtree(dst)
            if strategy == "symlink":
                try:
                    dst.symlink_to(src)
                except OSError:
                    shutil.copy2(src, dst)
            else:
                shutil.copy2(src, dst)
            installed.append(name)
        except OSError as e:
            skipped.append(f"{name}: {e}")

    return {"installed": installed, "skipped": skipped,
            "source": str(source), "dest": str(dest_root), "strategy": strategy}


def install_agents_quietly() -> None:
    """Best-effort install for MCP startup. Never raises; logs to stderr.

    Disable with CO_SCIENTIST_SKIP_AGENT_INSTALL=1.
    """
    if os.environ.get("CO_SCIENTIST_SKIP_AGENT_INSTALL") == "1":
        return
    try:
        res = install_agents(pathlib.Path.cwd())
    except Exception as e:  # never break server startup
        print(f"co-scientist-local: agent install skipped ({e})", file=sys.stderr)
        return
    if res.get("installed"):
        print(
            f"co-scientist-local: linked {len(res['installed'])} agents -> "
            f"{res.get('dest')}",
            file=sys.stderr,
        )
    # A missing agents source is normal on older installs — stay silent.


def cli(argv: list[str]) -> int:
    """`co-scientist-local install-agents` — explicit, pre-launch install."""
    import argparse

    p = argparse.ArgumentParser(
        prog="co-scientist-local install-agents",
        description="Link bundled Claude Code subagents into a project's .claude/agents/",
    )
    p.add_argument("--dir", default=".", help="project dir (default: cwd)")
    p.add_argument("--copy", action="store_true",
                   help="copy definitions instead of symlinking")
    args = p.parse_args(argv)

    res = install_agents(args.dir, strategy="copy" if args.copy else "symlink")
    if res.get("error"):
        print(f"✗ {res['error']}", file=sys.stderr)
        return 1
    print(f"✓ Linked {len(res['installed'])} agents into {res['dest']}")
    print(f"  source: {res['source']} ({res['strategy']})")
    if res["installed"]:
        print("  " + ", ".join(res["installed"]))
    for s in res["skipped"]:
        print(f"  ⚠ {s}", file=sys.stderr)
    return 0

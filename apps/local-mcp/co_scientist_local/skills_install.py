"""Install the bundled skills into a project's skills directory.

The skills (`/paper-deck`, `/paper-export`, …) ship *with* the
co-scientist-local package, so a plain `pip install` carries them. They are
linked into the **project directory** — not a global location — so the session
launched in that directory uses exactly the skill set the project was set up
with. Where they go depends on the host:

    Claude Code   <project>/.claude/skills/
    Codex         <project>/.agents/skills/   (a repo-scope skills root Codex
                                               scans from the project root down
                                               to the cwd; `codex-rs/ext/skills/
                                               src/host_roots.rs`)
    Pi            nowhere — Pi reads them from the installed package.

The SKILL.md files are identical across hosts; only the directory differs.

This runs idempotently on MCP startup (cwd = the project dir) and is also
exposed as `co-scientist-local install-skills [--dir .] [--copy] [--host codex]`.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

_PKG_DIR = pathlib.Path(__file__).resolve().parent


def _has_any_skill(d: pathlib.Path) -> bool:
    return d.is_dir() and any(
        (c / "SKILL.md").is_file() for c in d.iterdir() if c.is_dir()
    )


def find_skills_source() -> pathlib.Path | None:
    """Locate the canonical skills directory.

    1. Bundled inside the installed package (wheel / `pip install git+…`):
       `co_scientist_local/skills/`.
    2. The repo's `packages/skills` — for an editable install *or* a repo
       cloned into the project. `parents[2]` of the package dir is the repo
       root (apps/local-mcp/co_scientist_local → repo).
    """
    bundled = _PKG_DIR / "skills"
    if _has_any_skill(bundled):
        return bundled
    repo_skills = _PKG_DIR.parents[2] / "packages" / "skills"
    if _has_any_skill(repo_skills):
        return repo_skills
    return None


def _skill_names(source: pathlib.Path) -> list[str]:
    """Real skills only (dirs with a SKILL.md) — skips CLAUDE.md.template etc."""
    return sorted(
        c.name
        for c in source.iterdir()
        if c.is_dir() and (c / "SKILL.md").is_file()
    )


SKILL_DEST = {
    "claude": pathlib.Path(".claude") / "skills",
    "codex": pathlib.Path(".agents") / "skills",
}


def install_skills(
    project_dir: pathlib.Path | str = ".",
    *,
    source: pathlib.Path | None = None,
    strategy: str = "symlink",  # or "copy"
    host: str = "claude",
) -> dict:
    """Link/copy each bundled skill into the host's skills dir under `project_dir`.

    Replaces an existing entry for any of *our* skill names (a stale symlink or
    a stale plain-dir copy) so an upgrade / `git pull` is reflected. Names that
    are not part of our set are never touched. Returns a summary dict.
    """
    if host not in SKILL_DEST:
        raise ValueError(f"unknown host {host!r}; one of {sorted(SKILL_DEST)}")
    project_dir = pathlib.Path(project_dir).resolve()
    source = source or find_skills_source()
    # Also covers an explicitly-passed path that does not exist or holds no
    # skills: iterating it would raise FileNotFoundError rather than returning
    # the documented error dict.
    if source is None or not _has_any_skill(pathlib.Path(source)):
        return {"installed": [], "skipped": [], "source": None,
                "error": "no skills source found"}

    dest_root = project_dir / SKILL_DEST[host]
    dest_root.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    skipped: list[str] = []
    for name in _skill_names(source):
        src = source / name
        dst = dest_root / name
        try:
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            elif dst.is_dir():
                shutil.rmtree(dst)
            if strategy == "symlink":
                try:
                    dst.symlink_to(src, target_is_directory=True)
                except OSError:
                    shutil.copytree(src, dst)
            else:
                shutil.copytree(src, dst)
            installed.append(name)
        except OSError as e:
            skipped.append(f"{name}: {e}")

    return {"installed": installed, "skipped": skipped, "host": host,
            "source": str(source), "dest": str(dest_root), "strategy": strategy}


def _claude_code_project(project_dir: pathlib.Path) -> bool:
    """Whether this directory is a Claude Code project.

    `.claude/` and `CLAUDE.md` are both written by `co-scientist link` before the
    MCP ever starts, so their presence is a reliable marker — and their ABSENCE
    means another host launched us. The same MCP now serves Pi (via
    pi-mcp-adapter, same .mcp.json), and Pi reads its skills from
    ~/.pi/agent/skills, never from .claude/. Creating .claude/ there would
    scatter symlinks nothing reads through the user's repo.

    Refresh what exists; never conjure it where it does not.
    """
    return (project_dir / ".claude").is_dir() or (project_dir / "CLAUDE.md").is_file()


def _codex_project(project_dir: pathlib.Path) -> bool:
    """Whether this directory was set up for Codex.

    Same principle as `_claude_code_project`: refresh what the setup script
    created (`.agents/skills`, or a `.codex/` config folder), never conjure it.
    `AGENTS.md` alone is NOT a marker — Pi reads that name too, and a Pi project
    must not grow an `.agents/skills` nothing reads.
    """
    return (project_dir / ".agents" / "skills").is_dir() or (project_dir / ".codex").is_dir()


def hosts_to_refresh(project_dir: pathlib.Path) -> list[str]:
    """Which hosts' skill dirs exist here and should be re-linked on startup.

    A directory can be both (Claude Code and Codex used on the same checkout);
    then both are refreshed, so the two never run different skill versions.
    """
    hosts = []
    if _claude_code_project(project_dir):
        hosts.append("claude")
    if _codex_project(project_dir):
        hosts.append("codex")
    return hosts


def install_skills_quietly() -> None:
    """Best-effort install for MCP startup. Never raises; logs to stderr.

    Disable with CO_SCIENTIST_SKIP_SKILL_INSTALL=1.
    """
    if os.environ.get("CO_SCIENTIST_SKIP_SKILL_INSTALL") == "1":
        return
    cwd = pathlib.Path.cwd()
    for host in hosts_to_refresh(cwd):   # empty under Pi — see _claude_code_project
        try:
            res = install_skills(cwd, host=host)
        except Exception as e:  # never break server startup
            print(f"co-scientist-local: skill install skipped ({e})", file=sys.stderr)
            continue
        if res.get("installed"):
            print(
                f"co-scientist-local: linked {len(res['installed'])} skills -> "
                f"{res.get('dest')}",
                file=sys.stderr,
            )
        elif res.get("error"):
            print(f"co-scientist-local: skills not installed ({res['error']})",
                  file=sys.stderr)


def cli(argv: list[str]) -> int:
    """`co-scientist-local install-skills` — explicit, pre-launch install."""
    import argparse

    p = argparse.ArgumentParser(
        prog="co-scientist-local install-skills",
        description="Link bundled skills into a project's skills dir "
                    "(.claude/skills for Claude Code, .agents/skills for Codex)",
    )
    p.add_argument("--dir", default=".", help="project dir (default: cwd)")
    p.add_argument("--copy", action="store_true",
                   help="copy skills instead of symlinking")
    p.add_argument("--host", default="claude", choices=sorted(SKILL_DEST),
                   help="which host's skills dir to write (default: claude)")
    args = p.parse_args(argv)

    res = install_skills(
        args.dir, strategy="copy" if args.copy else "symlink", host=args.host,
    )
    if res.get("error"):
        print(f"✗ {res['error']}", file=sys.stderr)
        return 1
    print(f"✓ Linked {len(res['installed'])} skills into {res['dest']}")
    print(f"  source: {res['source']} ({res['strategy']})")
    if res["installed"]:
        print("  " + ", ".join(res["installed"]))
    for s in res["skipped"]:
        print(f"  ⚠ {s}", file=sys.stderr)
    return 0

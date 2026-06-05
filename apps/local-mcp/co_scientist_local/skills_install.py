"""Install the bundled Claude Code skills into a project's `.claude/skills/`.

The skills (`/paper-deck`, `/paper-export`, …) ship *with* the
co-scientist-local package, so a plain `pip install` carries them. They are
linked into the **project directory's** `.claude/skills/` — not the global
`~/.claude/skills/` — so the Claude Code session launched in that directory
uses exactly the skill set the project was set up with.

This runs idempotently on MCP startup (cwd = the project dir) and is also
exposed as `co-scientist-local install-skills [--dir .] [--copy]`.
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


def install_skills(
    project_dir: pathlib.Path | str = ".",
    *,
    source: pathlib.Path | None = None,
    strategy: str = "symlink",  # or "copy"
) -> dict:
    """Link/copy each bundled skill into `<project_dir>/.claude/skills/`.

    Replaces an existing entry for any of *our* skill names (a stale symlink or
    a stale plain-dir copy) so an upgrade / `git pull` is reflected. Names that
    are not part of our set are never touched. Returns a summary dict.
    """
    project_dir = pathlib.Path(project_dir).resolve()
    source = source or find_skills_source()
    if source is None:
        return {"installed": [], "skipped": [], "source": None,
                "error": "no skills source found"}

    dest_root = project_dir / ".claude" / "skills"
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

    return {"installed": installed, "skipped": skipped,
            "source": str(source), "dest": str(dest_root), "strategy": strategy}


def install_skills_quietly() -> None:
    """Best-effort install for MCP startup. Never raises; logs to stderr.

    Disable with CO_SCIENTIST_SKIP_SKILL_INSTALL=1.
    """
    if os.environ.get("CO_SCIENTIST_SKIP_SKILL_INSTALL") == "1":
        return
    try:
        res = install_skills(pathlib.Path.cwd())
    except Exception as e:  # never break server startup
        print(f"co-scientist-local: skill install skipped ({e})", file=sys.stderr)
        return
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
        description="Link bundled Claude Code skills into a project's .claude/skills/",
    )
    p.add_argument("--dir", default=".", help="project dir (default: cwd)")
    p.add_argument("--copy", action="store_true",
                   help="copy skills instead of symlinking")
    args = p.parse_args(argv)

    res = install_skills(
        args.dir, strategy="copy" if args.copy else "symlink",
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

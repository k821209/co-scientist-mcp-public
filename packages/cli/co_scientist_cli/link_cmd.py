"""`co-scientist link` — set up the current directory as a Claude Code project.

Writes:
- .mcp.json (declares the co_scientist stdio MCP server)
- .claude/settings.json (permissions allowlist + hooks with absolute paths)
- .claude/skills → symlink to packages/skills (or copy if symlinking fails)
- CLAUDE.md (from packages/skills/CLAUDE.md.template)
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

from . import repo_root


def _hooks_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "packages" / "hooks"


def _skills_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "packages" / "skills"


def _make_settings(hooks_dir: pathlib.Path) -> dict:
    """Build .claude/settings.json — same shape as the original co-scientist."""
    def hook(name: str, timeout: int) -> dict:
        return {
            "type": "command",
            "command": str(hooks_dir / f"{name}.py"),
            "timeout": timeout,
        }
    return {
        "permissions": {
            "allow": [
                "mcp__co_scientist__*",
                "Read", "Glob", "Grep", "WebSearch", "WebFetch",
            ],
        },
        "hooks": {
            "SessionStart": [
                {"hooks": [hook("session_start", 5000)]},
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        hook("pretool_block_ssh_nohup", 3000),
                        hook("pretool_cutadapt_lint", 2000),
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "mcp__co_scientist__*",
                    "hooks": [hook("post_tool", 3000)],
                },
            ],
        },
    }


_MCP_JSON = {
    "mcpServers": {
        "co_scientist": {
            "type": "stdio",
            "command": "python3",
            "args": ["-m", "co_scientist_local"],
        },
    },
}


def do_link(
    target_dir: pathlib.Path,
    *,
    root: pathlib.Path | None = None,
    paper_slug: str | None = None,
    skills_strategy: str = "symlink",  # or "copy"
) -> dict:
    """Set up `target_dir` as a co-scientist Claude Code project.

    Returns: {target_dir, files_written, skills_strategy}
    """
    root = root or repo_root()
    target_dir = target_dir.resolve()
    if not target_dir.is_dir():
        raise FileNotFoundError(f"target dir does not exist: {target_dir}")

    hooks = _hooks_dir(root)
    skills = _skills_dir(root)
    template = skills / "CLAUDE.md.template"
    if not template.is_file():
        raise FileNotFoundError(f"CLAUDE.md template not found at {template}")
    if not hooks.is_dir():
        raise FileNotFoundError(f"hooks dir not found at {hooks}")

    files_written: list[str] = []

    # .mcp.json
    mcp_path = target_dir / ".mcp.json"
    mcp_path.write_text(json.dumps(_MCP_JSON, indent=2) + "\n")
    files_written.append(".mcp.json")

    # .claude/settings.json
    claude_dir = target_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings = _make_settings(hooks)
    (claude_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    files_written.append(".claude/settings.json")

    # .claude/skills
    skills_link = claude_dir / "skills"
    if skills_link.exists() or skills_link.is_symlink():
        if skills_link.is_symlink() or skills_link.is_dir():
            if skills_link.is_symlink():
                skills_link.unlink()
            else:
                shutil.rmtree(skills_link)
    strategy_used = skills_strategy
    if skills_strategy == "symlink":
        try:
            skills_link.symlink_to(skills, target_is_directory=True)
        except OSError:
            shutil.copytree(skills, skills_link)
            strategy_used = "copy (symlink failed)"
    else:
        shutil.copytree(skills, skills_link)
    files_written.append(f".claude/skills ({strategy_used})")

    # CLAUDE.md
    (target_dir / "CLAUDE.md").write_text(template.read_text())
    files_written.append("CLAUDE.md")

    # Paper-slug marker (optional)
    if paper_slug:
        (target_dir / ".co-scientist-paper").write_text(paper_slug + "\n")
        files_written.append(".co-scientist-paper")

    return {
        "target_dir": str(target_dir),
        "files_written": files_written,
        "skills_strategy": strategy_used,
    }


def link_command(args) -> int:
    target = pathlib.Path(args.dir or ".").resolve()
    try:
        result = do_link(
            target,
            paper_slug=args.slug,
            skills_strategy=args.skills,
        )
    except FileNotFoundError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    for f in result["files_written"]:
        print(f"✓ Wrote {result['target_dir']}/{f}")
    print()
    print(f"Ready. Open Claude Code in {result['target_dir']} and try:")
    print("  /paper-writing \"Your paper title\"")
    return 0

"""`co-scientist` console script entry point.

Usage:
    co-scientist init [--email EMAIL] [--password PASSWORD] [--image-gen-mode {disabled,local,cloud}] [--gemini-api-key KEY]
    co-scientist link [--dir PATH] [--slug SLUG] [--skills {symlink,copy}]
    co-scientist auth whoami
    co-scientist auth logout
"""
from __future__ import annotations

import argparse
import sys

from .auth_cmd import logout_command, whoami_command
from .init_cmd import init_command
from .link_cmd import link_command


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="co-scientist")
    subs = p.add_subparsers(dest="cmd", required=True)

    # init
    init = subs.add_parser("init", help="Sign in to Firebase + write config.toml")
    init.add_argument("--email", default=None)
    init.add_argument("--password", default=None)
    init.add_argument(
        "--image-gen-mode", choices=("disabled", "local", "cloud"), default="disabled",
    )
    init.add_argument("--gemini-api-key", default=None)
    init.set_defaults(func=init_command)

    # link
    link = subs.add_parser("link", help="Set up current dir as a Claude Code project")
    link.add_argument("--dir", default=".")
    link.add_argument("--slug", default=None, help="Optional paper slug marker file")
    link.add_argument("--skills", choices=("symlink", "copy"), default="symlink")
    link.set_defaults(func=link_command)

    # auth
    auth = subs.add_parser("auth", help="Inspect / clear credentials")
    auth_subs = auth.add_subparsers(dest="auth_cmd", required=True)
    auth_subs.add_parser("whoami").set_defaults(func=whoami_command)
    auth_subs.add_parser("logout").set_defaults(func=logout_command)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

"""`co-scientist init` — first-time setup: sign in, write config.toml."""
from __future__ import annotations

import getpass
import json
import os
import pathlib
import stat
import sys

from . import repo_root
from .firebase_auth import HttpPost, SignInError, sign_in_email_password


DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".co-scientist" / "config.toml"


def _load_firebase_config(root: pathlib.Path) -> dict:
    p = root / "apps" / "web" / ".firebase-config.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"Firebase config not found at {p}. Run from the co-scientist repo "
            "or set apps/web/.firebase-config.json manually."
        )
    return json.loads(p.read_text())


def _write_config_toml(path: pathlib.Path, data: dict) -> None:
    """Write a config.toml file. We hand-roll the TOML to keep zero deps."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    flat = {k: v for k, v in data.items() if not isinstance(v, dict)}
    sections = {k: v for k, v in data.items() if isinstance(v, dict)}
    for k, v in flat.items():
        if isinstance(v, str):
            esc = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{esc}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    for section, fields in sections.items():
        lines.append("")
        lines.append(f"[{section}]")
        for k, v in fields.items():
            if isinstance(v, str):
                esc = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{esc}"')
            else:
                lines.append(f"{k} = {v}")
    path.write_text("\n".join(lines) + "\n")
    # Restrict to user-only — the refresh_token is sensitive
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        os.chmod(path.parent, stat.S_IRWXU)
    except OSError:
        pass  # non-Unix; best effort


def do_init(
    *,
    email: str,
    password: str,
    root: pathlib.Path | None = None,
    config_path: pathlib.Path | None = None,
    http_post: HttpPost | None = None,
    image_gen_mode: str = "disabled",
    gemini_api_key: str = "",
) -> dict:
    """Headless init — for tests and scripted setup.

    Returns: {uid, email, config_path}
    """
    root = root or repo_root()
    config_path = config_path or DEFAULT_CONFIG_PATH
    fb_cfg = _load_firebase_config(root)
    result = sign_in_email_password(
        email=email, password=password,
        web_api_key=fb_cfg["apiKey"], http_post=http_post,
    )
    config = {
        "uid": result["localId"],
        "web_api_key": fb_cfg["apiKey"],
        "refresh_token": result["refreshToken"],
        "project_id": fb_cfg["projectId"],
        "storage_bucket": fb_cfg["storageBucket"],
        "credentials_path": "",
        "image_gen_mode": image_gen_mode,
        "gemini_api_key": gemini_api_key,
        "function_urls": {
            "generate_image": (
                f"https://us-central1-{fb_cfg['projectId']}.cloudfunctions.net/generate_image"
            ),
        },
    }
    _write_config_toml(config_path, config)
    return {
        "uid": result["localId"],
        "email": result.get("email") or email,
        "config_path": str(config_path),
    }


def init_command(args) -> int:
    """Interactive entry point for `co-scientist init`."""
    root = repo_root()
    try:
        fb_cfg = _load_firebase_config(root)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"co-scientist init — project {fb_cfg['projectId']!r}")
    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")

    try:
        result = do_init(
            email=email, password=password,
            image_gen_mode=args.image_gen_mode,
            gemini_api_key=args.gemini_api_key or "",
        )
    except SignInError as e:
        print(f"✗ Sign-in failed: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    print(f"✓ Signed in as {result['email']} (uid: {result['uid']})")
    print(f"✓ Wrote {result['config_path']} (chmod 600)")
    print()
    print("To set up a paper project, cd into a directory and run:")
    print("  co-scientist link")
    return 0

"""Config loader for the local MCP.

Reads `~/.co-scientist/config.toml`, written by `co-scientist init`. Shape:

    uid = "abc123"
    web_api_key = "AIzaSy..."
    refresh_token = "..."
    project_id = "co-scientist-prod"
    storage_bucket = "co-scientist-prod.appspot.com"
    image_gen_mode = "cloud"      # or "local"
    gemini_api_key = ""           # required when image_gen_mode = "local"

    [function_urls]
    generate_image = "https://us-central1-co-scientist-prod.cloudfunctions.net/generate_image"

The web_api_key and project_id are not secrets (they ship in every Firebase
frontend bundle). The refresh_token IS sensitive — keep ~/.co-scientist/
readable only by the user (mode 0700).
"""
from __future__ import annotations

import pathlib
import tomllib

DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".co-scientist" / "config.toml"

REQUIRED_FIELDS = (
    "uid",
    "web_api_key",
    "refresh_token",
    "project_id",
    "storage_bucket",
)

VALID_IMAGE_GEN_MODES = {"local", "openai", "cloud", "disabled"}


def load_config(path: str | pathlib.Path | None = None) -> dict:
    """Load and parse the config file. Does NOT validate — call validate_config."""
    p = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.is_file():
        raise FileNotFoundError(f"config file not found: {p}")
    with open(p, "rb") as f:
        return tomllib.load(f)


def validate_config(cfg: dict) -> list[str]:
    """Return a list of validation errors (empty if all good)."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not cfg.get(field):
            errors.append(f"missing required field: {field!r}")
    mode = cfg.get("image_gen_mode", "disabled")
    if mode not in VALID_IMAGE_GEN_MODES:
        errors.append(
            f"image_gen_mode={mode!r} must be one of {sorted(VALID_IMAGE_GEN_MODES)}"
        )
    if mode == "local" and not cfg.get("gemini_api_key"):
        errors.append("image_gen_mode='local' requires gemini_api_key")
    if mode == "openai" and not cfg.get("openai_api_key"):
        errors.append("image_gen_mode='openai' requires openai_api_key")
    if mode == "cloud":
        urls = cfg.get("function_urls") or {}
        if not urls.get("generate_image"):
            errors.append("image_gen_mode='cloud' requires function_urls.generate_image")
    return errors


def load_and_validate(path: str | pathlib.Path | None = None) -> dict:
    """Convenience: load + validate, raise on any error."""
    cfg = load_config(path)
    errors = validate_config(cfg)
    if errors:
        raise ValueError(
            "config is invalid:\n  - " + "\n  - ".join(errors)
        )
    return cfg

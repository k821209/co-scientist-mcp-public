"""Entry point: `python -m co_scientist_local`.

Startup modes, in priority order:

  1. **Memory** (CO_SCIENTIST_USE_MEMORY=1) — InMemoryBackend, no network.
  2. **API-key mode** (CO_SCIENTIST_API_KEY set) — preferred multi-user path.
     Exchanges the key via /exchange_key Cloud Function, signs in with the
     resulting custom token, uses the ID token for all Firestore + Storage
     writes. Security rules enforce per-project scope.
  3. **Service-account mode** (GOOGLE_APPLICATION_CREDENTIALS + CO_SCIENTIST_PROJECT_ID)
     — developer / smoke fallback. Bypasses rules. End users never need this.

Env vars per mode:

    API-key mode:
        CO_SCIENTIST_API_KEY          per-project API key from the dashboard
        FIREBASE_PROJECT_ID           the Firebase project (e.g. co-scientist-5af1a)
        FIREBASE_STORAGE_BUCKET       the bucket
        FIREBASE_WEB_API_KEY          public web SDK API key (Identity Toolkit)
        CO_SCIENTIST_EXCHANGE_URL     [optional] override the default Cloud Function URL

    Service-account mode (developer):
        CO_SCIENTIST_PROJECT_ID, FIREBASE_PROJECT_ID, FIREBASE_STORAGE_BUCKET,
        GOOGLE_APPLICATION_CREDENTIALS
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

from .backends import InMemoryBackend
from .state import State


# The project context file, by host. Claude Code and Pi read CLAUDE.md; Codex
# reads AGENTS.md only (its fallback filename list is empty by default —
# `codex-rs/config/src/config_toml.rs`), so the Codex setup writes that name.
_CONTEXT_FILES = ("CLAUDE.md", "AGENTS.md")


LEGACY_SERVER_KEY = "co_scientist"
SERVER_KEY = "scivo"


def detect_legacy_server_key(project_dir: pathlib.Path) -> str | None:
    """The config file that still names the server `co_scientist`, or None.

    The skills call `mcp__scivo__*` since 2026-09-09; a config from before
    that exposes the tools as `mcp__co_scientist__*`, and every skill's tool
    reference misses — which reads as "the tools are gone". Checked here, at
    the one moment the MCP is certainly running under that config."""
    mcp_json = project_dir / ".mcp.json"
    if mcp_json.is_file():
        try:
            servers = (json.loads(mcp_json.read_text(encoding="utf-8")) or {}).get("mcpServers") or {}
            if LEGACY_SERVER_KEY in servers and SERVER_KEY not in servers:
                return str(mcp_json)
        except (OSError, ValueError):
            pass
    toml = project_dir / ".codex" / "config.toml"
    if toml.is_file():
        try:
            text = toml.read_text(encoding="utf-8")
            if re.search(r"^\[mcp_servers\.co_scientist\]", text, re.M) and \
               not re.search(r"^\[mcp_servers\.scivo\]", text, re.M):
                return str(toml)
        except OSError:
            pass
    return None


def _warn_legacy_server_key() -> None:
    hit = detect_legacy_server_key(pathlib.Path.cwd())
    if hit:
        sys.stderr.write(
            "\n"
            "  ╭─ ⚠  MCP server key is still `co_scientist` ───────────────────╮\n"
            f"  │  {hit[-58:]:<62} │\n"
            "  │  The skills call mcp__scivo__* now. Rename the key to `scivo`  │\n"
            "  │  (or re-run the Setup tab script) and restart the session.     │\n"
            "  ╰────────────────────────────────────────────────────────────────╯\n\n"
        )


def _check_claude_md_project_id(state: State) -> None:
    """Compare the project context file's stated project id (if any) against
    the one the MCP actually authenticated to. A mismatch usually means the
    user mixed the MCP config and the context file from two different
    dashboard projects — the source of the long-running 'paper not found' bug.

    Prints a prominent banner to stderr; doesn't fail startup so the
    user can still operate (just with the wrong project bound).
    """
    cwd = pathlib.Path.cwd()
    ctx = next((cwd / n for n in _CONTEXT_FILES if (cwd / n).is_file()), None)
    if ctx is None:
        return
    try:
        text = ctx.read_text(encoding="utf-8")
    except OSError:
        return
    # The dashboard template writes `Project id: \`<pid>\``; older
    # templates may say `id: \`<pid>\`` or embed the pid in the heading.
    pid_pattern = re.compile(r"[Pp]roject\s+id\s*:\s*`([a-zA-Z0-9_-]+)`")
    m = pid_pattern.search(text)
    claimed = m.group(1) if m else None
    if claimed is None:
        return
    if claimed != state.project_id:
        name = ctx.name
        sys.stderr.write(
            "\n"
            f"  ╭─ ⚠  {name} / API key mismatch ─────────────────────────────╮\n"
            f"  │  {name:<9} project_id : {claimed:<36} │\n"
            f"  │  MCP authenticated as : {state.project_id:<36} │\n"
            "  │                                                                │\n"
            "  │  These should match. You probably mixed the MCP config and     │\n"
            f"  │  {name:<9} from two different dashboard projects. Re-download │\n"
            "  │  setup-<slug>.sh from a single project's Setup tab to fix.     │\n"
            "  ╰────────────────────────────────────────────────────────────────╯\n\n"
        )


def _build_dev_state() -> State:
    pid = os.environ.get("CO_SCIENTIST_PROJECT_ID", "dev-project")
    uid = os.environ.get("CO_SCIENTIST_UID", "local-dev")
    return State(project_id=pid, owner_uid=uid, backend=InMemoryBackend())


def _build_api_key_state() -> State:
    """Preferred multi-user path: API key → custom token → ID token → Firestore."""
    from .auth import (
        FirebaseAuthClient,
        HttpCustomTokenSignIn,
        exchange_api_key,
    )
    from .backends.firestore import FirestoreBackend
    from .image_gen import CloudFunctionImageGenerator

    from .constants import (
        DEFAULT_EXCHANGE_URL_TEMPLATE,
        DEFAULT_FIREBASE_PROJECT_ID,
        DEFAULT_FIREBASE_STORAGE_BUCKET,
        DEFAULT_FIREBASE_WEB_API_KEY,
        DEFAULT_GENERATE_IMAGE_URL_TEMPLATE,
    )

    api_key = os.environ["CO_SCIENTIST_API_KEY"]
    # Only the API key is user-specific. The Firebase project/bucket/web-key are
    # constants of the hosted service; defaults are baked into constants.py and
    # can be overridden via env (for self-hosted forks).
    fb_project = os.environ.get("FIREBASE_PROJECT_ID", DEFAULT_FIREBASE_PROJECT_ID)
    bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", DEFAULT_FIREBASE_STORAGE_BUCKET)
    web_api_key = os.environ.get("FIREBASE_WEB_API_KEY", DEFAULT_FIREBASE_WEB_API_KEY)
    exchange_url = os.environ.get(
        "CO_SCIENTIST_EXCHANGE_URL",
        DEFAULT_EXCHANGE_URL_TEMPLATE.format(project_id=fb_project),
    )

    # 1. Exchange API key for custom token + project/owner ids
    exch = exchange_api_key(api_key=api_key, exchange_url=exchange_url)
    project_id = exch["projectId"]
    owner_uid = exch["ownerUid"]

    # 2. Custom token → ID token + refresh token
    signin = HttpCustomTokenSignIn().sign_in(exch["customToken"], web_api_key)

    # 3. Auth client seeded with the initial token
    auth_client = FirebaseAuthClient(
        web_api_key=web_api_key,
        refresh_token=signin["refreshToken"],
        initial_id_token=signin["idToken"],
        initial_expires_in=int(signin.get("expiresIn", 3600)),
    )

    # 4. FirestoreBackend authenticated as the user
    backend = FirestoreBackend(
        project_id=fb_project,
        bucket_name=bucket,
        user_token_provider=auth_client.get_id_token,
    )

    # 5. Image generator — always the Cloud Function. The function gates on
    #    plan_id (free → 403, Pro+ → quota check → gpt-image-2). Free-tier
    #    users who want image generation wire up their own provider through
    #    Claude Code (other MCPs / built-in tools) — outside our scope.
    gen_image_url = os.environ.get(
        "CO_SCIENTIST_GENERATE_IMAGE_URL",
        DEFAULT_GENERATE_IMAGE_URL_TEMPLATE.format(project_id=fb_project),
    )
    image_gen = CloudFunctionImageGenerator(
        function_url=gen_image_url,
        get_id_token=auth_client.get_id_token,
    )

    return State(
        project_id=project_id, owner_uid=owner_uid, backend=backend,
        image_gen=image_gen,
    )


def _build_service_account_state() -> State:
    """Developer fallback: service-account JSON, bypasses rules."""
    from .backends.firestore import FirestoreBackend

    pid = os.environ["CO_SCIENTIST_PROJECT_ID"]
    fb_project = os.environ["FIREBASE_PROJECT_ID"]
    bucket = os.environ["FIREBASE_STORAGE_BUCKET"]
    backend = FirestoreBackend(project_id=fb_project, bucket_name=bucket)

    project_doc = backend.get_doc(f"projects/{pid}")
    if project_doc is None:
        raise RuntimeError(
            f"project {pid!r} not found in Firestore. Create it via the dashboard first."
        )
    owner_uid = project_doc.get("owner_uid")
    if not owner_uid:
        raise RuntimeError(f"project {pid!r} has no owner_uid set")
    return State(project_id=pid, owner_uid=owner_uid, backend=backend)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "install-skills":
        from .skills_install import cli as _install_skills_cli
        sys.exit(_install_skills_cli(argv[1:]))
    if argv and argv[0] == "install-agents":
        from .agents_install import cli as _install_agents_cli
        sys.exit(_install_agents_cli(argv[1:]))
    if argv and argv[0] == "install-hooks":
        from .hooks_install import cli as _install_hooks_cli
        sys.exit(_install_hooks_cli(argv[1:]))

    if os.environ.get("CO_SCIENTIST_USE_MEMORY") == "1":
        state = _build_dev_state()
        print("co-scientist-local: in-memory (dev mode)", file=sys.stderr)
    elif os.environ.get("CO_SCIENTIST_API_KEY"):
        try:
            state = _build_api_key_state()
        except (KeyError, RuntimeError) as e:
            print(f"co-scientist-local: {e}", file=sys.stderr)
            sys.exit(2)
        print(
            f"co-scientist-local: token-auth, "
            f"project={state.project_id}, owner={state.owner_uid}",
            file=sys.stderr,
        )
        _check_claude_md_project_id(state)
        _warn_legacy_server_key()
    elif os.environ.get("CO_SCIENTIST_PROJECT_ID") and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            state = _build_service_account_state()
        except (KeyError, RuntimeError) as e:
            print(f"co-scientist-local: {e}", file=sys.stderr)
            sys.exit(2)
        print(
            f"co-scientist-local: service-account (developer fallback), "
            f"project={state.project_id}, owner={state.owner_uid}",
            file=sys.stderr,
        )
    else:
        print(
            "co-scientist-local: no credentials.\n"
            "Set CO_SCIENTIST_API_KEY (preferred) and FIREBASE_* env vars,\n"
            "or CO_SCIENTIST_USE_MEMORY=1 for dev mode.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Link bundled skills + subagents into this project's .claude/ (best-effort;
    # cwd is the project dir). Takes effect on the next Claude Code launch.
    from .skills_install import install_skills_quietly
    install_skills_quietly()
    # The ssh guard reads ~/.co-scientist/cache/servers.json; this is the write
    # the hook, the Pi extension and the docs always said happened here.
    from .tools.servers_cache import write_servers_cache
    write_servers_cache(state)
    from .agents_install import install_agents_quietly
    install_agents_quietly()

    # Start the background reaper, which ALSO does the one-shot sweep for local
    # jobs that died while no session was running. Deliberately not awaited here:
    # that sweep is O(papers × analyses) sequential Firestore round-trips, and
    # doing it before mcp.run() delayed the stdio server's first response by that
    # whole time — a server Claude Code reports as "still connecting"
    # (feedback bfa97278f680). Nothing needs it finished before the first call.
    from .tools.runs import start_local_reaper
    start_local_reaper(state)

    from .mcp_server import build_mcp
    mcp = build_mcp(state)
    mcp.run()


if __name__ == "__main__":
    main()

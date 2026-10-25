#!/bin/sh
# Scivo — one-line install.
#
#   curl -fsSL https://scivo.newgenes.me/install.sh | sh -s -- --project <pid> --key <key>
#
# Or, if you would rather read it first (the same thing, two lines):
#
#   curl -fsSL https://scivo.newgenes.me/install.sh -o scivo-install.sh
#   sh scivo-install.sh --project <pid> --key <key>
#
# What it replaces: four steps in the dashboard's Setup tab — a virtualenv, a
# pip install from git, a symlink onto PATH, and then the wiring command — of
# which the first three exist only because "which python3?" has no good answer
# on a machine with several. This script answers it once by making one.
#
# What it deliberately does NOT do:
#   · install Claude Code (or Codex, or Pi). Signing in belongs to that vendor
#     and Anthropic's terms require it to happen through their own flow, so the
#     script checks and tells you, rather than reaching for your credentials.
#   · decide anything per host. It asks the package: `co_scientist_local wire`
#     reads the host table and writes that host's config. Branching in shell is
#     a `case` statement nothing tests.
#
# POSIX sh on purpose: it is piped into `sh`, which on Debian/Ubuntu is dash.
set -eu

HOST=claude
PROJECT=
KEY=${CO_SCIENTIST_API_KEY:-}
DIR=.
VENV=${SCIVO_VENV:-$HOME/.scivo}
BIN=$HOME/.local/bin
REPO=${SCIVO_MCP_REPO:-https://github.com/k821209/co-scientist-mcp-public.git}
HARNESS_REPO=${SCIVO_HARNESS_REPO:-https://github.com/k821209/scivo-harness.git}
FORCE=

usage() {
  cat <<'USAGE'
Usage: install.sh [--host claude|codex|pi|harness] [--project <pid>] [--key <key>] [--dir <path>] [--force]

  --host     the agent you will run Scivo from (default: claude)
  --project  the project id, from the dashboard's Setup tab
  --key      that project's API key; or export CO_SCIENTIST_API_KEY.
             Left out, you are prompted — which keeps it out of your shell history.
  --dir      the project directory to wire (default: the current one)
  --force    replace an existing host config
USAGE
}

while [ $# -gt 0 ]; do
  case $1 in
    --host) HOST=$2; shift 2 ;;
    --host=*) HOST=${1#*=}; shift ;;
    --project) PROJECT=$2; shift 2 ;;
    --project=*) PROJECT=${1#*=}; shift ;;
    --key) KEY=$2; shift 2 ;;
    --key=*) KEY=${1#*=}; shift ;;
    --dir) DIR=$2; shift 2 ;;
    --dir=*) DIR=${1#*=}; shift ;;
    --force) FORCE=--force; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

say() { printf '  %s\n' "$*"; }
die() { printf '\n  %s\n' "$*" >&2; exit 1; }

# ── python ───────────────────────────────────────────────────────────────────
PY=
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
      PY=$candidate
      break
    fi
  fi
done
[ -n "$PY" ] || die "no python3.11+ found. Install Python 3.11 or newer and run this again."

# ── the one interpreter ──────────────────────────────────────────────────────
# Every "which python3?" paragraph in the Setup tab exists because the answer
# differs between shells. A virtualenv of our own is the answer, and its full
# path is what goes into the host's config.
if [ ! -x "$VENV/bin/python" ]; then
  say "creating $VENV"
  "$PY" -m venv "$VENV" || die "could not create $VENV (python3-venv installed?)"
fi
say "installing the Scivo MCP"
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VENV/bin/pip" install --quiet --upgrade \
  "co-scientist-local @ git+$REPO#subdirectory=apps/local-mcp" \
  || die "pip install failed — scroll up for why"

if [ "$HOST" = harness ]; then
  say "installing the harness"
  "$VENV/bin/pip" install --quiet --upgrade "scivo-harness @ git+$HARNESS_REPO" \
    || die "pip install (harness) failed"
  mkdir -p "$BIN"
  ln -sf "$VENV/bin/scivo" "$BIN/scivo"
  case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "note: $BIN is not on PATH — add it, or run $BIN/scivo by full path" ;;
  esac
fi

# ── the key, asked for rather than left in history ───────────────────────────
if [ -z "$KEY" ]; then
  if [ -r /dev/tty ]; then
    # /dev/tty, not stdin: stdin is this script when the command was piped.
    printf '  Project API key (Setup tab): '
    KEY=$(head -n 1 </dev/tty)
  fi
fi
[ -n "$KEY" ] || die "no key. Pass --key, export CO_SCIENTIST_API_KEY, or run without piping so it can be asked for."

# ── the wiring, which the package owns ───────────────────────────────────────
mkdir -p "$DIR"
if [ "$HOST" = harness ]; then
  ( cd "$DIR" && CO_SCIENTIST_API_KEY="$KEY" "$VENV/bin/scivo" setup \
      ${PROJECT:+--project "$PROJECT"} --key "$KEY" ) \
    || die "scivo setup failed — scroll up for why"
else
  ( cd "$DIR" && "$VENV/bin/python" -m co_scientist_local wire \
      --host "$HOST" --key "$KEY" ${PROJECT:+--project "$PROJECT"} \
      --python "$VENV/bin/python" --dir . $FORCE ) \
    || die "wiring failed — scroll up for why"
fi

printf '\n'
say "Scivo is installed for: $HOST"
# What to run next comes from the host table, not from this script.
"$VENV/bin/python" - "$HOST" <<'PYEOF'
import sys
from co_scientist_local.hosts import host
spec = host(sys.argv[1])
print(f"  sign in:  {spec.sign_in}")
print(f"  start:    {spec.start}")
PYEOF
printf '\n'

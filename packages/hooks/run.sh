#!/bin/bash
# Hook dispatcher — Claude Code's settings.json calls
# `<packages/hooks>/run.sh <hook_name>` and we route to the right Python file.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$1"
shift
exec python3 "$DIR/${HOOK}.py" "$@"

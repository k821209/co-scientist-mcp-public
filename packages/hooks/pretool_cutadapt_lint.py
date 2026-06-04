#!/usr/bin/env python3
"""PreToolUse(Bash) hook: warn on the silent-bug `cutadapt -g X -a Y --discard-untrimmed`
pattern (todo 009 in the original repo).

Non-blocking: prints to stderr (visible to Claude as additional context) and
exits 0. Linked-adapter syntax (`-g 'X...Y'`) does NOT trigger.

Discovered live during nanoALE-seq: 4% trimmed-pool leak, primary mapping
rate 7.67% → 34.70% after switching to the linked form.
"""
from __future__ import annotations

import json
import re
import sys

_CUTADAPT_RE = re.compile(r"\bcutadapt\b")
_HAS_G_RE = re.compile(r"(?:^|\s)-g\s+\S")
_HAS_A_RE = re.compile(r"(?:^|\s)-a\s+\S")
_LINKED_RE = re.compile(r"-g\s+['\"]?\S*\.\.\.\S*['\"]?")
_DISCARD_RE = re.compile(r"--discard-untrimmed\b")


def is_loose_paired_amplicon(command: str) -> bool:
    if not _CUTADAPT_RE.search(command):
        return False
    if not _DISCARD_RE.search(command):
        return False
    if _LINKED_RE.search(command):
        return False
    return bool(_HAS_G_RE.search(command) and _HAS_A_RE.search(command))


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "").strip()
    if not command or not is_loose_paired_amplicon(command):
        sys.exit(0)

    print(
        "⚠ cutadapt loose-vs-strict warning:\n"
        "  Independent `-g X -a Y` with `--discard-untrimmed` only requires ONE\n"
        "  adapter to be found. For paired-primer amplicons where every read\n"
        "  MUST carry both primers, prefer the linked-adapter form:\n\n"
        "    cutadapt -g 'PRIMER_F...PRIMER_R_RC' --discard-untrimmed ...\n",
        file=sys.stderr,
    )
    sys.exit(0)  # non-blocking


if __name__ == "__main__":
    main()

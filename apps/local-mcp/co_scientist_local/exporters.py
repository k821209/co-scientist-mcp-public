"""Pandoc executor abstraction — same injectable-seam pattern as ssh.py.

Production wraps the `pandoc` binary via subprocess. Tests inject a Fake that
records the arguments + snapshots the working directory at call time, and can
synthesize output bytes so the post-pandoc upload step still has something to
read from disk.

LibreOffice (for .pptx ↔ .pdf conversion in the deck pipeline) is a separate
executor that lands when the deck tools port — not in v0.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class PandocExecutor(Protocol):
    def run(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        timeout: int = 120,
    ) -> tuple[int, str, str]:
        """Run `pandoc <args>` in `cwd`. Returns (rc, stdout, stderr)."""
        ...


class RealPandocExecutor:
    """Production pandoc executor."""

    def run(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        timeout: int = 120,
    ) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                ["pandoc", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"pandoc timeout after {timeout}s"
        except FileNotFoundError:
            return -1, "", "pandoc binary not found (install pandoc on this machine)"


class FakePandocExecutor:
    """Test pandoc executor.

    - Records all calls with args + cwd + a snapshot of files present in cwd.
    - Synthesizes an empty output file at the `-o` path so callers that
      try to read the output afterward don't fail.
    - `output_bytes` can be set to control what bytes the fake "produces".
    """

    def __init__(self, *, rc: int = 0, output_bytes: bytes = b"FAKE_PANDOC_OUTPUT") -> None:
        self.calls: list[dict] = []
        self._rc = rc
        self.output_bytes = output_bytes

    def run(
        self,
        args: list[str],
        *,
        cwd: str | None = None,
        timeout: int = 120,
    ) -> tuple[int, str, str]:
        snapshot: dict[str, bytes] = {}
        if cwd and Path(cwd).is_dir():
            for p in Path(cwd).rglob("*"):
                if p.is_file():
                    snapshot[str(p.relative_to(cwd))] = p.read_bytes()
        self.calls.append({
            "args": list(args), "cwd": cwd, "files": snapshot,
        })

        # Synthesize output file at the -o path so downstream code can read it
        if self._rc == 0 and self.output_bytes is not None:
            for i, a in enumerate(args):
                if a == "-o" and i + 1 < len(args):
                    out_path = Path(args[i + 1])
                    if not out_path.is_absolute() and cwd:
                        out_path = Path(cwd) / out_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(self.output_bytes)
                    break

        return self._rc, "", ""

"""Analysis runs: a record of one execution of an analysis.

Paths:
    doc: projects/{pid}/papers/{slug}/analyses/{analysis_name}/runs/{run_key}

`run_key` is a timestamp-derived id like `run_20260517_120453`. It's unique
per analysis. Runs carry: host ('local' or a server alias), command, pid,
exit_code, log path, start/finish timestamps.

`launch_local_job` is the only side-effecting tool here — it backgrounds the
command with `nohup … &` (the real work reparents to init) so it keeps
running even if Claude Code exits. The remote (SSH) job tools live in
`ssh_ops.py`.
"""
from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
from datetime import datetime, timezone

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from .analyses import _analysis_path


def _runs_path(state: State, slug: str, analysis: str) -> str:
    return state.project_path("papers", slug, "analyses", analysis, "runs")


def _run_path(state: State, slug: str, analysis: str, run_key: str) -> str:
    return state.project_path("papers", slug, "analyses", analysis, "runs", run_key)


def _ensure_analysis(state: State, slug: str, analysis: str) -> None:
    if state.backend.get_doc(_analysis_path(state, slug, analysis)) is None:
        raise NotFound(f"analysis {analysis!r} not found for {slug!r}")


def _new_run_key() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def record_analysis_run(
    state: State,
    slug: str,
    analysis: str,
    *,
    command: str,
    host: str = "local",
    env_name: str | None = None,
    pid: int | None = None,
    started_at: str | None = None,
    log_path: str | None = None,
    notes: str | None = None,
    run_key: str | None = None,
) -> dict:
    """Insert a new analysis_runs doc. Used by `launch_local_job` and (later)
    `submit_remote_job`."""
    _ensure_analysis(state, slug, analysis)
    run_key = run_key or _new_run_key()
    doc = {
        "run_key": run_key,
        # Denormalized fields so cross-paper collectionGroup queries on
        # "runs" can filter by project_id and link back to origin paper.
        "project_id": state.project_id,
        "paper_slug": slug,
        "analysis_name": analysis,
        "command": command,
        "host": host,
        "env_name": env_name,
        "pid": pid,
        "started_at": started_at or now_iso(),
        "finished_at": None,
        "exit_code": None,
        "log_path": log_path,
        "notes": notes,
        "created_at": now_iso(),
    }
    state.backend.set_doc(_run_path(state, slug, analysis, run_key), doc)
    return doc


def list_analysis_runs(
    state: State,
    slug: str,
    analysis: str,
    *,
    unfinished_only: bool = False,
    host: str | None = None,
) -> list[dict]:
    _ensure_analysis(state, slug, analysis)
    pairs = state.backend.list_collection(_runs_path(state, slug, analysis))
    runs = [data for _, data in pairs]
    if unfinished_only:
        runs = [r for r in runs if r.get("finished_at") is None]
    if host is not None:
        runs = [r for r in runs if r.get("host") == host]
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs


def get_analysis_run(state: State, slug: str, analysis: str, run_key: str) -> dict:
    _ensure_analysis(state, slug, analysis)
    doc = state.backend.get_doc(_run_path(state, slug, analysis, run_key))
    if doc is None:
        raise NotFound(f"run {run_key!r} not found")
    return doc


def mark_run_finished(
    state: State,
    slug: str,
    analysis: str,
    run_key: str,
    *,
    exit_code: int,
    finished_at: str | None = None,
    notes: str | None = None,
) -> dict:
    """Stamp finished_at + exit_code on a run; optionally append notes."""
    _ensure_analysis(state, slug, analysis)
    path = _run_path(state, slug, analysis, run_key)
    existing = state.backend.get_doc(path)
    if existing is None:
        raise NotFound(f"run {run_key!r} not found")
    fields: dict = {
        "finished_at": finished_at or now_iso(),
        "exit_code": exit_code,
    }
    if notes:
        prior = existing.get("notes") or ""
        fields["notes"] = (prior + " " + notes).strip()
    state.backend.update_doc(path, fields)
    return state.backend.get_doc(path)


def launch_local_job(
    state: State,
    slug: str,
    analysis: str,
    *,
    command: str,
    workdir: str,
    env_name: str | None = None,
    conda_root: str | None = None,
) -> dict:
    """Spawn `command` on the user's laptop, detached, log streamed to file.

    Uses the same `nohup … &` pattern as the original repo's `submit_remote_job`:
    a short-lived bash launcher backgrounds the real work and prints its PID.
    We synchronously wait for the launcher (microseconds), so no zombie of
    *our* parent process remains. The real job is reparented to init.

    Returns the analysis_runs row with `pid` and `log_path` set. The wrapper
    writes the exit code to `.exitcode_<run_key>` so `reap_local_run` can
    recover it once the PID is gone.
    """
    _ensure_analysis(state, slug, analysis)
    wd = pathlib.Path(workdir).expanduser().resolve()
    if not wd.is_dir():
        raise FileNotFoundError(f"workdir not found: {wd}")

    run_key = _new_run_key()
    log_file = wd / f"{run_key}.log"
    exit_sidecar = wd / f".exitcode_{run_key}"

    if env_name and conda_root:
        activate = (
            f"source {shlex.quote(conda_root)}/etc/profile.d/conda.sh && "
            f"conda activate {shlex.quote(env_name)} && "
        )
    else:
        activate = ""

    # Inner script runs the user's command, captures its exit code into a
    # sidecar file that reap_local_run reads after the PID disappears.
    inner = f"{activate}( {command} ); echo $? > {shlex.quote(str(exit_sidecar))}"

    # Launcher backgrounds `inner` via nohup, echoes the inner PID, then exits.
    # We Popen the launcher and wait for it — it exits in milliseconds, leaving
    # the inner process running and reparented to init.
    launcher = (
        f"nohup bash -c {shlex.quote(inner)} "
        f"> {shlex.quote(str(log_file))} 2>&1 & "
        f"echo $!"
    )
    result = subprocess.run(
        ["bash", "-c", launcher],
        cwd=str(wd),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launch failed (rc={result.returncode}): {result.stderr.strip()}")
    try:
        pid = int(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"could not parse PID from launcher output: {result.stdout!r}")

    return record_analysis_run(
        state, slug, analysis,
        command=command, host="local", env_name=env_name,
        pid=pid,
        log_path=str(log_file),
        run_key=run_key,
    )


def read_local_exitcode(workdir: str, run_key: str) -> int | None:
    """Read `.exitcode_<key>` written by the wrapper. Returns None if absent."""
    p = pathlib.Path(workdir).expanduser() / f".exitcode_{run_key}"
    if not p.is_file():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def reap_local_run(state: State, slug: str, analysis: str, run_key: str) -> dict:
    """Check whether a local run's PID is still alive; if not, mark it finished.

    Reads the .exitcode sidecar to recover the real exit code if the wrapper
    wrote one. Returns the (possibly-updated) run doc.
    """
    run = get_analysis_run(state, slug, analysis, run_key)
    if run.get("finished_at"):
        return run
    pid = run.get("pid")
    if pid is None:
        return run
    try:
        os.kill(pid, 0)
        return run  # still alive
    except ProcessLookupError:
        # Process is gone — try to recover exit code from the sidecar
        log_path = run.get("log_path") or ""
        workdir = str(pathlib.Path(log_path).parent) if log_path else ""
        ec = read_local_exitcode(workdir, run_key) if workdir else None
        return mark_run_finished(
            state, slug, analysis, run_key,
            exit_code=ec if ec is not None else -2,
            notes="auto-reaped: local PID gone",
        )
    except PermissionError:
        # Process exists but is owned by someone else (shouldn't happen for local)
        return run

"""SSH-bound server tools — port of the original src/servers.py operational layer.

All SSH and rsync calls go through `state.require_ssh()` / `state.require_rsync()`,
which fall back to subprocess-based executors in production and accept fakes
in tests.

Provides:
- server_status — live load/memory/our-jobs + politeness warnings
- submit_remote_job — politeness check + rsync + nohup launch (pidfile-idempotent)
- tail_remote_log — last N lines of run log (remote or local)
- kill_remote_job — SIGKILL recorded PID + mark run finished
- poll_remote_pids — close phantom rows for a host
- auto_finish_stale_runs — bulk cleanup across hosts
- scan_untracked_jobs — find detached job-like processes not in analysis_runs
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shlex
from datetime import datetime, timezone

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from .runs import (
    _new_run_key,
    bump_heartbeat,
    get_analysis_run,
    list_analysis_runs,
    mark_run_finished,
    record_analysis_run,
)
from .servers import get_server


# ──────────────────────────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────────────────────────


def _parse_uptime(s: str) -> dict:
    """Parse the load-average tail of `uptime`."""
    m = re.search(r"load average[s]?:\s*([\d.]+)[, ]+([\d.]+)[, ]+([\d.]+)", s)
    if not m:
        return {}
    return {
        "load_1": float(m.group(1)),
        "load_5": float(m.group(2)),
        "load_15": float(m.group(3)),
    }


def _parse_free_g(s: str) -> dict:
    """Parse `free -g` output (Linux). macOS lacks `free`, returns {}."""
    for line in s.splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            try:
                return {
                    "total_gb": int(parts[1]),
                    "used_gb": int(parts[2]),
                    "free_gb": int(parts[3]),
                    "available_gb": int(parts[6]) if len(parts) >= 7 else int(parts[3]),
                }
            except (ValueError, IndexError):
                return {}
    return {}


def _split_sections(out: str) -> dict[str, list[str]]:
    """Split `---marker---` delimited output into named sections."""
    sections: dict[str, list[str]] = {}
    cur: str | None = None
    for line in out.splitlines():
        m = re.match(r"^---(\w+)---$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    return sections


# ──────────────────────────────────────────────────────────────────────────────
# server_status
# ──────────────────────────────────────────────────────────────────────────────


def server_status(
    state: State,
    alias: str,
    *,
    our_pids: list[int] | None = None,
) -> dict:
    """SSH the server and report load / memory / our jobs / warnings.

    If `our_pids` is None, the unfinished PIDs recorded for this host across
    all analyses (the user's papers) are queried automatically.
    """
    server = get_server(state, alias)
    ssh = state.require_ssh()
    cores = server.get("cores") or 1
    user = server["user"]

    if our_pids is None:
        our_pids = _collect_unfinished_pids_for_host(state, alias)

    pids_arg = ",".join(str(p) for p in our_pids) if our_pids else ""
    cmd = (
        "echo '---uptime---'; uptime; "
        "echo '---free---'; free -g 2>/dev/null || echo 'no-free'; "
        "echo '---others---'; "
        f"(ps -e -o user= -o pcpu= 2>/dev/null | "
        f"awk -v me={shlex.quote(user)} '$1!=me && $2+0>10 {{c++}} END{{print c+0}}'); "
        + (f"echo '---ours---'; ps -p {pids_arg} -o pid=,etime=,cmd= 2>/dev/null || true; "
           if pids_arg else "echo '---ours---'; ")
        + "true"
    )
    rc, out, err = ssh.run(server, cmd)
    if rc != 0:
        return {
            "alias": alias, "host": server["host"], "online": False,
            "error": (err or "").strip() or f"ssh exit={rc}",
            "warnings": ["server unreachable"],
        }

    sections = _split_sections(out)
    load = _parse_uptime("\n".join(sections.get("uptime", [])))
    mem = _parse_free_g("\n".join(sections.get("free", [])))

    others_heavy = 0
    if sections.get("others"):
        try:
            others_heavy = int(sections["others"][0].strip() or "0")
        except (ValueError, IndexError):
            others_heavy = 0

    our_running: list[dict] = []
    for line in sections.get("ours", []):
        line = line.strip()
        if not line or line.startswith("PID"):
            continue
        parts = line.split(None, 2)
        if len(parts) >= 3:
            try:
                our_running.append({
                    "pid": int(parts[0]), "etime": parts[1], "cmd": parts[2],
                })
            except ValueError:
                continue

    warnings: list[str] = []
    if load.get("load_1") is not None and load["load_1"] >= cores:
        warnings.append(
            f"load avg 1min={load['load_1']:.2f} >= {cores} cores; another user may be busy"
        )
    if mem.get("total_gb") and mem.get("available_gb") is not None:
        if mem["available_gb"] < max(2, mem["total_gb"] * 0.10):
            warnings.append(
                f"available memory {mem['available_gb']}GB < 10% of {mem['total_gb']}GB"
            )
    if others_heavy > 0:
        warnings.append(f"{others_heavy} other-user process(es) using >10% CPU")

    alive = {r["pid"] for r in our_running}
    dead_pids = [p for p in our_pids if p not in alive]

    polite_max = int(cores * (server.get("polite_max_cores_pct") or 50) / 100)
    return {
        "alias": alias, "host": server["host"], "online": True,
        "cores": cores, "load": load, "memory": mem,
        "other_users_heavy_count": others_heavy,
        "our_running": our_running,
        "dead_pids": dead_pids,
        "polite_max_workers": polite_max,
        "warnings": warnings,
    }


def _collect_unfinished_pids_for_host(state: State, host: str) -> list[int]:
    """Walk all papers/analyses for the user and gather unfinished PIDs on `host`."""
    out: list[int] = []
    papers_pairs = state.backend.list_collection(state.project_path("papers"))
    for paper_slug, _ in papers_pairs:
        analyses_pairs = state.backend.list_collection(
            state.project_path("papers", paper_slug, "analyses")
        )
        for analysis_name, _ in analyses_pairs:
            for r in list_analysis_runs(
                state, paper_slug, analysis_name, unfinished_only=True, host=host,
            ):
                if r.get("pid"):
                    out.append(r["pid"])
    return out


# ──────────────────────────────────────────────────────────────────────────────
# submit_remote_job
# ──────────────────────────────────────────────────────────────────────────────


def submit_remote_job(
    state: State,
    paper_slug: str,
    analysis_name: str,
    *,
    command: str,
    server_alias: str,
    env_name: str | None = None,
    workers: int | None = None,
    local_dir: str | None = None,
    sync_files: bool = True,
    force: bool = False,
) -> dict:
    """Politeness-checked SSH job submission with pidfile idempotency.

    Steps:
        1. server_status → block if load >= cores or workers > polite cap (unless force=True)
        2. SSH `mkdir -p remote_dir`
        3. rsync local_dir → remote_dir (if sync_files=True)
        4. SSH-launch under nohup, capture PID via deterministic pidfile.
           If a live PID already runs the same command, return "existing".
        5. Record an analysis_runs row.
    """
    server = get_server(state, server_alias)
    # Base dir: this PROJECT's working directory on the server (if bound) takes
    # precedence over the account server's default_workdir — so each project's
    # runs land in its own directory. Falls back to the server default.
    from . import workdirs as _workdirs
    proj_wd = (_workdirs.get_project_workdir(state, server_alias) or {}).get("workdir")
    base_workdir = (proj_wd or server.get("default_workdir") or "").strip()
    if not base_workdir:
        return {
            "error": f"server {server_alias!r} has no working directory for this "
                     "project — set one via set_project_workdir(alias, workdir, "
                     "description=...) (or the server's default_workdir)."
        }
    ssh = state.require_ssh()

    # 1. Politeness
    status = server_status(state, server_alias)
    polite_warnings: list[str] = []
    if not status.get("online", False):
        return {"error": f"server unreachable: {status.get('error', '?')}"}
    polite_workers = status["polite_max_workers"]
    if not force:
        load_1 = (status.get("load") or {}).get("load_1")
        if load_1 is not None and load_1 >= server["cores"]:
            return {
                "error": f"{server_alias} load avg {load_1:.2f} >= {server['cores']} cores; "
                         "another user appears busy. Pass force=True to override."
            }
        if workers is not None and workers > polite_workers:
            return {
                "error": f"requested {workers} workers > polite cap {polite_workers} "
                         f"(= {server['cores']} cores * "
                         f"{server.get('polite_max_cores_pct', 50)}%). "
                         "Pass force=True to override."
            }
    if status.get("warnings"):
        polite_warnings.extend(status["warnings"])

    # 2. Resolve remote dir + create (under the project's base workdir)
    remote_dir = f"{base_workdir.rstrip('/')}/analysis/{analysis_name}"
    rc, _, err = ssh.run(server, f"mkdir -p {shlex.quote(remote_dir)}")
    if rc != 0:
        return {"error": f"failed to create remote dir: {(err or '').strip()}"}

    # 3. rsync (only if local_dir is provided)
    if sync_files and local_dir:
        rsync = state.require_rsync()
        rc, _, err = rsync.mirror(server, local_dir, remote_dir)
        if rc != 0:
            return {"error": f"rsync failed: {(err or '').strip() or f'rc={rc}'}"}

    # 4. Launch script with pidfile idempotency (matches original submit_remote_job)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_filename = f"run_{ts}.log"
    log_path_remote = f"{remote_dir}/{log_filename}"
    log_path_relative = f"analysis/{analysis_name}/{log_filename}"
    if env_name:
        if server.get("conda_root"):
            activate = (
                f"source {shlex.quote(server['conda_root'])}/etc/profile.d/conda.sh && "
                f"conda activate {shlex.quote(env_name)} && "
            )
        else:
            activate = f"conda activate {shlex.quote(env_name)} && "
    else:
        activate = ""
    marker = hashlib.sha256(f"{analysis_name}|{command}".encode("utf-8")).hexdigest()[:12]
    pidfile = f".pidfile_{marker}"
    wrapped = (
        f"trap 'rm -f {pidfile}' EXIT; "
        f"( {command} ); echo $? > .exitcode"
    )
    launch = (
        f"cd {shlex.quote(remote_dir)} && {activate}"
        f"if [ -f {pidfile} ]; then "
        f"  EXIST=$(cat {pidfile}); "
        f"  if kill -0 \"$EXIST\" 2>/dev/null; then "
        f"    echo \"EXISTING:$EXIST\"; exit 0; "
        f"  fi; "
        f"  rm -f {pidfile}; "
        f"fi; "
        f"nohup bash -c {shlex.quote(wrapped)} > {shlex.quote(log_filename)} 2>&1 & "
        f"PID=$!; echo $PID > {pidfile}; sync; "
        f"echo \"PID:$PID\""
    )
    rc, out, err = ssh.run(server, launch, timeout=30)
    if rc != 0:
        return {
            "error": f"launch failed (rc={rc}): {(err or '').strip()}",
            "stdout": out,
        }
    last = (out.strip().splitlines() or [""])[-1]
    existing = False
    pid: int | None = None
    if last.startswith("EXISTING:"):
        existing = True
        try: pid = int(last.split(":", 1)[1])
        except ValueError: pid = None
    elif last.startswith("PID:"):
        try: pid = int(last.split(":", 1)[1])
        except ValueError: pid = None
    if pid is None:
        return {"error": f"could not parse launch output: {out!r}"}

    if existing:
        polite_warnings.append(
            f"Duplicate submit blocked: PID {pid} already running on "
            f"{server_alias} (idempotency lock via {pidfile})."
        )
        return {
            "run_key": None, "pid": pid, "host": server_alias,
            "log_path": log_path_relative, "remote_dir": remote_dir,
            "remote_log_path": log_path_remote,
            "warnings": polite_warnings, "existing": True,
        }

    notes = "; ".join(polite_warnings) if polite_warnings else None
    started_at = now_iso()
    run = record_analysis_run(
        state, paper_slug, analysis_name,
        command=command, host=server_alias, env_name=env_name,
        pid=pid, started_at=started_at, log_path=log_path_relative,
        workdir=remote_dir,
        notes=notes,
    )
    return {
        "run_key": run["run_key"], "pid": pid, "host": server_alias,
        "log_path": log_path_relative, "remote_dir": remote_dir,
        "remote_log_path": log_path_remote,
        "warnings": polite_warnings, "existing": False,
    }


# ──────────────────────────────────────────────────────────────────────────────
# tail / kill / poll / scan
# ──────────────────────────────────────────────────────────────────────────────


def tail_remote_log(
    state: State,
    paper_slug: str,
    analysis_name: str,
    run_key: str,
    *,
    lines: int = 50,
) -> dict:
    """Return the last N lines of a run's log file (remote or local)."""
    run = get_analysis_run(state, paper_slug, analysis_name, run_key)
    log_path = run.get("log_path")
    if not log_path:
        return {"error": "run has no log_path"}
    host = run.get("host") or "local"
    if host == "local":
        p = pathlib.Path(log_path)
        if not p.is_file():
            return {"error": f"log file not found: {p}"}
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"error": f"read failed: {e}"}
        tail = "\n".join(text.splitlines()[-lines:])
        return {"run_key": run_key, "host": host, "log_path": log_path, "tail": tail}

    server = get_server(state, host)
    ssh = state.require_ssh()
    if log_path.startswith("/"):
        remote_log = log_path
    elif run.get("workdir"):
        # Prefer the absolute workdir recorded at submit time — robust even if
        # the server's default_workdir was changed afterwards.
        remote_log = f"{run['workdir'].rstrip('/')}/{pathlib.PurePosixPath(log_path).name}"
    else:
        wd = (server.get("default_workdir") or "").rstrip("/")
        remote_log = f"{wd}/{log_path}" if wd else log_path
    rc, out, err = ssh.run(server, f"tail -n {int(lines)} {shlex.quote(remote_log)}", timeout=15)
    if rc != 0:
        return {"error": f"remote tail failed: {(err or '').strip() or f'rc={rc}'}"}
    return {"run_key": run_key, "host": host, "log_path": log_path, "tail": out}


def refresh_log_tail(
    state: State,
    paper_slug: str,
    analysis_name: str,
    run_key: str,
    *,
    lines: int = 50,
) -> dict:
    """Like tail_remote_log, but ALSO writes the result onto the run doc so
    the dashboard's Runs tab can render it via its Firestore listener.

    Skill flow: user opens Runs tab, asks Claude to "tail run_xyz", Claude
    calls this tool, the run doc gets `log_tail` + `log_tail_updated_at`
    fields, the dashboard updates within ~50ms via the Firestore listener.

    Future: a background thread spawned by launch_local_job / submit_remote_job
    auto-calls this every 30s while finished_at is null — fully live tail
    without the agent's involvement.
    """
    res = tail_remote_log(state, paper_slug, analysis_name, run_key, lines=lines)
    if "tail" not in res:
        return res  # propagate error
    # Write back onto the run doc
    from .runs import _run_path
    state.backend.update_doc(
        _run_path(state, paper_slug, analysis_name, run_key),
        {
            "log_tail": res["tail"],
            "log_tail_lines": lines,
            "log_tail_updated_at": now_iso(),
        },
    )
    return {**res, "persisted": True}


def kill_remote_job(
    state: State,
    paper_slug: str,
    analysis_name: str,
    run_key: str,
) -> dict:
    """SIGKILL a recorded remote (or local) PID and mark its run finished."""
    run = get_analysis_run(state, paper_slug, analysis_name, run_key)
    if run.get("finished_at"):
        return {"error": f"run {run_key!r} already finished at {run['finished_at']}"}
    pid = run.get("pid")
    if not pid:
        return {"error": "run has no pid recorded"}
    host = run.get("host") or "local"

    if host == "local":
        try:
            import signal
            os.kill(int(pid), signal.SIGKILL)
            killed = True
        except ProcessLookupError:
            killed = False
        except Exception as e:
            return {"error": f"local kill failed: {e}"}
    else:
        server = get_server(state, host)
        ssh = state.require_ssh()
        rc, _, err = ssh.run(server, f"kill -9 {int(pid)}", timeout=10)
        if rc != 0 and "no such process" not in (err or "").lower():
            return {"error": f"remote kill failed: {(err or '').strip() or f'rc={rc}'}"}
        killed = (rc == 0)

    fin = mark_run_finished(
        state, paper_slug, analysis_name, run_key,
        exit_code=-1, notes="[killed]",
    )
    return {
        "run_key": run_key, "host": host, "pid": pid,
        "killed": killed, "finished_at": fin["finished_at"],
    }


def _all_unfinished_runs_for_host(state: State, host: str) -> list[dict]:
    """Walk all papers/analyses for the user, gather unfinished runs on `host`.

    Returns dicts with paper_slug + analysis_name injected for easy follow-up.
    """
    out: list[dict] = []
    for paper_slug, _ in state.backend.list_collection(state.project_path("papers")):
        for analysis_name, _ in state.backend.list_collection(
            state.project_path("papers", paper_slug, "analyses")
        ):
            for r in list_analysis_runs(
                state, paper_slug, analysis_name, unfinished_only=True, host=host,
            ):
                out.append({**r, "paper_slug": paper_slug, "analysis_name": analysis_name})
    return out


def poll_remote_pids(state: State, alias: str) -> dict:
    """One SSH round-trip: detect dead PIDs for `alias` and auto-finish their runs."""
    rows = _all_unfinished_runs_for_host(state, alias)
    rows = [r for r in rows if r.get("pid")]
    if not rows:
        return {"alias": alias, "checked": 0, "finished": 0, "still_running": 0}

    server = get_server(state, alias)
    ssh = state.require_ssh()
    pid_list = ",".join(str(r["pid"]) for r in rows)
    rc, out, err = ssh.run(server, f"ps -p {pid_list} -o pid= 2>/dev/null", timeout=10)
    if rc != 0 and not out:
        return {
            "alias": alias, "checked": len(rows),
            "finished": 0, "still_running": len(rows),
            "error": (err or "").strip() or f"ssh rc={rc}",
        }
    alive: set[int] = set()
    for line in out.splitlines():
        try:
            alive.add(int(line.strip()))
        except ValueError:
            continue

    finished = 0
    for r in rows:
        if r["pid"] in alive:
            # Still running — a live PID is proof of life; refresh the heartbeat
            # so the dashboard keeps it spinning rather than aging it to "stale".
            bump_heartbeat(state, r["paper_slug"], r["analysis_name"], r["run_key"])
            continue
        mark_run_finished(
            state, r["paper_slug"], r["analysis_name"], r["run_key"],
            exit_code=-2, notes="auto-detected: process no longer running",
        )
        finished += 1
    return {
        "alias": alias, "checked": len(rows),
        "finished": finished, "still_running": len(rows) - finished,
    }


def auto_finish_stale_runs(state: State) -> dict:
    """Cleanup across all hosts: local PIDs via os.kill, remote PIDs via poll."""
    finished = 0
    errors: list[str] = []

    # Build per-host bucket
    by_host: dict[str, list[dict]] = {}
    for paper_slug, _ in state.backend.list_collection(state.project_path("papers")):
        for analysis_name, _ in state.backend.list_collection(
            state.project_path("papers", paper_slug, "analyses")
        ):
            for r in list_analysis_runs(
                state, paper_slug, analysis_name, unfinished_only=True,
            ):
                if not r.get("pid"):
                    continue
                by_host.setdefault(r.get("host") or "local", []).append(
                    {**r, "paper_slug": paper_slug, "analysis_name": analysis_name}
                )

    # Local cleanup
    for r in by_host.pop("local", []):
        try:
            os.kill(int(r["pid"]), 0)  # still alive
        except ProcessLookupError:
            mark_run_finished(
                state, r["paper_slug"], r["analysis_name"], r["run_key"],
                exit_code=-2, notes="auto-detected: local PID gone (backfill)",
            )
            finished += 1
        except PermissionError:
            pass  # exists but not ours

    # Remote cleanup, one SSH per host
    for alias in list(by_host):
        try:
            res = poll_remote_pids(state, alias)
            finished += res.get("finished", 0)
            if res.get("error"):
                errors.append(f"{alias}: {res['error']}")
        except Exception as e:  # pragma: no cover — defensive
            errors.append(f"{alias}: {e}")
    return {"finished": finished, "errors": errors}


# ──────────────────────────────────────────────────────────────────────────────
# scan_untracked_jobs
# ──────────────────────────────────────────────────────────────────────────────

_JOB_LIKE_RE = re.compile(
    r"^(?:nohup\b|"
    r"\S*python\d?(?:\s+-\w+)*\s+\S+\.py\b|"
    r"\S*Rscript\b|"
    r"\S*julia\b|"
    r"\S*java\s+-(?:jar|cp)\b|"
    r"\S*bash\s+\S+\.sh\b|"
    r"\S*sh\s+\S+\.sh\b)",
)
_DAEMON_EXCLUDE_RE = re.compile(
    r"\b(?:sshd|tmux|screen|dbus|gpg-agent|systemd|init|"
    r"agetty|cron|crond|atd|nginx|sudo|login|getty|udisksd|"
    r"jupyter[- ]?(?:lab|notebook)|jupyter-server|"
    r"code-server|"
    r"vim|emacs|nano|less|htop|top|"
    r"bash|zsh|fish|sh)\b",
    re.IGNORECASE,
)


def _parse_etime_seconds(etime: str) -> int:
    """Parse `ps etime` (e.g. 12-04:55:30, 04:55:30, 55:30, 30) → seconds."""
    s = etime.strip()
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts[-3], parts[-2], parts[-1]
    return days * 86400 + h * 3600 + m * 60 + sec


def scan_untracked_jobs(
    state: State,
    alias: str,
    *,
    min_etime_seconds: int = 60,
) -> dict:
    """List detached job-like processes on `alias` that aren't in analysis_runs.

    Returns {alias, tracked: [pid], untracked: [{pid, ppid, etime, etime_sec, cmd}]}.
    """
    server = get_server(state, alias)
    ssh = state.require_ssh()
    user = server["user"]
    cmd = f"ps -u {shlex.quote(user)} -o pid=,ppid=,etime=,cmd= --no-headers 2>/dev/null"
    rc, out, err = ssh.run(server, cmd, timeout=12)
    if rc != 0:
        return {
            "alias": alias,
            "error": (err or "").strip() or f"ssh rc={rc}",
            "tracked": [], "untracked": [],
        }

    tracked_pids = set(_collect_unfinished_pids_for_host(state, alias))
    tracked_seen: list[int] = []
    untracked: list[dict] = []
    for line in out.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0]); ppid = int(parts[1])
        except ValueError:
            continue
        etime, cmdline = parts[2], parts[3]
        try:
            etime_sec = _parse_etime_seconds(etime)
        except (ValueError, IndexError):
            etime_sec = 0
        if etime_sec < min_etime_seconds:
            continue
        if _DAEMON_EXCLUDE_RE.search(cmdline):
            continue
        is_detached = (ppid == 1)
        is_job_like = bool(_JOB_LIKE_RE.match(cmdline))
        if not (is_detached and is_job_like):
            continue
        if pid in tracked_pids:
            tracked_seen.append(pid)
        else:
            untracked.append({
                "pid": pid, "ppid": ppid, "etime": etime,
                "etime_sec": etime_sec, "cmd": cmdline,
            })
    return {"alias": alias, "tracked": tracked_seen, "untracked": untracked}

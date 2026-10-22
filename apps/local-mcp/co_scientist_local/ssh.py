"""SSH + rsync executor abstraction.

Production wraps the `ssh` / `rsync` binaries via subprocess. Tests inject
fakes that record calls and return canned responses. This lets every SSH
tool be unit-tested without a real SSH target — the executor is the only
seam.

Connection-error handling mirrors the original src/servers.py:_ssh_exec:
- Try the registered alias first (matches user's ~/.ssh/config), then
  user@host as fallback.
- Retry once with 1.5s backoff on transient errors (rc 255/-1, "Connection
  refused", "kex_exchange_identification", etc.).
- Treat rc=0 as success even with stderr noise.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Protocol


_CONN_ERROR_PATTERNS = (
    "connection refused", "connection timed out", "connection reset",
    "ssh: connect to host", "kex_exchange_identification",
    "broken pipe", "no route to host", "operation timed out",
    "permission denied (publickey",
)


def is_connection_error(rc: int, stderr: str) -> bool:
    """Heuristic: should this ssh failure be retried?"""
    if rc in (255, -1):
        return True
    s = (stderr or "").lower()
    return any(p in s for p in _CONN_ERROR_PATTERNS)


# ── session setup cost, and how it is paid once ───────────────────────────────
#
# A registered host returned "server unreachable: timeout after 12s" on four
# consecutive calls while it was up, idle and accepting work: direct ssh from
# the same machine took a consistent 24 s, at load 5 and at load 25 alike. The
# time goes after authentication — Ubuntu's default `pam_motd.so` runs 13
# scripts from /etc/update-motd.d/, several wanting outbound network the host's
# network constrains. Key exchange and public-key acceptance complete
# immediately. That is an ordinary Ubuntu default, so any host like it was
# unusable through these tools, and the message said the host was down
# (feedback 92515583fea8).
#
# Two things follow. The cost is PER CONNECTION, so multiplexing pays it once —
# the reporter measured 24 s then 0–1 s with ControlMaster in their own
# ~/.ssh/config, which is the fix, and it also speeds up the many short calls
# these tools already make (tail_remote_log, poll_remote_pids, server_status).
# And the first contact with a host needs a budget that a login can fit inside;
# 12 s is below the cost of a default Ubuntu login on a busy box.
_FIRST_CONTACT_TIMEOUT = 45
# Keep the master alive across the short calls of one session, not forever.
_CONTROL_PERSIST = "30m"
# Sockets live under a short path: the control path goes into a sockaddr_un,
# which caps at ~100 characters, and %C is a hash of (host, port, user).
_CONTROL_DIR = Path.home() / ".cache" / "co-scientist" / "ssh"
# Hosts this PROCESS has reached. The first call to one pays the login cost;
# the rest ride the master socket.
_REACHED: set[str] = set()


def _control_args() -> list[str]:
    """Multiplexing options, or nothing if the socket directory is unusable."""
    try:
        _CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        _CONTROL_DIR.chmod(0o700)
    except OSError:
        return []
    return [
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={_CONTROL_DIR}/%C",
        "-o", f"ControlPersist={_CONTROL_PERSIST}",
    ]


# ──────────────────────────────────────────────────────────────────────────────
# SSH executor
# ──────────────────────────────────────────────────────────────────────────────


class SSHExecutor(Protocol):
    def run(
        self,
        server: dict,
        command: str,
        *,
        timeout: int = 12,
    ) -> tuple[int, str, str]:
        """Execute `command` on `server`. Returns (returncode, stdout, stderr)."""
        ...


class RealSSHExecutor:
    """Production SSH executor using the system `ssh` binary."""

    def run(
        self,
        server: dict,
        command: str,
        *,
        timeout: int = 12,
    ) -> tuple[int, str, str]:
        targets: list[str] = []
        if server.get("alias"):
            targets.append(server["alias"])
        if server.get("user") and server.get("host"):
            ut = f"{server['user']}@{server['host']}"
            if ut not in targets:
                targets.append(ut)
        if not targets:
            return -1, "", "no ssh target (alias or user@host) configured"

        def _try(target: str) -> tuple[int, str, str]:
            first = target not in _REACHED
            # ConnectTimeout covers reaching the host, which is a different
            # question from how long its login takes; the budget below is what
            # the slow part needs.
            budget = max(timeout + 5, _FIRST_CONTACT_TIMEOUT) if first else timeout + 5
            args = [
                "ssh",
                "-T",                      # no tty: skips tty-conditional motd
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={max(5, timeout)}",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ServerAliveInterval=15",
                *_control_args(),
            ]
            if server.get("ssh_key"):
                args += ["-i", server["ssh_key"]]
            args += [target, command]
            try:
                proc = subprocess.run(
                    args, capture_output=True, text=True, timeout=budget,
                )
                if proc.returncode == 0:
                    _REACHED.add(target)
                return proc.returncode, proc.stdout, proc.stderr
            except subprocess.TimeoutExpired:
                # Named, and separated from "cannot connect": the host that
                # produced this one was up the whole time, and "unreachable"
                # sent the author to raw `ssh … nohup`, which the guardrails
                # block and which costs the run record.
                return -1, "", (
                    f"no answer within {budget}s"
                    + (" on the first connection to this host — ssh itself "
                       "connects, but the login can take that long when the "
                       "server runs update-motd scripts; the connection is "
                       "multiplexed, so if the host is simply slow a retry now "
                       "reuses it and returns at once"
                       if first else
                       f" (ssh was given {budget}s for this command)"))
            except FileNotFoundError:
                return -1, "", "ssh binary not found"

        def _attempt() -> tuple[int, str, str]:
            last = (-1, "", "no targets")
            for target in targets:
                rc, out, err = _try(target)
                if rc == 0:
                    return rc, out, err
                last = (rc, out, err)
                if not is_connection_error(rc, err):
                    return last  # real remote failure, fallback won't help
            return last

        rc, out, err = _attempt()
        if rc == 0 or not is_connection_error(rc, err):
            return rc, out, err

        # Transient → 1 retry after backoff
        time.sleep(1.5)
        return _attempt()


class FakeSSHExecutor:
    """Test SSH executor: programmable responses + call recording.

    Usage:
        ssh = FakeSSHExecutor()
        ssh.expect(alias="gpu-box", command_substring="uptime",
                   stdout="...load average: 0.4, 0.5, 0.6")
        ssh.expect(stdout="default-response")

    Matchers are checked in registration order; first match wins. If no
    matcher matches, default is (rc=0, stdout="", stderr="").
    """

    def __init__(self) -> None:
        self._responses: list[tuple[str | None, str | None, int, str, str]] = []
        self.calls: list[tuple[str | None, str]] = []

    def expect(
        self,
        *,
        alias: str | None = None,
        command_substring: str | None = None,
        rc: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self._responses.append((alias, command_substring, rc, stdout, stderr))

    def run(
        self,
        server: dict,
        command: str,
        *,
        timeout: int = 12,
    ) -> tuple[int, str, str]:
        alias = server.get("alias")
        self.calls.append((alias, command))
        for exp_alias, exp_substr, rc, out, err in self._responses:
            if exp_alias is not None and exp_alias != alias:
                continue
            if exp_substr is not None and exp_substr not in command:
                continue
            return rc, out, err
        return 0, "", ""


# ──────────────────────────────────────────────────────────────────────────────
# Rsync executor
# ──────────────────────────────────────────────────────────────────────────────


class RsyncExecutor(Protocol):
    def mirror(
        self,
        server: dict,
        local_dir: str,
        remote_dir: str,
        *,
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        """Mirror local_dir → remote_dir over SSH. Returns (rc, stdout, stderr)."""
        ...


class RealRsyncExecutor:
    """Production rsync executor."""

    def mirror(
        self,
        server: dict,
        local_dir: str,
        remote_dir: str,
        *,
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        local = Path(local_dir)
        if not local.exists():
            return -1, "", f"local dir not found: {local}"

        ssh_args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if server.get("ssh_key"):
            ssh_args += ["-i", server["ssh_key"]]
        ssh_cmd = " ".join(shlex.quote(a) for a in ssh_args)
        target = f"{server['user']}@{server['host']}:{remote_dir}"
        args = [
            "rsync", "-az",
            "-e", ssh_cmd,
            "--exclude=.*", "--exclude=run_*.log", "--exclude=commands.log",
            f"{local}/",
            target,
        ]
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout + 30,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "rsync timeout"
        except FileNotFoundError:
            return -1, "", "rsync binary not found"


class FakeRsyncExecutor:
    """Test rsync executor: records calls, returns programmable results."""

    def __init__(self, *, rc: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.calls: list[tuple[str, str, str]] = []  # (alias, local, remote)
        self._rc, self._stdout, self._stderr = rc, stdout, stderr

    def mirror(
        self,
        server: dict,
        local_dir: str,
        remote_dir: str,
        *,
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        self.calls.append((server.get("alias", ""), local_dir, remote_dir))
        return self._rc, self._stdout, self._stderr

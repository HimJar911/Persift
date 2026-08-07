"""Thin wrapper around ssh/scp subprocess calls to the VM. Laptop always
initiates (outbound-only) -- no inbound port opened on the laptop, no
tunnel/ngrok exposure surface. Every call has its own timeout so a wedged
SSH connection (network blip, VM reboot) can't hang the runner loop
forever -- caller is expected to catch SSHError and retry on the next poll
tick rather than crash.
"""

import logging
import subprocess

from decision_agent import config

logger = logging.getLogger(__name__)

_SSH_TIMEOUT_SECONDS = 30


class SSHError(Exception):
    pass


def _ssh_base_cmd() -> list[str]:
    return [
        "ssh", "-i", config.VM_SSH_KEY,
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        config.VM_HOST,
    ]


def run_remote(command: str, timeout: int = _SSH_TIMEOUT_SECONDS) -> str:
    """Runs `command` on the VM via a login shell so PATH/venv-relative
    commands behave the same as an interactive SSH session. Returns stdout;
    raises SSHError (with stderr attached) on nonzero exit or timeout."""
    full_cmd = _ssh_base_cmd() + [command]
    try:
        proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SSHError(f"SSH command timed out after {timeout}s: {command!r}") from e
    if proc.returncode != 0:
        raise SSHError(f"SSH command failed (exit {proc.returncode}): {command!r}\nstderr: {proc.stderr}")
    return proc.stdout


def list_remote_files(remote_glob: str) -> list[str]:
    """Returns matching remote paths, or [] if none match (uses `ls` with
    a fallback so a no-match glob doesn't raise -- `ls` errors on no match
    without nullglob, so we suppress that specific failure)."""
    try:
        out = run_remote(f"ls -1 {remote_glob} 2>/dev/null || true")
    except SSHError:
        raise
    return [line.strip() for line in out.splitlines() if line.strip()]


def read_remote_file(remote_path: str) -> str:
    return run_remote(f"cat {remote_path}")


def rename_remote_file(src: str, dst: str) -> None:
    """Atomic on a POSIX filesystem -- used to claim a decision-request
    file so a runner restart mid-poll never double-processes it."""
    run_remote(f"mv {src} {dst}")


def write_remote_file(remote_path: str, content: str) -> None:
    """Writes via SSH stdin (not scp) so no local temp file is needed and
    the write is a single round trip. Content is passed through the SSH
    command's stdin to `cat > path`, avoiding shell-quoting issues with
    JSON content containing quotes/newlines."""
    full_cmd = _ssh_base_cmd() + [f"cat > {remote_path}"]
    try:
        proc = subprocess.run(
            full_cmd, input=content, capture_output=True, text=True, timeout=_SSH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise SSHError(f"SSH write timed out after {_SSH_TIMEOUT_SECONDS}s: {remote_path!r}") from e
    if proc.returncode != 0:
        raise SSHError(f"SSH write failed (exit {proc.returncode}): {remote_path!r}\nstderr: {proc.stderr}")

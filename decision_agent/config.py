"""Local config for the laptop-side decision-agent runner. Not committed
secrets — just paths/hosts specific to this machine. Edit these constants
directly (this package only ever runs on the one laptop, no multi-user
deploy target)."""

from pathlib import Path

VM_HOST = "vmuser@REDACTED-HOST"
VM_SSH_KEY = r"C:\Users\himan\.ssh\harness-vm_key.pem"
VM_REPO_DIR = "/home/vmuser/persift"

POLL_INTERVAL_SECONDS = 30

# Where per-ATS claude session IDs are persisted across runner restarts, so
# a laptop reboot mid-effort resumes the SAME session (full history intact)
# rather than starting a fresh one.
LOCAL_STATE_DIR = Path(__file__).resolve().parent / "state"
SESSION_IDS_FILE = LOCAL_STATE_DIR / "session_ids.json"
LOG_FILE = LOCAL_STATE_DIR / "runner.log"

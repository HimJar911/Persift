"""Prevents Windows from sleeping (idle timeout OR lid-close, if the lid
close action is set to 'do nothing') for as long as this process holds the
flag set. Uses SetThreadExecutionState, the standard Win32 mechanism apps
like video players use to keep the machine awake during playback — no
registry/power-plan changes, and it reverts automatically the moment the
process exits or clears the flag (including on a crash, since the flag is
thread-scoped and dies with the process).

Public API:
    keep_awake() -- context manager; prevents sleep for its duration
"""

import contextlib
import ctypes
import logging

logger = logging.getLogger(__name__)

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_AWAYMODE_REQUIRED = 0x00000040


@contextlib.contextmanager
def keep_awake():
    """Does nothing (logs a warning) on non-Windows so the runner still
    works for local testing on other platforms."""
    if not hasattr(ctypes, "windll"):
        logger.warning("Not running on Windows — sleep prevention is a no-op.")
        yield
        return

    flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_AWAYMODE_REQUIRED
    result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    if result == 0:
        logger.warning("SetThreadExecutionState failed — sleep prevention may not be active.")
    else:
        logger.info("Sleep prevention active (SetThreadExecutionState).")
    try:
        yield
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        logger.info("Sleep prevention released.")

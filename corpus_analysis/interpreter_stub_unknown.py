"""Trivial always-UNKNOWN interpreter — exists only to prove replay.py's
--interpreter swapping actually swaps (P1.3 verification step 4), not to be
used for any real scoring.
"""


def interpret(field):
    return {"category": None, "confidence": 0.0, "rule": None, "key": None}

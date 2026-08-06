"""JSONL writer/reader for the per-job failure log.

One line per non-`mechanically_verified` job, per joyful-sprouting-swan.md's
"Failure log schema" section. Field-level context deliberately mirrors
filler_utils.js's rich Field object (enrichField()) so cluster.py's
structural-fingerprint grouping and any resulting interpreter_regressions.json
entry need no reshaping between what the harness observed and what the
interpreter/extension already key on.

Also defines a second, parallel JSONL stream — attempts_<run_id>.jsonl — one
line per job that reached field verification (ANY outcome, not just
non-clean ones), each field enriched the same way. failure_log.py's own
greenhouse_run_<run_id>.jsonl stays exactly the plan's literal failure
schema (failures only); this second stream exists because cluster.py's
paired-success lookup ("what's different about the forms that failed vs.
the ones that didn't") needs structural data on SUCCESSFUL fields too,
which nothing else persists — harness_job_state (migrations/025) only
tracks per-job aggregate counts, not per-field structure.

Public API:
    FieldFailure          — one field's failure context (dataclass)
    JobFailureRecord       — one job's full failure record (dataclass)
    append_failure(run_id, path, record) — append one JSONL line, flush immediately
    read_failures(path)                  — yield JobFailureRecord for every line
    FieldAttempt           — one field's attempt context, any outcome (dataclass)
    JobAttemptRecord        — one job's full attempt record, any outcome (dataclass)
    attempts_path_for_run(run_id)        — path for the parallel all-outcomes stream
    append_attempt_record(path, record)  — append one JSONL line, flush immediately
    read_attempt_records(path)           — yield JobAttemptRecord for every line
"""

import dataclasses
import json
import logging
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

FAILURES_DIR = Path(__file__).resolve().parent.parent / "failures"


@dataclasses.dataclass
class FieldFailure:
    reason_code: str
    category_attempted: str | None
    autocomplete: str
    id: str
    role: str
    html_type: str
    options_hash: str
    label: str
    section: str
    required: bool


@dataclasses.dataclass
class JobFailureRecord:
    harness_version: str
    run_id: int
    job_id: str
    ats: str
    sample_phase: str
    company_name: str
    outcome: str
    phase_reached: str | None
    worker_id: int
    field_failures: list[FieldFailure]
    debug_log_ref: str | None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JobFailureRecord":
        field_failures = [FieldFailure(**ff) for ff in d.get("field_failures", [])]
        kwargs = {k: v for k, v in d.items() if k != "field_failures"}
        return cls(field_failures=field_failures, **kwargs)


def failures_path_for_run(run_id: int) -> Path:
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    return FAILURES_DIR / f"greenhouse_run_{run_id}.jsonl"


def append_failure(path: Path, record: JobFailureRecord) -> None:
    """Append one line and flush immediately — same discipline as
    corpus_harvester.py's manifest writer (a crash mid-run must lose at most
    the in-flight job, not buffered-but-unwritten prior results)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")
        f.flush()


def read_failures(path: Path) -> Iterator[JobFailureRecord]:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield JobFailureRecord.from_dict(json.loads(line))


def read_failures_since(path: Path, skip_lines: int) -> list[JobFailureRecord]:
    """Returns records after the first `skip_lines` lines — used by
    checkpoint passes to read only what accumulated since the last
    checkpoint without re-clustering the whole file every time."""
    all_records = list(read_failures(path))
    return all_records[skip_lines:]


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


@dataclasses.dataclass
class FieldAttempt:
    self_reported_verified: bool
    landed: bool
    category: str
    label: str
    reason: str | None
    autocomplete: str
    id: str
    role: str
    html_type: str
    options_hash: str
    required: bool


@dataclasses.dataclass
class JobAttemptRecord:
    harness_version: str
    run_id: int
    job_id: str
    ats: str
    sample_phase: str
    outcome: str
    attempts: list[FieldAttempt]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JobAttemptRecord":
        attempts = [FieldAttempt(**a) for a in d.get("attempts", [])]
        kwargs = {k: v for k, v in d.items() if k != "attempts"}
        return cls(attempts=attempts, **kwargs)


def attempts_path_for_run(run_id: int) -> Path:
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    return FAILURES_DIR / f"attempts_{run_id}.jsonl"


def append_attempt_record(path: Path, record: JobAttemptRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")
        f.flush()


def read_attempt_records(path: Path) -> Iterator[JobAttemptRecord]:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield JobAttemptRecord.from_dict(json.loads(line))

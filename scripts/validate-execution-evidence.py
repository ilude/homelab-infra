#!/usr/bin/env python3
"""Validate the deterministic update-run-journal execution evidence ledger."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

TASKS = ("T1", "V1", "T2", "V2", "T3", "V3", "F1", "F2", "F3", "F4", "F5")
PHASES = {
    "T1": "wave-1", "V1": "wave-1", "T2": "wave-2", "V2": "wave-2",
    "T3": "wave-3", "V3": "wave-3", "F1": "final-gates", "F2": "final-gates",
    "F3": "final-gates", "F4": "final-gates", "F5": "final-gates",
}


class EvidenceError(ValueError):
    """Raised when ledger evidence is missing or inconsistent."""


def parse_timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("timestamps must be nonempty UTC strings")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("timestamps must be ISO-8601 UTC strings") from error
    if parsed.tzinfo != dt.timezone.utc:
        raise EvidenceError("timestamps must use UTC")
    return parsed


def read_records(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise EvidenceError(f"cannot read evidence ledger: {path}") from error
    records: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line:
            raise EvidenceError(f"blank evidence line {number}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvidenceError(f"invalid JSON at line {number}") from error
        if not isinstance(record, dict):
            raise EvidenceError(f"evidence line {number} must be an object")
        records.append(record)
    return records


def validate_records(records: list[dict[str, Any]], through: str, require_archived: bool = False) -> None:
    if through not in TASKS:
        raise EvidenceError(f"unknown task: {through}")
    expected_tasks = TASKS[: TASKS.index(through) + 1]
    if len(records) != len(expected_tasks):
        raise EvidenceError("evidence records do not match the required dependency prefix")
    required = {
        "episode_id", "sequence", "phase_id", "task_id", "validation_command", "status",
        "archive_status", "started_at", "completed_at", "evidence",
    }
    for index, (record, task_id) in enumerate(zip(records, expected_tasks), 1):
        if set(record) != required:
            raise EvidenceError(f"record {index} has unexpected fields")
        if record["episode_id"] != "update-run-journal":
            raise EvidenceError(f"record {index} has an invalid episode ID")
        if record["sequence"] != index or record["task_id"] != task_id:
            raise EvidenceError(f"record {index} is out of dependency order")
        if record["phase_id"] != PHASES[task_id] or record["status"] != "passed":
            raise EvidenceError(f"record {index} has invalid phase or status")
        if not all(isinstance(record[key], str) and record[key] for key in ("validation_command", "evidence")):
            raise EvidenceError(f"record {index} requires command and evidence")
        started_at = parse_timestamp(record["started_at"])
        if parse_timestamp(record["completed_at"]) < started_at:
            raise EvidenceError(f"record {index} completes before it starts")
        expected_archive = "archived" if task_id == "F5" else "not_ready"
        if record["archive_status"] != expected_archive:
            raise EvidenceError(f"record {index} has invalid archive status")
    if require_archived and (through != "F5" or records[-1]["archive_status"] != "archived"):
        raise EvidenceError("archived F5 evidence is required")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--through", required=True, choices=TASKS)
    parser.add_argument("--require-archived", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate_records(read_records(args.ledger), args.through, args.require_archived)
    except EvidenceError as error:
        print(f"execution evidence validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

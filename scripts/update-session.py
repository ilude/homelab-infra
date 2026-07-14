#!/usr/bin/env python3
"""Create and validate local update-run journal episode evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import hashlib
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EPISODE_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
EVENT_TYPES = {
    "episode_started",
    "command_started",
    "command_completed",
    "command_interrupted",
    "command_spawn_failed",
    "reflection_completed",
}
RECIPES = {"update", "validate", "plan"}
FAILURE_CODES = {
    "command-failed",
    "command-interrupted",
    "spawn-not-found",
    "spawn-denied",
    "plan-artifact-missing",
    "journal-write-failed",
}
BOUNDARIES = {
    "episode_files",
    "tracked_or_private_pins",
    "private_artifacts",
    "private_values_migration",
    "root_plan_artifacts",
    "tooling_workdirs",
    "generated_python_cache",
    "docker_runtime_cache",
}


class JournalError(RuntimeError):
    """Raised when journal evidence cannot safely be created or read."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def platform_os_name() -> str:
    return os.name


def format_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise JournalError("timestamps must be timezone-aware UTC values")
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise JournalError("timestamp must be an ISO-8601 UTC string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise JournalError("timestamp must be an ISO-8601 UTC string") from error
    if parsed.tzinfo != dt.timezone.utc:
        raise JournalError("timestamp must use UTC")
    return parsed


def is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def require_regular_path(path: Path) -> None:
    if path.is_symlink() or is_reparse_point(path):
        raise JournalError(f"symlink or reparse point is not allowed: {path}")


def restricted_mode(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


@dataclass(frozen=True)
class ReducedCommand:
    command_id: str
    event_id: str
    sequence: int
    status: str
    failure_code: str | None


class EpisodeLock:
    def __init__(self, journal: "Journal") -> None:
        self.journal = journal
        self.path = journal.episode_dir / ".lock"
        self.owner_path = self.path / "owner.json"
        self.handle: Any | None = None

    def __enter__(self) -> "EpisodeLock":
        self.journal._check_episode_dir()
        try:
            self.path.mkdir(mode=0o700)
        except FileExistsError as error:
            raise JournalError(f"journal lock exists at {self.path}; inspect it before retrying") from error
        restricted_mode(self.path, 0o700)
        try:
            descriptor = os.open(
                self.owner_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
            json.dump({"pid": os.getpid(), "started_at": format_utc(self.journal.clock())}, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            if "handle" in locals():
                handle.close()
            raise
        self.handle = handle
        restricted_mode(self.owner_path, 0o600)
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        try:
            if self.handle is not None:
                self.handle.close()
            release_path = self.journal.episode_dir / f".lock.release-{os.getpid()}-{secrets.token_hex(16)}"
            for attempt in range(5):
                try:
                    os.rename(self.path, release_path)
                    break
                except PermissionError:
                    if platform_os_name() != "nt" or attempt == 4:
                        raise
                    time.sleep(0.02)
            (release_path / "owner.json").unlink()
            release_path.rmdir()
        finally:
            self.handle = None


class Journal:
    def __init__(
        self,
        root: Path,
        episode_id: str,
        *,
        clock: Callable[[], dt.datetime] = utc_now,
        token_source: Callable[[int], str] = secrets.token_hex,
    ) -> None:
        self.root = root.absolute()
        self.episode_id = validate_episode_id(episode_id)
        self.clock = clock
        self.token_source = token_source
        self.episode_dir = self._episode_path()
        self.events_path = self.episode_dir / "events.jsonl"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        clock: Callable[[], dt.datetime] = utc_now,
        token_source: Callable[[int], str] = secrets.token_hex,
    ) -> "Journal":
        token = token_source(4)
        if not re.fullmatch(r"[0-9a-f]{8}", token):
            raise JournalError("token source returned an invalid episode token")
        episode_id = f"{format_utc(clock()).replace('-', '').replace(':', '')}-{token}"
        journal = cls(root, episode_id, clock=clock, token_source=token_source)
        journal._create_episode_dir()
        return journal

    def _episode_path(self) -> Path:
        path = self.root / self.episode_id
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise JournalError("episode path escapes journal root") from error
        return path

    def _check_journal_root_path(self) -> None:
        repository_root = self.root.parents[1]
        require_regular_path(repository_root)
        current = repository_root
        for component in (self.root.parent.name, self.root.name):
            current /= component
            if current.exists():
                require_regular_path(current)

    def _create_episode_dir(self) -> None:
        self._check_journal_root_path()
        self.root.mkdir(parents=True, exist_ok=True)
        self._check_journal_root_path()
        require_regular_path(self.root)
        restricted_mode(self.root, 0o700)
        try:
            self.episode_dir.mkdir(mode=0o700)
        except FileExistsError as error:
            raise JournalError(f"episode already exists: {self.episode_id}") from error
        self._check_episode_dir()
        restricted_mode(self.episode_dir, 0o700)

    def _check_episode_dir(self) -> None:
        self._check_journal_root_path()
        require_regular_path(self.root)
        if not self.episode_dir.is_dir():
            raise JournalError(f"episode does not exist: {self.episode_id}")
        require_regular_path(self.episode_dir)
        if self.episode_dir.resolve() != self.episode_dir:
            raise JournalError("episode path must not resolve through a link")

    def lock(self) -> EpisodeLock:
        return EpisodeLock(self)

    def _read_events_bytes(self) -> bytes:
        if self.events_path.exists() or self.events_path.is_symlink():
            require_regular_path(self.events_path)
        try:
            descriptor = os.open(self.events_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return b""
        except OSError as error:
            raise JournalError("cannot safely open events.jsonl") from error
        try:
            file_stat = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(descriptor)
            raise JournalError("events.jsonl must be a regular file")
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()

    def _parse_events(self, data: bytes) -> list[dict[str, Any]]:
        if data and not data.endswith(b"\n"):
            raise JournalError("events.jsonl has a torn final line")
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(data.splitlines(), 1):
            try:
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise JournalError(f"invalid JSONL at line {line_number}") from error
            if not isinstance(event, dict):
                raise JournalError(f"event at line {line_number} must be an object")
            events.append(event)
        validate_events(events, self.episode_id, self.episode_dir)
        return events

    def read_events(self) -> list[dict[str, Any]]:
        self._check_episode_dir()
        return self._parse_events(self._read_events_bytes())

    def _append_event_locked(self, event: dict[str, Any]) -> None:
        self._check_episode_dir()
        existing = self._read_events_bytes()
        events = self._parse_events(existing)
        event = dict(event)
        event["sequence"] = len(events) + 1
        event["event_id"] = f"{self.episode_id}-{event['sequence']:06d}"
        event["episode_id"] = self.episode_id
        validate_events([*events, event], self.episode_id, self.episode_dir)
        encoded = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        temporary = self.episode_dir / f".events.{event['sequence']:06d}.tmp"
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(existing + encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.events_path)
            restricted_mode(self.events_path, 0o600)
        except OSError as error:
            raise JournalError("cannot safely publish events.jsonl") from error
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def append_event(self, event: dict[str, Any]) -> None:
        with self.lock():
            self._append_event_locked(event)

    def start(self) -> None:
        now = format_utc(self.clock())
        self.append_event(
            event_template(
                "episode_started",
                status="started",
                started_at=now,
                completed_at=now,
            )
        )


def validate_episode_id(episode_id: str) -> str:
    if not EPISODE_ID_RE.fullmatch(episode_id):
        raise JournalError("episode ID must match YYYYMMDDTHHMMSSZ-<8 lowercase hex>")
    return episode_id


def event_template(
    event_type: str,
    *,
    status: str,
    started_at: str,
    completed_at: str | None,
    command_id: str | None = None,
    recipe: str | None = None,
    command_argv: list[str] | None = None,
    mutation_boundaries: list[str] | None = None,
    exit_code: int | None = None,
    signal: int | None = None,
    failure_code: str | None = None,
    evidence_paths: list[str] | None = None,
    report_generation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "command_id": command_id,
        "recipe": recipe,
        "command_argv": command_argv or [],
        "mutation_boundaries": mutation_boundaries or [],
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "signal": signal,
        "failure_code": failure_code,
        "evidence_paths": evidence_paths or [],
        "report_generation_id": report_generation_id,
    }


def validate_events(events: Iterable[dict[str, Any]], episode_id: str, episode_dir: Path) -> None:
    commands: dict[str, dict[str, Any]] = {}
    used_command_ids: set[str] = set()
    event_list = list(events)
    if event_list and event_list[0].get("event_type") != "episode_started":
        raise JournalError("the first event must be episode_started")
    for expected_sequence, event in enumerate(event_list, 1):
        required = {
            "schema_version", "episode_id", "event_id", "sequence", "event_type", "command_id", "recipe",
            "command_argv", "mutation_boundaries", "status", "started_at", "completed_at", "exit_code",
            "signal", "failure_code", "evidence_paths", "report_generation_id",
        }
        if set(event) != required:
            raise JournalError("event does not match schema version 1")
        if (
            not isinstance(event["schema_version"], int) or isinstance(event["schema_version"], bool)
            or not isinstance(event["episode_id"], str) or not isinstance(event["event_id"], str)
            or not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool)
            or not isinstance(event["event_type"], str) or not isinstance(event["status"], str)
            or not isinstance(event["command_argv"], list) or not all(isinstance(value, str) for value in event["command_argv"])
            or not isinstance(event["mutation_boundaries"], list) or not all(isinstance(value, str) for value in event["mutation_boundaries"])
            or not isinstance(event["evidence_paths"], list) or not all(isinstance(value, str) for value in event["evidence_paths"])
            or event["command_id"] is not None and not isinstance(event["command_id"], str)
            or event["recipe"] is not None and not isinstance(event["recipe"], str)
            or event["completed_at"] is not None and not isinstance(event["completed_at"], str)
            or event["exit_code"] is not None and (not isinstance(event["exit_code"], int) or isinstance(event["exit_code"], bool))
            or event["signal"] is not None and (not isinstance(event["signal"], int) or isinstance(event["signal"], bool))
            or event["failure_code"] is not None and not isinstance(event["failure_code"], str)
            or event["report_generation_id"] is not None and not isinstance(event["report_generation_id"], str)
        ):
            raise JournalError("event contains malformed field types")
        if event["schema_version"] != SCHEMA_VERSION or event["episode_id"] != episode_id:
            raise JournalError("event schema version or episode ID is invalid")
        if event["sequence"] != expected_sequence or event["event_id"] != f"{episode_id}-{expected_sequence:06d}":
            raise JournalError("event sequence is not contiguous")
        event_type = event["event_type"]
        if event_type not in EVENT_TYPES:
            raise JournalError("event type is invalid")
        started_at = parse_utc(event["started_at"])
        completed_at = event["completed_at"]
        if completed_at is not None and parse_utc(completed_at) < started_at:
            raise JournalError("completed_at precedes started_at")
        command_event = event_type.startswith("command_")
        if command_event:
            if not isinstance(event["command_id"], str) or not event["command_id"]:
                raise JournalError("command event requires command_id")
            if event["recipe"] not in RECIPES or not isinstance(event["command_argv"], list):
                raise JournalError("command event has invalid recipe")
            if len(set(event["mutation_boundaries"])) != len(event["mutation_boundaries"]) or not set(event["mutation_boundaries"]).issubset(BOUNDARIES):
                raise JournalError("command event has invalid mutation boundaries")
        elif any(event[key] not in (None, []) for key in ("command_id", "recipe", "command_argv", "mutation_boundaries")):
            raise JournalError("non-command event contains command fields")
        for evidence_path in event["evidence_paths"]:
            if not isinstance(evidence_path, str) or Path(evidence_path).is_absolute() or ".." in Path(evidence_path).parts:
                raise JournalError("evidence path must be relative to the episode")
            evidence = episode_dir / evidence_path
            try:
                evidence.resolve(strict=True).relative_to(episode_dir.resolve())
            except (FileNotFoundError, ValueError) as error:
                raise JournalError("evidence path escapes the episode") from error
            component = evidence
            while component != episode_dir:
                require_regular_path(component)
                component = component.parent
            if not evidence.is_file():
                raise JournalError("evidence path must be a regular file")
        if event_type == "episode_started":
            if (
                expected_sequence != 1 or event["status"] != "started" or completed_at is None
                or any(event[key] is not None for key in ("exit_code", "signal", "failure_code", "report_generation_id"))
            ):
                raise JournalError("episode_started is invalid")
        elif event_type == "command_started":
            expected_argv = ["just", event["recipe"]]
            if event["command_id"] in used_command_ids:
                raise JournalError("command ID is reused")
            if (
                event["status"] != "running" or completed_at is not None
                or event["command_argv"] != expected_argv
                or any(event[key] is not None for key in ("exit_code", "signal", "failure_code", "report_generation_id"))
            ):
                raise JournalError("command_started is invalid")
            commands[event["command_id"]] = event
            used_command_ids.add(event["command_id"])
        elif event_type in {"command_completed", "command_interrupted", "command_spawn_failed"}:
            start = commands.get(event["command_id"])
            if (
                start is None or event["status"] not in {"passed", "failed"} or completed_at is None
                or any(event[key] != start[key] for key in ("recipe", "command_argv", "mutation_boundaries"))
                or event["report_generation_id"] is not None
            ):
                raise JournalError("terminal command event is invalid")
            if event_type == "command_completed":
                max_exit_code = None if platform_os_name() == "nt" else 255
                if (
                    not isinstance(event["exit_code"], int)
                    or event["exit_code"] < 0
                    or (max_exit_code is not None and event["exit_code"] > max_exit_code)
                    or event["signal"] is not None
                ):
                    raise JournalError("command completion exit status is invalid")
                if (event["exit_code"] == 0) != (event["status"] == "passed"):
                    raise JournalError("command completion status is invalid")
            elif event["status"] != "failed" or event["exit_code"] is not None:
                raise JournalError("failed terminal event has passed status")
            if event_type == "command_interrupted" and (not isinstance(event["signal"], int) or event["signal"] <= 0):
                raise JournalError("interrupted command requires a positive signal")
            if event_type == "command_spawn_failed" and event["signal"] is not None:
                raise JournalError("spawn failure cannot contain a signal")
            if event["status"] == "passed":
                if event["failure_code"] is not None:
                    raise JournalError("passed command has a failure code")
            elif event["failure_code"] not in FAILURE_CODES:
                raise JournalError("failed terminal event requires a stable failure code")
            commands.pop(event["command_id"])
        elif event_type == "reflection_completed":
            if (
                event["status"] != "passed" or completed_at is None
                or event["evidence_paths"] != list(REPORT_FILENAMES)
                or not isinstance(event["report_generation_id"], str) or not event["report_generation_id"]
                or any(event[key] is not None for key in ("exit_code", "signal", "failure_code"))
            ):
                raise JournalError("reflection_completed is invalid")


def reduce_commands(events: Iterable[dict[str, Any]]) -> list[ReducedCommand]:
    starts: dict[str, dict[str, Any]] = {}
    reduced: list[ReducedCommand] = []
    for event in sorted(events, key=lambda item: item["sequence"]):
        if event["event_type"] == "command_started":
            starts[event["command_id"]] = event
        elif event["event_type"] in {"command_completed", "command_interrupted", "command_spawn_failed"}:
            starts.pop(event["command_id"], None)
            reduced.append(ReducedCommand(event["command_id"], event["event_id"], event["sequence"], event["status"], event["failure_code"]))
    for event in starts.values():
        reduced.append(ReducedCommand(event["command_id"], event["event_id"], event["sequence"], "incomplete", "interrupted-unknown"))
    return sorted(reduced, key=lambda item: item.sequence)


RECOMMENDATIONS = {
    "spawn-not-found": "preflight",
    "spawn-denied": "preflight",
    "plan-artifact-missing": "workflow-guard",
    "journal-write-failed": "workflow-guard",
    "command-failed": "no-action",
    "command-interrupted": "no-action",
    "interrupted-unknown": "no-action",
}
REPORT_FILENAMES = ("summary.json", "failures.md", "commands.md")


@dataclass(frozen=True)
class ReportCommand:
    event: dict[str, Any]
    status: str
    failure_code: str | None


def report_commands(events: Iterable[dict[str, Any]]) -> list[ReportCommand]:
    """Reduce command events into terminal events and incomplete starts."""
    starts: dict[str, dict[str, Any]] = {}
    records: list[ReportCommand] = []
    for event in sorted(events, key=lambda item: item["sequence"]):
        if event["event_type"] == "command_started":
            starts[event["command_id"]] = event
        elif event["event_type"] in {"command_completed", "command_interrupted", "command_spawn_failed"}:
            starts.pop(event["command_id"], None)
            records.append(ReportCommand(event, event["status"], event["failure_code"]))
    records.extend(
        ReportCommand(event, "incomplete", "interrupted-unknown") for event in starts.values()
    )
    return sorted(records, key=lambda record: record.event["sequence"])


def compact_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def markdown_metadata(report_type: str, episode_id: str, generation_id: str, event_ids: list[str]) -> str:
    metadata = {
        "episode_id": episode_id,
        "event_ids": event_ids,
        "report_generation_id": generation_id,
        "report_type": report_type,
        "schema_version": SCHEMA_VERSION,
    }
    return f"<!-- update-run-journal:{compact_json(metadata)} -->\n"


def markdown_field(name: str, value: object) -> str:
    return f"- {name}: {compact_json(value)}\n"


def render_failures(episode_id: str, generation_id: str, commands: list[ReportCommand]) -> str:
    failures = [record for record in commands if record.status != "passed"]
    output = [markdown_metadata("failures", episode_id, generation_id, [record.event["event_id"] for record in failures]), "# Failures\n"]
    if not failures:
        output.append("None.\n")
    for record in failures:
        event = record.event
        output.append(f"## {event['sequence']} {event['event_id']}\n")
        for name, value in (
            ("recipe", event["recipe"]), ("status", record.status),
            ("exit_code", event["exit_code"] if record.status != "incomplete" else None),
            ("signal", event["signal"] if record.status != "incomplete" else None),
            ("failure_code", record.failure_code),
            ("recommendation", RECOMMENDATIONS[record.failure_code]),
        ):
            output.append(markdown_field(name, value))
    return "".join(output)


def render_commands(episode_id: str, generation_id: str, commands: list[ReportCommand]) -> str:
    output = [markdown_metadata("commands", episode_id, generation_id, [record.event["event_id"] for record in commands]), "# Commands\n"]
    if not commands:
        output.append("None.\n")
    for record in commands:
        event = record.event
        output.append(f"## {event['sequence']} {event['event_id']}\n")
        for name, value in (
            ("recipe", event["recipe"]), ("command_argv", event["command_argv"]),
            ("status", record.status),
            ("exit_code", event["exit_code"] if record.status != "incomplete" else None),
            ("signal", event["signal"] if record.status != "incomplete" else None),
            ("failure_code", record.failure_code), ("mutation_boundaries", event["mutation_boundaries"]),
        ):
            output.append(markdown_field(name, value))
    return "".join(output)


def render_summary(episode_id: str, generation_id: str, generated_at: str, commands: list[ReportCommand]) -> str:
    failures = [record for record in commands if record.status != "passed"]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "report_generation_id": generation_id,
        "generated_at": generated_at,
        "episode_status": "incomplete" if any(record.status == "incomplete" for record in commands) else "failed" if failures else "passed",
        "first_failure_event_id": failures[0].event["event_id"] if failures else None,
        "command_event_ids": [record.event["event_id"] for record in commands],
        "failure_event_ids": [record.event["event_id"] for record in failures],
        "classifications": [{"event_id": record.event["event_id"], "failure_code": record.failure_code} for record in failures],
        "recommendations": [{"event_ids": [record.event["event_id"]], "kind": RECOMMENDATIONS[record.failure_code]} for record in failures],
    }
    return compact_json(summary) + "\n"


def write_report_files(journal: Journal, reports: dict[str, str], generation_id: str) -> None:
    temporary_paths: dict[str, Path] = {}
    try:
        for name in REPORT_FILENAMES:
            temporary = journal.episode_dir / f".{name}.{generation_id}.tmp"
            temporary_paths[name] = temporary
            require_regular_path(journal.episode_dir)
            with temporary.open("xb") as handle:
                handle.write(reports[name].encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            restricted_mode(temporary, 0o600)
        for name in REPORT_FILENAMES:
            os.replace(temporary_paths[name], journal.episode_dir / name)
            restricted_mode(journal.episode_dir / name, 0o600)
    finally:
        for temporary in temporary_paths.values():
            if temporary.exists():
                temporary.unlink()


def reflect(journal: Journal) -> int:
    try:
        with journal.lock():
            try:
                events = journal.read_events()
            except JournalError as error:
                print(f"update journal reflection failed: {error}", file=sys.stderr)
                return 1
            commands = report_commands(events)
            token = journal.token_source(8)
            if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{16}", token):
                raise JournalError("token source returned an invalid report token")
            generation_id = f"report-{token}"
            generated_at = format_utc(journal.clock())
            reports = {
                "summary.json": render_summary(journal.episode_id, generation_id, generated_at, commands),
                "failures.md": render_failures(journal.episode_id, generation_id, commands),
                "commands.md": render_commands(journal.episode_id, generation_id, commands),
            }
            write_report_files(journal, reports, generation_id)
            journal._append_event_locked(event_template(
                "reflection_completed", status="passed", started_at=generated_at,
                completed_at=format_utc(journal.clock()), evidence_paths=list(REPORT_FILENAMES),
                report_generation_id=generation_id,
            ))
    except (JournalError, OSError) as error:
        print(f"update journal reflection failed: {error}", file=sys.stderr)
        return 125
    return 0


def parse_markdown_report(path: Path, report_type: str, episode_id: str, generation_id: str) -> tuple[list[str], str]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise JournalError(f"cannot read {path.name}") from error
    if "\r" in content or not content.endswith("\n"):
        raise JournalError(f"{path.name} has invalid line endings")
    lines = content.splitlines(keepends=True)
    if len(lines) < 2 or not lines[0].startswith("<!-- update-run-journal:") or lines[0][-5:] != " -->\n":
        raise JournalError(f"{path.name} has invalid metadata")
    try:
        metadata = json.loads(lines[0][len("<!-- update-run-journal:"):-5])
    except json.JSONDecodeError as error:
        raise JournalError(f"{path.name} has invalid metadata JSON") from error
    expected_metadata = {"episode_id", "event_ids", "report_generation_id", "report_type", "schema_version"}
    if not isinstance(metadata, dict) or set(metadata) != expected_metadata or metadata != {
        "episode_id": episode_id, "event_ids": metadata.get("event_ids"),
        "report_generation_id": generation_id, "report_type": report_type, "schema_version": SCHEMA_VERSION,
    } or not isinstance(metadata["event_ids"], list) or not all(isinstance(value, str) for value in metadata["event_ids"]):
        raise JournalError(f"{path.name} metadata does not match episode")
    return metadata["event_ids"], content


def verify(journal: Journal) -> int:
    try:
        lock = journal.lock()
        lock.__enter__()
    except JournalError as error:
        print(f"update journal verification failed: {error}", file=sys.stderr)
        return 125
    try:
        events = journal.read_events()
        reflections = [event for event in events if event["event_type"] == "reflection_completed"]
        if not reflections:
            raise JournalError("no successful reflection exists")
        generation_id = reflections[-1]["report_generation_id"]
        commands = report_commands(events)
        summary_path = journal.episode_dir / "summary.json"
        try:
            summary_bytes = summary_path.read_bytes()
            summary = json.loads(summary_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise JournalError("summary.json is invalid") from error
        required = {"schema_version", "episode_id", "report_generation_id", "generated_at", "episode_status", "first_failure_event_id", "command_event_ids", "failure_event_ids", "classifications", "recommendations"}
        if not isinstance(summary, dict) or set(summary) != required or not isinstance(summary.get("generated_at"), str):
            raise JournalError("summary.json does not match report schema")
        parse_utc(summary["generated_at"])
        expected_summary = render_summary(journal.episode_id, generation_id, summary["generated_at"], commands).encode("utf-8")
        if summary_bytes != expected_summary:
            raise JournalError("summary.json does not match canonical report bytes")
        for name, report_type, renderer in (
            ("failures.md", "failures", render_failures), ("commands.md", "commands", render_commands),
        ):
            ids, content = parse_markdown_report(journal.episode_dir / name, report_type, journal.episode_id, generation_id)
            expected = renderer(journal.episode_id, generation_id, commands)
            expected_ids = [record.event["event_id"] for record in (commands if report_type == "commands" else [item for item in commands if item.status != "passed"])]
            if content != expected or ids != expected_ids:
                raise JournalError(f"{name} does not match events")
    except JournalError as error:
        print(f"update journal verification failed: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"update journal verification failed: {error}", file=sys.stderr)
        return 125
    finally:
        lock.__exit__(None, None, None)
    return 0


class ParentInterrupted(Exception):
    """Raised after the parent receives an interrupt signal while waiting."""

    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number


RECIPE_BOUNDARIES = {
    "update": [
        "episode_files",
        "tracked_or_private_pins",
        "private_artifacts",
        "tooling_workdirs",
        "docker_runtime_cache",
    ],
    "validate": [
        "episode_files",
        "private_values_migration",
        "tooling_workdirs",
        "generated_python_cache",
        "docker_runtime_cache",
    ],
    "plan": [
        "episode_files",
        "private_values_migration",
        "root_plan_artifacts",
        "tooling_workdirs",
        "docker_runtime_cache",
    ],
}


class RecipeRunner:
    """Observe one immutable public recipe without capturing its output."""

    def __init__(
        self,
        journal: Journal,
        cwd: Path,
        *,
        process_factory: Callable[..., Any] = subprocess.Popen,
        event_builder: Callable[..., dict[str, Any]] = event_template,
    ) -> None:
        self.journal = journal
        self.cwd = cwd
        self.process_factory = process_factory
        self.event_builder = event_builder

    def _event(self, event_type: str, **values: Any) -> dict[str, Any]:
        return self.event_builder(event_type, **values)

    def _command_id(self) -> str:
        token = self.journal.token_source(8)
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{16}", token):
            raise JournalError("token source returned an invalid command token")
        return f"command-{token}"

    def _append_terminal(
        self,
        event_type: str,
        *,
        command_id: str,
        recipe: str,
        started_at: str,
        exit_code: int | None = None,
        signal_number: int | None = None,
        failure_code: str | None = None,
        evidence_paths: list[str] | None = None,
    ) -> None:
        status = "passed" if event_type == "command_completed" and exit_code == 0 else "failed"
        self.journal.append_event(self._event(
            event_type,
            status=status,
            started_at=started_at,
            completed_at=format_utc(self.journal.clock()),
            command_id=command_id,
            recipe=recipe,
            command_argv=["just", recipe],
            mutation_boundaries=RECIPE_BOUNDARIES[recipe],
            exit_code=exit_code,
            signal=signal_number,
            failure_code=failure_code,
            evidence_paths=evidence_paths,
        ))

    def _plan_evidence(self) -> list[str]:
        rows: list[dict[str, str]] = []
        for name in ("tfplan", "tfplan.meta.json"):
            path = self.cwd / name
            require_regular_path(path)
            if not path.is_file():
                raise JournalError(f"plan artifact is missing: {name}")
            rows.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        evidence = self.journal.episode_dir / "plan-artifacts.json"
        require_regular_path(self.journal.episode_dir)
        encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        with evidence.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        restricted_mode(evidence, 0o600)
        return [evidence.name]

    def _forward_interruption(self, process: Any) -> None:
        try:
            if platform_os_name() == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (OSError, ProcessLookupError):
            pass

    def run(self, recipe: str) -> int:
        if recipe not in RECIPE_BOUNDARIES:
            raise JournalError("recipe is not allowlisted")
        command_id = self._command_id()
        started_at = format_utc(self.journal.clock())
        boundaries = ", ".join(RECIPE_BOUNDARIES[recipe])
        print(f"Mutation boundary before spawn ({recipe}): {boundaries}", file=sys.stderr)
        try:
            self.journal.append_event(self._event(
                "command_started",
                status="running",
                started_at=started_at,
                completed_at=None,
                command_id=command_id,
                recipe=recipe,
                command_argv=["just", recipe],
                mutation_boundaries=RECIPE_BOUNDARIES[recipe],
            ))
        except Exception as error:
            print(f"update journal failed before spawn: {error}", file=sys.stderr)
            return 125

        try:
            process = self.process_factory(
                ["just", recipe], cwd=self.cwd, shell=False,
                start_new_session=platform_os_name() == "posix",
            )
        except FileNotFoundError:
            return self._persist_spawn_failure(command_id, recipe, started_at, "spawn-not-found", 127)
        except (PermissionError, OSError) as error:
            print(f"update journal launch failed: {error}", file=sys.stderr)
            return self._persist_spawn_failure(command_id, recipe, started_at, "spawn-denied", 126)

        interrupted_signal: int | None = None

        def interrupt_handler(signal_number: int, _frame: Any) -> None:
            raise ParentInterrupted(signal_number)

        previous_handlers: dict[int, Any] = {}
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            try:
                previous_handlers[signal_number] = signal.signal(signal_number, interrupt_handler)
            except (ValueError, OSError):
                pass
        try:
            try:
                return_code = process.wait()
            except KeyboardInterrupt:
                interrupted_signal = signal.SIGINT
                self._forward_interruption(process)
                return_code = process.wait()
            except ParentInterrupted as interruption:
                interrupted_signal = interruption.signal_number
                self._forward_interruption(process)
                return_code = process.wait()
        finally:
            for signal_number, previous_handler in previous_handlers.items():
                signal.signal(signal_number, previous_handler)
        return self._persist_wait_result(
            command_id, recipe, started_at, return_code, interrupted_signal=interrupted_signal,
        )

    def _persist_spawn_failure(self, command_id: str, recipe: str, started_at: str, code: str, status: int) -> int:
        try:
            self._append_terminal("command_spawn_failed", command_id=command_id, recipe=recipe, started_at=started_at, failure_code=code)
        except Exception as error:
            print(f"update journal failed: {error}", file=sys.stderr)
            return 125
        return status

    def _persist_wait_result(
        self, command_id: str, recipe: str, started_at: str, return_code: int, *, interrupted_signal: int | None,
    ) -> int:
        if platform_os_name() == "posix" and return_code < 0:
            event_type, exit_code, signal_number, failure_code, wrapper_status = (
                "command_interrupted", None, -return_code, "command-interrupted", 128 - return_code,
            )
        else:
            event_type, exit_code, signal_number, failure_code, wrapper_status = (
                "command_completed", return_code, None, None if return_code == 0 else "command-failed", return_code,
            )
        if interrupted_signal is not None and platform_os_name() == "posix" and event_type == "command_completed" and return_code == 0:
            event_type, exit_code, signal_number, failure_code, wrapper_status = (
                "command_interrupted", None, interrupted_signal, "command-interrupted", 128 + interrupted_signal,
            )
        evidence_paths: list[str] = []
        if event_type == "command_completed" and return_code == 0 and recipe == "plan":
            try:
                evidence_paths = self._plan_evidence()
            except Exception as error:
                print(f"update journal failed: {error}", file=sys.stderr)
                return 125
        try:
            self._append_terminal(
                event_type, command_id=command_id, recipe=recipe, started_at=started_at,
                exit_code=exit_code, signal_number=signal_number, failure_code=failure_code,
                evidence_paths=evidence_paths,
            )
        except Exception as error:
            print(f"update journal failed: {error}", file=sys.stderr)
            return wrapper_status if wrapper_status != 0 else 125
        return wrapper_status


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--episode", required=True)
    run_parser.add_argument("recipe", choices=tuple(sorted(RECIPES)))
    for command in ("reflect", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--episode", required=True)
    args = parser.parse_args(argv)
    if args.command in {"run", "reflect", "verify"}:
        try:
            validate_episode_id(args.episode)
        except JournalError as error:
            parser.error(str(error))
    root = repository_root() / ".tmp" / "update-runs"
    try:
        if args.command == "start":
            journal = Journal.create(root)
            journal.start()
            print(journal.episode_id)
            return 0
        journal = Journal(root, args.episode)
        if args.command == "run":
            return RecipeRunner(journal, repository_root()).run(args.recipe)
        if args.command == "reflect":
            return reflect(journal)
        return verify(journal)
    except (JournalError, OSError) as error:
        print(f"update journal failed: {error}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())

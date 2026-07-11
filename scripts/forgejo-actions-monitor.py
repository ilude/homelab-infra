#!/usr/bin/env python3
"""Read-only Forgejo Actions monitor for the private values repository."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
INVENTORY = "values/ansible/inventory/local.yml"
TFVARS_INVENTORY = "infra/ansible/inventory/tfvars.py"
HOST = "pve_target"

STATUS = {
    0: "unknown",
    1: "success",
    2: "failure",
    3: "cancelled",
    4: "skipped",
    5: "waiting",
    6: "running",
    7: "blocked",
}
TERMINAL_OK = {"success", "skipped"}
TERMINAL_BAD = {"failure", "cancelled", "blocked", "unknown"}
TERMINAL = TERMINAL_OK | TERMINAL_BAD

REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization:\s*)(?:basic|bearer)?\s*[^\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASS|API_KEY)[A-Z0-9_]*)=([^\s]+)"), r"\1=<redacted>"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "<token>"),
    (re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])"), "<ip>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"https?://[^\s]+"), "<url>"),
    (re.compile(r"git@[^\s:]+:[^\s]+"), "<ssh-url>"),
)


class MonitorError(RuntimeError):
    pass


def status_name(value: int | str | None) -> str:
    try:
        return STATUS[int(value)]
    except (TypeError, ValueError, KeyError):
        return "unknown"


def age(timestamp: int | str | None) -> str:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return "-"
    if value <= 0:
        return "-"
    seconds = max(0, int(datetime.now(timezone.utc).timestamp()) - value)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def duration(started: int | str | None, stopped: int | str | None) -> str:
    try:
        start = int(started or 0)
        stop = int(stopped or 0)
    except (TypeError, ValueError):
        return "-"
    if start <= 0:
        return "-"
    if stop <= 0:
        stop = int(datetime.now(timezone.utc).timestamp())
    seconds = max(0, stop - start)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minute = divmod(minutes, 60)
    return f"{hours}h{minute:02d}m"


def redact(text: str) -> str:
    redacted = text
    for pattern, replacement in REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def run_ansible_shell(command: str) -> str:
    inventory_args = ["-i", INVENTORY, "-i", TFVARS_INVENTORY]
    if shutil.which("ansible") and Path("/workspace").exists():
        argv = ["ansible", HOST, *inventory_args, "-m", "shell", "-a", command]
    else:
        argv = [
            "bash",
            "scripts/run-infra.sh",
            "ansible",
            HOST,
            *inventory_args,
            "-m",
            "shell",
            "-a",
            command,
        ]
    result = subprocess.run(
        argv,
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise MonitorError(redact(output.strip()))
    marker = ">>\n"
    if marker in result.stdout:
        return result.stdout.split(marker, 1)[1].strip()
    lines = [line for line in result.stdout.splitlines() if not line.startswith(" Container ")]
    if lines and " | " in lines[0]:
        return "\n".join(lines[1:]).strip()
    return "\n".join(lines).strip()


def run_pve_pct(command: str) -> str:
    guarded_command = (
        'expected={{ proxmox_node_name | quote }}; '
        'actual="$(hostname -s 2>/dev/null || true)"; '
        'if [ "$actual" != "$expected" ]; then '
        'printf "%s\\n" "refusing pct command: connected host is not the configured Proxmox node" >&2; '
        "exit 1; "
        "fi; "
        + command
    )
    return run_ansible_shell(guarded_command)


def forgejo_sql(query: str) -> list[dict[str, Any]]:
    escaped = shell_quote(query)
    command = (
        "pct exec {{ forgejo_vmid | string }} -- runuser -u git -- "
        f"sqlite3 -readonly -json /var/lib/forgejo/data/forgejo.db {escaped}"
    )
    raw = run_pve_pct(command)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise MonitorError(f"failed to parse Forgejo SQLite JSON: {error}\n{redact(raw)}") from error


def latest_runs(limit: int) -> list[dict[str, Any]]:
    return forgejo_sql(
        "select r.id, r.status, r.event, r.workflow_id, r.created, r.updated, "
        "coalesce(j.name, '-') as job_name, coalesce(j.status, 0) as job_status, "
        "coalesce(j.task_id, 0) as task_id, coalesce(j.started, 0) as started, "
        "coalesce(j.stopped, 0) as stopped "
        "from action_run r left join action_run_job j on j.run_id = r.id "
        f"order by r.id desc limit {int(limit)}"
    )


def print_status(limit: int, as_json: bool) -> None:
    rows = latest_runs(limit)
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'RUN':>5}  {'STATUS':<9}  {'WORKFLOW':<16}  {'EVENT':<8}  {'AGE':>6}  {'DURATION':>9}  JOB")
    for row in rows:
        run_status = status_name(row.get("status"))
        job_status = status_name(row.get("job_status"))
        print(
            f"{row.get('id', '-'):>5}  {run_status:<9}  "
            f"{str(row.get('workflow_id', '-')):<16}  {str(row.get('event', '-')):<8}  "
            f"{age(row.get('created')):>6}  {duration(row.get('started'), row.get('stopped')):>9}  "
            f"{row.get('job_name', '-')}:{job_status}"
        )


def run_id_or_latest(value: str) -> int:
    if value != "latest":
        return int(value)
    rows = forgejo_sql("select id from action_run order by id desc limit 1")
    if not rows:
        raise MonitorError("no Forgejo Actions runs found")
    return int(rows[0]["id"])


def run_state(run_id: int) -> dict[str, Any]:
    rows = forgejo_sql(
        "select r.id, r.status, r.workflow_id, coalesce(j.name, '-') as job_name, "
        "coalesce(j.status, 0) as job_status, coalesce(j.started, 0) as started, "
        "coalesce(j.stopped, 0) as stopped, coalesce(j.task_id, 0) as task_id "
        "from action_run r left join action_run_job j on j.run_id = r.id "
        f"where r.id = {int(run_id)} limit 1"
    )
    if not rows:
        raise MonitorError(f"run {run_id} not found")
    return rows[0]


def watch(run: str, interval: int, timeout: int) -> int:
    run_id = run_id_or_latest(run)
    deadline = time.monotonic() + timeout if timeout else None
    last = ""
    while True:
        row = run_state(run_id)
        current = status_name(row.get("status"))
        job = status_name(row.get("job_status"))
        line = f"run {run_id}: {current} job {row.get('job_name', '-')}:{job} duration {duration(row.get('started'), row.get('stopped'))}"
        if line != last:
            print(line, flush=True)
            last = line
        if current in TERMINAL:
            return 0 if current in TERMINAL_OK else 1
        if deadline and time.monotonic() > deadline:
            print(f"run {run_id}: monitor timeout", file=sys.stderr)
            return 124
        time.sleep(interval)


def print_runners(as_json: bool) -> None:
    rows = forgejo_sql(
        "select id, name, owner_id, repo_id, last_online, last_active, agent_labels "
        "from action_runner order by id"
    )
    service = run_pve_pct(
        "pct exec {{ forgejo_runner_vmid | string }} -- systemctl is-active forgejo-runner || true"
    ).splitlines()[-1].strip()
    if as_json:
        print(json.dumps({"service": service, "runners": rows}, indent=2))
        return
    print(f"runner service: {service}")
    print(f"{'ID':>3}  {'NAME':<20}  {'SCOPE':<8}  {'LAST_SEEN':>9}  LABELS")
    for row in rows:
        scope = "global"
        if int(row.get("repo_id") or 0):
            scope = "repo"
        elif int(row.get("owner_id") or 0):
            scope = "owner"
        labels = row.get("agent_labels") or "[]"
        print(f"{row.get('id', '-'):>3}  {str(row.get('name', '-')):<20}  {scope:<8}  {age(row.get('last_online')):>9}  {labels}")


def print_logs(run: str, tail: int, unsafe: bool) -> None:
    run_id = run_id_or_latest(run)
    command = (
        "pct exec {{ forgejo_vmid | string }} -- bash -lc "
        + shell_quote(
            "path=$(find /var/lib/forgejo/data/actions_log -type f -name '"
            + str(run_id)
            + ".log.zst' | sort | tail -n1); "
            "if [ -z \"$path\" ]; then echo 'log not found'; exit 1; fi; "
            "zstdcat \"$path\" | tail -n "
            + str(int(tail))
        )
    )
    text = run_pve_pct(command)
    print(text if unsafe else redact(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--limit", type=int, default=10)
    status.add_argument("--json", action="store_true")

    runners = sub.add_parser("runners")
    runners.add_argument("--json", action="store_true")

    watch_cmd = sub.add_parser("watch")
    watch_cmd.add_argument("run", nargs="?", default="latest")
    watch_cmd.add_argument("--interval", type=int, default=5)
    watch_cmd.add_argument("--timeout", type=int, default=1800)

    logs = sub.add_parser("logs")
    logs.add_argument("run", nargs="?", default="latest")
    logs.add_argument("--tail", type=int, default=200)
    logs.add_argument("--unsafe-no-redact", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            print_status(args.limit, args.json)
        elif args.command == "runners":
            print_runners(args.json)
        elif args.command == "watch":
            return watch(args.run, args.interval, args.timeout)
        elif args.command == "logs":
            print_logs(args.run, args.tail, args.unsafe_no_redact)
    except MonitorError as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

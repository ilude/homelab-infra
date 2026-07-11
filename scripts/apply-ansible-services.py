#!/usr/bin/env python3
"""Run enabled service Ansible playbooks, optionally in dependency-safe parallel waves."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

REPO = Path(__file__).resolve().parents[1]
SETTINGS_SPEC = importlib.util.spec_from_file_location("settings", REPO / "scripts" / "settings.py")
if SETTINGS_SPEC is None or SETTINGS_SPEC.loader is None:
    raise RuntimeError("cannot load scripts/settings.py")
settings = importlib.util.module_from_spec(SETTINGS_SPEC)
SETTINGS_SPEC.loader.exec_module(settings)
DEFAULT_INVENTORY = (
    "values/ansible/inventory/local.yml",
    "infra/ansible/inventory/tfvars.py",
)
RunCommand = Callable[[list[str], Path, dict[str, str]], int]


@dataclass(frozen=True)
class ServiceResult:
    service: str
    playbooks: tuple[str, ...]
    returncode: int
    log_path: Path


def enabled_services(settings_path: Path | None = None) -> list[str]:
    return settings.load_settings(settings_path)["services"]


def dependency_waves(services: Iterable[str]) -> list[list[str]]:
    pending = list(services)
    enabled = set(pending)
    completed: set[str] = set()
    waves: list[list[str]] = []
    while pending:
        ready = [
            service
            for service in pending
            if set(settings.SERVICES[service]["dependencies"]) & enabled <= completed
        ]
        if not ready:
            unresolved = ", ".join(pending)
            raise settings.SettingsError(f"cannot resolve service dependency order: {unresolved}")
        resources: set[str] = set()
        wave = []
        for service in ready:
            resource = settings.SERVICES[service]["execution_resource"]
            if resource in resources:
                continue
            resources.add(resource)
            wave.append(service)
        waves.append(wave)
        completed.update(wave)
        pending = [service for service in pending if service not in wave]
    return waves


def selected_services(configured: list[str], requested: list[str] | None) -> list[str]:
    services = requested or configured
    unknown_services = sorted(set(services) - set(configured))
    if unknown_services:
        raise settings.SettingsError(f"service is not enabled: {', '.join(unknown_services)}")
    if len(services) != len(set(services)):
        raise settings.SettingsError("service selections contain duplicates")
    return services


def inventory_args(inventories: Iterable[str]) -> list[str]:
    args: list[str] = []
    for inventory in inventories:
        args.extend(["-i", inventory])
    return args


def load_env_file(path: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("parse_env_script", REPO / "scripts" / "parse-env.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/parse-env.py")
    parse_env_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse_env_script)
    return parse_env_script.parse_env(path)


def refresh_env_from_file(env_file: Path, env: dict[str, str]) -> None:
    env.update(load_env_file(env_file))


def bootstrap_technitium_token(env_file: Path, log_path: Path, env: dict[str, str], runner: RunCommand) -> int:
    rc = runner(
        ["python", "scripts/bootstrap-technitium-api-token.py", "--env-file", str(env_file)],
        log_path,
        env,
    )
    if rc == 0:
        refresh_env_from_file(env_file, env)
    return rc


def default_runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(("$ " + " ".join(command) + "\n").encode("utf-8"))
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=False)
        log.write((f"\nexit_code={process.returncode}\n").encode("utf-8"))
        return process.returncode


def run_service(
    service: str,
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    runner: RunCommand = default_runner,
) -> ServiceResult:
    playbooks = tuple(settings.SERVICES[service]["playbooks"])
    log_path = log_dir / f"{service}.log"
    env = dict(base_env)
    for playbook in playbooks:
        if playbook == "infra/ansible/playbooks/technitium-dns.yml":
            rc = bootstrap_technitium_token(env_file, log_path, env, runner)
            if rc != 0:
                return ServiceResult(service, playbooks, rc, log_path)
        command = ["ansible-playbook", *inventory_args(inventories), playbook]
        rc = runner(command, log_path, env)
        if rc != 0:
            return ServiceResult(service, playbooks, rc, log_path)
    return ServiceResult(service, playbooks, 0, log_path)


def run_sequential(
    services: list[str],
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    runner: RunCommand = default_runner,
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    for service in services:
        print(f"==> ansible service {service}", flush=True)
        result = run_service(service, inventories, log_dir, env_file, base_env, runner)
        results.append(result)
        if result.returncode != 0:
            break
        print(f"<== ansible service {service} ok", flush=True)
    return results


def run_parallel(
    services: list[str],
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    max_workers: int,
    runner: RunCommand = default_runner,
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    for index, wave in enumerate(dependency_waves(services), 1):
        print(f"==> ansible wave {index}: {', '.join(wave)}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(wave))) as executor:
            future_map = {
                executor.submit(run_service, service, inventories, log_dir, env_file, base_env, runner): service
                for service in wave
            }
            wave_results: list[ServiceResult] = []
            for future in concurrent.futures.as_completed(future_map):
                result = future.result()
                wave_results.append(result)
                status = "ok" if result.returncode == 0 else f"failed rc={result.returncode}"
                print(f"<== ansible service {result.service} {status}", flush=True)
        wave_results.sort(key=lambda item: wave.index(item.service))
        results.extend(wave_results)
        if any(result.returncode != 0 for result in wave_results):
            break
    return results


def summarize_failures(results: list[ServiceResult]) -> int:
    failed = [result for result in results if result.returncode != 0]
    if not failed:
        return 0
    print("Ansible service configuration failed:", file=sys.stderr)
    for result in failed:
        print(f"  {result.service}: exit {result.returncode}; log {result.log_path}", file=sys.stderr)
    print("Enter incident mode: preserve healthy services and recover one failed service directly.", file=sys.stderr)
    for result in failed:
        print(
            f"  scripts/apply-service.sh {result.service}",
            file=sys.stderr,
        )
    print("Resume broad orchestration only after direct endpoint and state checks pass.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--inventory", action="append", default=None)
    parser.add_argument("--env-file", type=Path, default=Path("values/.env"))
    parser.add_argument("--service", action="append", default=None)
    parser.add_argument("--mode", choices=("parallel", "sequential"), default=os.environ.get("INFRA_APPLY_ANSIBLE_MODE", "sequential"))
    parser.add_argument("--max-workers", type=int, default=int(os.environ.get("INFRA_APPLY_ANSIBLE_MAX_WORKERS", "4")))
    parser.add_argument("--log-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    configured_services = enabled_services(args.settings)
    try:
        services = selected_services(configured_services, args.service)
    except settings.SettingsError as error:
        parser.error(str(error))
    inventories = tuple(args.inventory or DEFAULT_INVENTORY)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_dir = args.log_dir or Path(".tmp") / f"apply-ansible-{timestamp.replace(':', '')}"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ansible service apply mode: {args.mode}; started {timestamp}; logs: {log_dir}", flush=True)
    base_env = dict(os.environ)

    if args.mode == "sequential":
        results = run_sequential(services, inventories, log_dir, args.env_file, base_env)
    else:
        results = run_parallel(services, inventories, log_dir, args.env_file, base_env, max(1, args.max_workers))
    return summarize_failures(results)


if __name__ == "__main__":
    raise SystemExit(main())

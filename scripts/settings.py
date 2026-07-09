#!/usr/bin/env python3
"""Read local operator settings for setup and service selection."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = Path("settings.local.json")
REPO = Path(__file__).resolve().parents[1]
SERVICE_REGISTRY = REPO / "infra" / "services.json"


def load_service_registry(path: Path = SERVICE_REGISTRY) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(registry, dict):
        raise ValueError(f"{path} must contain a JSON object")
    services = registry.get("services")
    defaults = registry.get("default_services")
    if not isinstance(services, dict):
        raise ValueError(f"{path}: services must be an object")
    if not isinstance(defaults, list) or not all(isinstance(item, str) for item in defaults):
        raise ValueError(f"{path}: default_services must be a list of strings")
    return registry


SERVICE_REGISTRY_DATA = load_service_registry()
DEFAULT_SERVICES = tuple(SERVICE_REGISTRY_DATA["default_services"])
SERVICES = {
    name: {
        "playbooks": tuple(config["playbooks"]),
        "dependencies": tuple(config["dependencies"]),
    }
    for name, config in SERVICE_REGISTRY_DATA["services"].items()
}
SERVICE_PLAYBOOKS = {name: config["playbooks"] for name, config in SERVICES.items()}
SERVICE_NAMES = set(SERVICES)


class SettingsError(ValueError):
    pass


def settings_path() -> Path:
    return Path(os.environ.get("INFRA_SETTINGS_FILE", DEFAULT_SETTINGS))


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SettingsError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise SettingsError(f"{path} must contain a JSON object")
    return data


def normalize_services(value: Any, path: Path) -> list[str]:
    if value is None:
        services = list(DEFAULT_SERVICES)
    else:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise SettingsError(f"{path}: services must be a list of strings")
        services = value
    unknown = sorted(set(services) - SERVICE_NAMES)
    if unknown:
        raise SettingsError(f"{path}: unknown services: {', '.join(unknown)}")
    if len(services) != len(set(services)):
        raise SettingsError(f"{path}: services contains duplicates")
    missing_dependencies = {
        service: sorted(set(SERVICES[service]["dependencies"]) - set(services))
        for service in services
        if set(SERVICES[service]["dependencies"]) - set(services)
    }
    if missing_dependencies:
        details = ", ".join(
            f"{service} requires {', '.join(dependencies)}"
            for service, dependencies in sorted(missing_dependencies.items())
        )
        raise SettingsError(f"{path}: {details}")
    return services


def ansible_playbooks(services: list[str]) -> list[str]:
    return [
        playbook
        for service in services
        for playbook in SERVICES[service]["playbooks"]
    ]


def all_ansible_playbooks() -> list[str]:
    playbooks: list[str] = []
    for service in SERVICES:
        for playbook in SERVICES[service]["playbooks"]:
            if playbook not in playbooks:
                playbooks.append(playbook)
    return playbooks


def settings_summary(settings: dict[str, Any]) -> str:
    path = settings["path"]
    status = str(path) if Path(path).exists() else f"{path} missing; using defaults"
    services = settings["services"]
    service_text = ", ".join(services) if services else "none"
    lines = [f"Settings file: {status}", f"Enabled services: {service_text}"]
    playbooks = ansible_playbooks(services)
    if playbooks:
        lines.append("Ansible playbooks:")
        lines.extend(f"  {playbook}" for playbook in playbooks)
    else:
        lines.append("Ansible playbooks: none")
    return "\n".join(lines)


def load_settings(path: Path | None = None) -> dict[str, Any]:
    resolved_path = path or settings_path()
    raw = load_raw(resolved_path)
    unknown = sorted(set(raw) - {"values_repo", "services"})
    if unknown:
        raise SettingsError(f"{resolved_path}: unknown top-level keys: {', '.join(unknown)}")

    values_repo = raw.get("values_repo", {})
    if values_repo is None:
        values_repo = {}
    if not isinstance(values_repo, dict):
        raise SettingsError(f"{resolved_path}: values_repo must be an object")
    unknown_values_keys = sorted(set(values_repo) - {"remote"})
    if unknown_values_keys:
        raise SettingsError(
            f"{resolved_path}: unknown values_repo keys: {', '.join(unknown_values_keys)}"
        )
    remote = values_repo.get("remote", "")
    if remote is None:
        remote = ""
    if not isinstance(remote, str):
        raise SettingsError(f"{resolved_path}: values_repo.remote must be a string")

    return {
        "path": resolved_path,
        "values_repo": {"remote": remote},
        "services": normalize_services(raw.get("services"), resolved_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("values-remote")
    subparsers.add_parser("services")
    ansible_playbooks_parser = subparsers.add_parser("ansible-playbooks")
    ansible_playbooks_parser.add_argument("--all", action="store_true")
    ansible_playbooks_parser.add_argument("--settings", type=Path, default=None)
    subparsers.add_parser("summary")
    subparsers.add_parser("tofu-var")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(args.settings)
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 1

    if args.command == "validate":
        print(f"settings valid: {settings['path']}")
    elif args.command == "values-remote":
        print(settings["values_repo"]["remote"])
    elif args.command == "services":
        print(" ".join(settings["services"]))
    elif args.command == "ansible-playbooks":
        playbooks = all_ansible_playbooks() if args.all else ansible_playbooks(settings["services"])
        for playbook in playbooks:
            print(playbook)
    elif args.command == "summary":
        print(settings_summary(settings))
    elif args.command == "tofu-var":
        print(json.dumps(settings["services"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

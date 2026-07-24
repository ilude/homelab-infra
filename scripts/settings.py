#!/usr/bin/env python3
"""Read local operator settings for setup and service selection."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from values_context import ValuesContextError, from_environment, load_metadata
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from values_context import ValuesContextError, from_environment, load_metadata

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
        "terraform_addresses": tuple(config.get("terraform_addresses", ())),
        "terraform_replace_addresses": {
            runtime: tuple(addresses)
            for runtime, addresses in config.get("terraform_replace_addresses", {}).items()
            if isinstance(runtime, str) and isinstance(addresses, list)
        },
    }
    for name, config in SERVICE_REGISTRY_DATA["services"].items()
}
SERVICE_PLAYBOOKS = {name: config["playbooks"] for name, config in SERVICES.items()}
SERVICE_NAMES = set(SERVICES)


class SettingsError(ValueError):
    pass


def settings_path() -> Path:
    explicit = os.environ.get("INFRA_SETTINGS_FILE")
    if explicit:
        return Path(explicit)
    context = from_environment()
    return context.metadata_path or DEFAULT_SETTINGS


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


def tofu_targets(service: str, enabled_services: list[str]) -> list[str]:
    if service not in SERVICE_NAMES:
        raise SettingsError(f"unknown service: {service}")
    if service not in enabled_services:
        raise SettingsError(f"service is not enabled: {service}")
    targets: list[str] = []
    for address in SERVICES[service]["terraform_addresses"]:
        if not isinstance(address, str) or not address:
            continue
        target = address[:-1] if address.endswith("[") else address
        if target not in targets:
            targets.append(target)
    if not targets:
        raise SettingsError(f"service has no OpenTofu targets: {service}")
    return targets


def tofu_replace_targets(service: str, enabled_services: list[str], runtime_type: str) -> list[str]:
    if service not in SERVICE_NAMES:
        raise SettingsError(f"unknown service: {service}")
    if service not in enabled_services:
        raise SettingsError(f"service is not enabled: {service}")
    if runtime_type not in {"lxc", "vm"}:
        raise SettingsError(f"unsupported service runtime: {runtime_type}")
    targets = [target for target in SERVICES[service]["terraform_replace_addresses"].get(runtime_type, ()) if target]
    if not targets:
        raise SettingsError(f"service has no OpenTofu replacement targets: {service}")
    return list(dict.fromkeys(targets))


def all_ansible_playbooks() -> list[str]:
    playbooks: list[str] = []
    for service in SERVICES:
        for playbook in SERVICES[service]["playbooks"]:
            if playbook not in playbooks:
                playbooks.append(playbook)
    return playbooks


def validate_site_metadata(metadata: dict[str, Any], site: str, path: Path) -> None:
    if metadata.get("name", site) != site:
        raise SettingsError(f"{path}: site metadata name does not match selected site")
    site_class = metadata.get("class", "")
    lifecycle = metadata.get("lifecycle", "")
    if site_class not in {"development", "staging", "production", "location", "purpose"}:
        raise SettingsError(f"{path}: unsupported site class")
    if lifecycle not in {"disposable", "persistent"}:
        raise SettingsError(f"{path}: lifecycle must be disposable or persistent")
    for key in ("allow_apply", "allow_destroy"):
        if not isinstance(metadata.get(key), bool):
            raise SettingsError(f"{path}: {key} must be a boolean")
    if site == "dev" and (site_class != "development" or lifecycle != "disposable"):
        raise SettingsError(f"{path}: the dev site must be disposable development")


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
    try:
        context = from_environment()
    except ValuesContextError as error:
        raise SettingsError(str(error)) from error

    resolved_path = path or settings_path()
    raw = load_raw(resolved_path)
    root_raw = load_raw(DEFAULT_SETTINGS) if context.site is not None and resolved_path != DEFAULT_SETTINGS else raw
    site_raw = raw if context.site is not None and resolved_path != DEFAULT_SETTINGS else {}
    unknown = sorted(set(root_raw) - {"values_repo", "services"})
    if unknown:
        raise SettingsError(f"{DEFAULT_SETTINGS}: unknown top-level keys: {', '.join(unknown)}")
    site_unknown = sorted(
        set(site_raw) - {"name", "class", "lifecycle", "allow_apply", "allow_destroy", "services"}
    )
    if site_unknown:
        raise SettingsError(f"{resolved_path}: unknown site keys: {', '.join(site_unknown)}")

    values_repo = root_raw.get("values_repo", {})
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

    try:
        metadata = load_metadata(context)
    except ValuesContextError as error:
        raise SettingsError(str(error)) from error
    if context.site is not None:
        validate_site_metadata(metadata, context.site, resolved_path)
    services_raw = site_raw.get("services") if context.site is not None else raw.get("services")
    if context.site is not None and services_raw is None:
        raise SettingsError(f"{resolved_path}: site services are required")
    return {
        "path": resolved_path,
        "site": context.site,
        "site_metadata": metadata,
        "values_repo": {"remote": remote},
        "services": normalize_services(services_raw, resolved_path),
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
    tofu_target_parser = subparsers.add_parser("tofu-targets")
    tofu_target_parser.add_argument("service")
    tofu_replace_parser = subparsers.add_parser("tofu-replace-targets")
    tofu_replace_parser.add_argument("service")
    tofu_replace_parser.add_argument("--runtime", required=True, choices=("lxc", "vm"))
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
    elif args.command == "tofu-targets":
        for target in tofu_targets(args.service, settings["services"]):
            print(target)
    elif args.command == "tofu-replace-targets":
        for target in tofu_replace_targets(args.service, settings["services"], args.runtime):
            print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

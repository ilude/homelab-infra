#!/usr/bin/env python3
"""Read local operator settings for setup and service selection."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_SETTINGS = Path("settings.local.json")
REPO = Path(__file__).resolve().parents[1]
SERVICE_REGISTRY = REPO / "infra" / "services.json"
SUPPORTED_RUNTIME_PROFILES = frozenset(
    {"config", "seaweedfs", "onclave", "freellmapi", "web_fetch"}
)


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
    if not isinstance(defaults, list) or not all(
        isinstance(item, str) for item in defaults
    ):
        raise ValueError(f"{path}: default_services must be a list of strings")
    if len(defaults) != len(set(defaults)):
        raise ValueError(f"{path}: default_services contains duplicates")

    service_names = set(services)
    unknown_defaults = sorted(set(defaults) - service_names)
    if unknown_defaults:
        raise ValueError(
            f"{path}: default_services contains unknown services: {', '.join(unknown_defaults)}"
        )

    playbook_owners: dict[str, str] = {}
    dependencies: dict[str, tuple[str, ...]] = {}
    for name, config in services.items():
        if not isinstance(config, dict):
            raise ValueError(f"{path}: service {name} must be an object")
        if "runtime_profile" not in config:
            raise ValueError(f"{path}: service {name} must declare runtime_profile")
        runtime_profile = config["runtime_profile"]
        if not isinstance(runtime_profile, str) or not runtime_profile.strip():
            raise ValueError(
                f"{path}: service {name} runtime_profile must be a non-empty string"
            )
        if runtime_profile not in SUPPORTED_RUNTIME_PROFILES:
            supported = ", ".join(sorted(SUPPORTED_RUNTIME_PROFILES))
            raise ValueError(
                f"{path}: service {name} has unsupported runtime_profile "
                f"{runtime_profile!r}; supported profiles: {supported}"
            )
        playbooks = config.get("playbooks")
        if not isinstance(playbooks, list) or not all(
            isinstance(playbook, str) and playbook for playbook in playbooks
        ):
            raise ValueError(
                f"{path}: service {name} playbooks must be a list of non-empty strings"
            )
        for playbook in playbooks:
            owner = playbook_owners.get(playbook)
            if owner is not None:
                raise ValueError(
                    f"{path}: duplicate playbook {playbook} for {owner} and {name}"
                )
            playbook_owners[playbook] = name

        service_dependencies = config.get("dependencies")
        if not isinstance(service_dependencies, list) or not all(
            isinstance(dependency, str) for dependency in service_dependencies
        ):
            raise ValueError(
                f"{path}: service {name} dependencies must be a list of strings"
            )
        unknown_dependencies = sorted(set(service_dependencies) - service_names)
        if unknown_dependencies:
            dependencies_text = ", ".join(unknown_dependencies)
            raise ValueError(
                f"{path}: service {name} has unknown dependencies: {dependencies_text}"
            )
        if name in service_dependencies:
            raise ValueError(f"{path}: service {name} cannot depend on itself")
        dependencies[name] = tuple(service_dependencies)

        if "execution_resource" in config and (
            not isinstance(config["execution_resource"], str)
            or not config["execution_resource"].strip()
        ):
            raise ValueError(
                f"{path}: service {name} execution_resource must be a non-empty string"
            )
        if "terraform_module" in config and (
            not isinstance(config["terraform_module"], str)
            or not config["terraform_module"].strip()
        ):
            raise ValueError(
                f"{path}: service {name} terraform_module must be a non-empty string"
            )
        if "terraform_target" in config and (
            not isinstance(config["terraform_target"], str)
            or not config["terraform_target"].strip()
        ):
            raise ValueError(
                f"{path}: service {name} terraform_target must be a non-empty string"
            )
        if "terraform_module" in config and "terraform_target" in config:
            raise ValueError(
                f"{path}: service {name} cannot declare both terraform_module and terraform_target"
            )

        if "conflicts" in config:
            conflicts = config["conflicts"]
            if not isinstance(conflicts, list) or not all(
                isinstance(conflict, str) for conflict in conflicts
            ):
                raise ValueError(
                    f"{path}: service {name} conflicts must be a list of strings"
                )
            unknown_conflicts = sorted(set(conflicts) - service_names)
            if unknown_conflicts:
                raise ValueError(
                    f"{path}: service {name} has unknown conflicts: {', '.join(unknown_conflicts)}"
                )
            if name in conflicts:
                raise ValueError(f"{path}: service {name} cannot conflict with itself")

    for name, config in services.items():
        for conflict in config.get("conflicts", []):
            if name not in services[conflict].get("conflicts", []):
                raise ValueError(
                    f"{path}: conflict between {name} and {conflict} must be reciprocal"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise ValueError(f"{path}: cyclic service dependencies include {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in services:
        visit(name)
    return registry


SERVICE_REGISTRY_DATA = load_service_registry()
DEFAULT_SERVICES = tuple(SERVICE_REGISTRY_DATA["default_services"])
SERVICES = {
    name: {
        "playbooks": tuple(config["playbooks"]),
        "dependencies": tuple(config["dependencies"]),
        "conflicts": tuple(config.get("conflicts", [])),
        "execution_resource": str(config.get("execution_resource", name)),
        "terraform_module": config.get("terraform_module"),
        "terraform_target": config.get("terraform_target"),
    }
    for name, config in SERVICE_REGISTRY_DATA["services"].items()
}
SERVICE_PLAYBOOKS = {name: config["playbooks"] for name, config in SERVICES.items()}
SERVICE_NAMES = set(SERVICES)


class SettingsError(ValueError):
    pass


def runtime_profile(service: str) -> str:
    try:
        return str(SERVICE_REGISTRY_DATA["services"][service]["runtime_profile"])
    except KeyError as error:
        raise SettingsError(f"unknown service: {service}") from error


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
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise SettingsError(f"{path}: services must be a list of strings")
        services = value
    unknown = sorted(set(services) - SERVICE_NAMES)
    if unknown:
        raise SettingsError(f"{path}: unknown services: {', '.join(unknown)}")
    if len(services) != len(set(services)):
        raise SettingsError(f"{path}: services contains duplicates")
    selected_services = set(services)
    conflicts = {
        service: sorted(selected_services & set(SERVICES[service]["conflicts"]))
        for service in services
        if selected_services & set(SERVICES[service]["conflicts"])
    }
    if conflicts:
        details = ", ".join(
            f"{service} conflicts with {', '.join(conflicting_services)}"
            for service, conflicting_services in sorted(conflicts.items())
        )
        raise SettingsError(f"{path}: {details}")
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
        playbook for service in services for playbook in SERVICES[service]["playbooks"]
    ]


def tofu_target(settings: dict[str, Any], service: str) -> str:
    if service not in settings["services"]:
        raise SettingsError(f"Service is not enabled: {service}")
    terraform_target = SERVICES[service]["terraform_target"]
    if terraform_target:
        return str(terraform_target)
    terraform_module = SERVICES[service]["terraform_module"]
    if not terraform_module:
        raise SettingsError(f"Service has no OpenTofu target: {service}")
    return f"module.{terraform_module}"


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


def enable_service(path: Path, service: str) -> bool:
    if service not in SERVICE_NAMES:
        raise SettingsError(f"unknown service: {service}")
    raw = load_raw(path)
    services = normalize_services(raw.get("services"), path)
    if service in services:
        return False
    services.append(service)
    normalize_services(services, path)
    raw["services"] = services
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return True


def load_settings(path: Path | None = None) -> dict[str, Any]:
    resolved_path = path or settings_path()
    raw = load_raw(resolved_path)
    unknown = sorted(set(raw) - {"bws", "values_repo", "services"})
    if unknown:
        raise SettingsError(
            f"{resolved_path}: unknown top-level keys: {', '.join(unknown)}"
        )

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

    bws = raw.get("bws", {})
    if bws is None:
        bws = {}
    if not isinstance(bws, dict):
        raise SettingsError(f"{resolved_path}: bws must be an object")
    unknown_bws_keys = sorted(set(bws) - {"project_id", "api_server"})
    if unknown_bws_keys:
        raise SettingsError(
            f"{resolved_path}: unknown bws keys: {', '.join(unknown_bws_keys)}"
        )
    project_id = bws.get("project_id", "")
    api_server = bws.get("api_server", "")
    if bws:
        if not isinstance(project_id, str) or not project_id.strip():
            raise SettingsError(f"{resolved_path}: bws.project_id must be a string")
        if not isinstance(api_server, str):
            raise SettingsError(f"{resolved_path}: bws.api_server must be a string")
        parsed_server = urlparse(api_server)
        if parsed_server.scheme not in {"http", "https"} or not parsed_server.netloc:
            raise SettingsError(f"{resolved_path}: bws.api_server must be an HTTP URL")

    return {
        "path": resolved_path,
        "bws": {"project_id": project_id, "api_server": api_server},
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
    enable_service_parser = subparsers.add_parser("enable-service")
    enable_service_parser.add_argument("service")
    ansible_playbooks_parser = subparsers.add_parser("ansible-playbooks")
    ansible_playbooks_parser.add_argument("--all", action="store_true")
    ansible_playbooks_parser.add_argument("--settings", type=Path, default=None)
    subparsers.add_parser("summary")
    subparsers.add_parser("tofu-var")
    tofu_target_parser = subparsers.add_parser("tofu-target")
    tofu_target_parser.add_argument("service")
    runtime_profile_parser = subparsers.add_parser("runtime-profile")
    runtime_profile_parser.add_argument("service")
    args = parser.parse_args(argv)

    if args.command == "runtime-profile":
        try:
            print(runtime_profile(args.service))
        except SettingsError as error:
            print(error, file=sys.stderr)
            return 1
        return 0

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
    elif args.command == "enable-service":
        enable_service(args.settings or settings_path(), args.service)
    elif args.command == "ansible-playbooks":
        playbooks = (
            all_ansible_playbooks()
            if args.all
            else ansible_playbooks(settings["services"])
        )
        for playbook in playbooks:
            print(playbook)
    elif args.command == "summary":
        print(settings_summary(settings))
    elif args.command == "tofu-var":
        tofu_services = [
            service
            for service in settings["services"]
            if SERVICE_REGISTRY_DATA["services"][service].get(
                "terraform_selection", True
            )
        ]
        print(json.dumps(tofu_services))
    elif args.command == "tofu-target":
        try:
            print(tofu_target(settings, args.service))
        except SettingsError as error:
            print(error, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

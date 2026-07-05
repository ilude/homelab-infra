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
DEFAULT_SERVICES = ("technitium", "forgejo")
SERVICE_PLAYBOOKS = {
    "technitium": (
        "infra/ansible/playbooks/technitium.yml",
        "infra/ansible/playbooks/caddy-proxy.yml",
    ),
    "forgejo": ("infra/ansible/playbooks/forgejo.yml",),
    "tailscale_client": (),
    "forgejo_runner": ("infra/ansible/playbooks/forgejo-runner.yml",),
}
SERVICE_NAMES = set(SERVICE_PLAYBOOKS)


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
    if "forgejo_runner" in services and "forgejo" not in services:
        raise SettingsError(f"{path}: forgejo_runner requires forgejo in services")
    return services


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
    subparsers.add_parser("ansible-playbooks")
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
        for service in settings["services"]:
            for playbook in SERVICE_PLAYBOOKS[service]:
                print(playbook)
    elif args.command == "tofu-var":
        print(json.dumps(settings["services"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

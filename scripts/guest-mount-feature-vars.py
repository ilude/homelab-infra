#!/usr/bin/env python3
"""Emit Ansible vars for LXC guest mount feature preflight checks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings
from values_context import from_environment

try:
    import hcl2
except ImportError as error:  # pragma: no cover - exercised in tooling container
    print(f"missing python-hcl2 dependency: {error}", file=sys.stderr)
    raise SystemExit(1) from error

DEFAULT_TFVARS = from_environment().path("terraform.tfvars")
REQUIRED_FEATURES = {"guest_nfs": "nfs", "guest_cifs": "cifs"}
SERVICE_HOSTS = settings.SERVICE_REGISTRY_DATA["services"]


class GuestMountFeatureError(ValueError):
    pass


def load_tfvars(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = hcl2.load(file)
    except OSError as error:
        raise GuestMountFeatureError(f"cannot read {path}: {error}") from error
    except Exception as error:
        raise GuestMountFeatureError(f"cannot parse {path}: {error}") from error
    if not isinstance(data, dict):
        raise GuestMountFeatureError(f"{path} must contain an object")
    return data


def build_feature_checks(enabled_services: list[str], tfvars: dict[str, Any]) -> list[dict[str, Any]]:
    storage = tfvars.get("service_storage", {})
    if not isinstance(storage, dict):
        return []

    checks: list[dict[str, Any]] = []
    for service in enabled_services:
        config = SERVICE_HOSTS.get(service, {}).get("inventory", {})
        vmid_key = config.get("tf_vmid")
        vmid = tfvars.get(vmid_key) if vmid_key else None
        runtimes = tfvars.get("service_runtime", {})
        runtime = runtimes.get(service, {}) if isinstance(runtimes, dict) else {}
        if not isinstance(runtime, dict) or not runtime:
            runtime = tfvars.get(f"{service}_runtime", {})
        runtime_type = runtime.get("type", "lxc") if isinstance(runtime, dict) else "lxc"
        if runtime_type != "lxc":
            continue
        service_storage = storage.get(service, {})
        if not isinstance(service_storage, dict):
            continue
        for mount_name, definition in service_storage.items():
            if not isinstance(definition, dict):
                continue
            feature = REQUIRED_FEATURES.get(definition.get("type"))
            if not feature:
                continue
            if vmid is None:
                raise GuestMountFeatureError(f"missing VMID for {service}.{mount_name} guest mount feature check")
            checks.append(
                {
                    "service": service,
                    "mount": mount_name,
                    "vmid": vmid,
                    "feature": feature,
                    "storage_type": definition.get("type"),
                }
            )
    return checks


def format_summary(checks: list[dict[str, Any]]) -> str:
    lines = ["Guest mount feature preflight summary:"]
    if not checks:
        lines.append("  none")
        return "\n".join(lines)
    for check in checks:
        lines.append(
            "  {service}.{mount}: vmid={vmid} requires LXC feature mount={feature} ({storage_type})".format(
                **check
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tfvars", type=Path, default=DEFAULT_TFVARS)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        loaded_settings = settings.load_settings(args.settings)
        checks = build_feature_checks(loaded_settings["services"], load_tfvars(args.tfvars))
    except (settings.SettingsError, GuestMountFeatureError) as error:
        print(f"guest mount feature vars failed: {error}", file=sys.stderr)
        return 1

    if args.summary:
        print(format_summary(checks))
    else:
        print(json.dumps({"guest_mount_feature_checks": checks}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

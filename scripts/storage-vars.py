#!/usr/bin/env python3
"""Emit Ansible vars for host storage that must exist before OpenTofu apply."""
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
LEGACY_FORGEJO_STORAGE_KEYS = {
    "dataset": "forgejo_data_dataset",
    "mountpoint": "forgejo_data_host_path",
    "uid": "forgejo_data_host_uid",
    "gid": "forgejo_data_host_gid",
}


class StorageVarsError(ValueError):
    pass


def load_tfvars(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = hcl2.load(file)
    except OSError as error:
        raise StorageVarsError(f"cannot read {path}: {error}") from error
    except Exception as error:
        raise StorageVarsError(f"cannot parse {path}: {error}") from error
    if not isinstance(data, dict):
        raise StorageVarsError(f"{path} must contain an object")
    return data


def legacy_forgejo_storage(tfvars: dict[str, Any]) -> dict[str, Any] | None:
    host_path = tfvars.get(LEGACY_FORGEJO_STORAGE_KEYS["mountpoint"])
    if not host_path:
        return None
    return {
        "type": "bind",
        "source": host_path,
        "target": tfvars.get("forgejo_data_mount_path", "/var/lib/forgejo"),
        "create_source": True,
        "host_uid": tfvars.get(LEGACY_FORGEJO_STORAGE_KEYS["uid"], 100000),
        "host_gid": tfvars.get(LEGACY_FORGEJO_STORAGE_KEYS["gid"], 100000),
        "mode": "0750",
        "host_prepare": {
            "type": "zfs_dataset",
            "dataset": tfvars.get(LEGACY_FORGEJO_STORAGE_KEYS["dataset"], ""),
            "mountpoint": host_path,
        },
    }


def storage_definitions(tfvars: dict[str, Any], service: str) -> dict[str, dict[str, Any]]:
    storage = tfvars.get("service_storage", {})
    if isinstance(storage, dict) and isinstance(storage.get(service), dict):
        return {
            mount_name: definition
            for mount_name, definition in storage[service].items()
            if isinstance(definition, dict)
        }
    legacy = legacy_forgejo_storage(tfvars) if service == "forgejo" else None
    return {"data": legacy} if legacy else {}


def build_storage_mounts(enabled_services: list[str], tfvars: dict[str, Any]) -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    for service in enabled_services:
        for mount_name, definition in storage_definitions(tfvars, service).items():
            if definition.get("type") != "bind":
                continue
            source = definition.get("source")
            if not source:
                raise StorageVarsError(f"missing bind source for {service}.{mount_name}")
            host_prepare = definition.get("host_prepare")
            if not isinstance(host_prepare, dict):
                host_prepare = {"type": "directory" if definition.get("create_source", True) else "none"}
            if host_prepare.get("type", "directory") == "none":
                continue
            mounts.append(
                {
                    "name": service,
                    "mount": mount_name,
                    "source": source,
                    "target": definition.get("target", ""),
                    "uid": definition.get("host_uid", 100000),
                    "gid": definition.get("host_gid", 100000),
                    "mode": definition.get("mode", "0750"),
                    "host_prepare": host_prepare,
                }
            )
    return mounts


def format_storage_summary(mounts: list[dict[str, Any]]) -> str:
    lines = ["Storage prep summary:"]
    if not mounts:
        lines.append("  none")
        return "\n".join(lines)
    for mount in mounts:
        lines.append(
            "  {name}.{mount}: {prepare} source={source} target={target} uid={uid} gid={gid} mode={mode}".format(
                name=mount["name"],
                mount=mount["mount"],
                prepare=mount["host_prepare"].get("type", "directory"),
                source=mount["source"],
                target=mount["target"],
                uid=mount["uid"],
                gid=mount["gid"],
                mode=mount["mode"],
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tfvars", type=Path, default=DEFAULT_TFVARS)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--service", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        loaded_settings = settings.load_settings(args.settings)
        enabled_services = loaded_settings["services"]
        if args.service:
            if args.service not in enabled_services:
                raise StorageVarsError(f"service is not enabled: {args.service}")
            enabled_services = [args.service]
        tfvars = load_tfvars(args.tfvars)
        mounts = build_storage_mounts(enabled_services, tfvars)
        payload = {"storage_bind_mounts": mounts}
    except (settings.SettingsError, StorageVarsError, OSError) as error:
        print(f"storage vars failed: {error}", file=sys.stderr)
        return 1
    if args.summary:
        print(format_storage_summary(mounts))
    else:
        print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

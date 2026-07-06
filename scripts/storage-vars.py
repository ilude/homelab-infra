#!/usr/bin/env python3
"""Emit Ansible vars for host storage that must exist before OpenTofu apply."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings

try:
    import hcl2
except ImportError as error:  # pragma: no cover - exercised in tooling container
    print(f"missing python-hcl2 dependency: {error}", file=sys.stderr)
    raise SystemExit(1) from error

DEFAULT_TFVARS = Path("values/terraform.tfvars")

STORAGE_SERVICES = {
    "forgejo": {
        "dataset": "forgejo_data_dataset",
        "mountpoint": "forgejo_data_host_path",
        "uid": "forgejo_data_host_uid",
        "gid": "forgejo_data_host_gid",
    },
}


class StorageVarsError(ValueError):
    pass


def load_tfvars(path: Path) -> dict[str, str | int]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = hcl2.load(file)
    except OSError as error:
        raise StorageVarsError(f"cannot read {path}: {error}") from error
    except Exception as error:
        raise StorageVarsError(f"cannot parse {path}: {error}") from error
    if not isinstance(data, dict):
        raise StorageVarsError(f"{path} must contain an object")
    return {
        key: value
        for key, value in data.items()
        if any(key == field for fields in STORAGE_SERVICES.values() for field in fields.values())
    }


def build_storage_datasets(enabled_services: list[str], tfvars: dict[str, str | int]) -> list[dict[str, str | int]]:
    datasets: list[dict[str, str | int]] = []
    for service in enabled_services:
        fields = STORAGE_SERVICES.get(service)
        if not fields:
            continue
        required = [fields["dataset"], fields["mountpoint"]]
        missing = [name for name in required if name not in tfvars]
        if missing:
            raise StorageVarsError(f"missing storage tfvars for {service}: {', '.join(missing)}")
        datasets.append(
            {
                "name": service,
                "dataset": tfvars[fields["dataset"]],
                "mountpoint": tfvars[fields["mountpoint"]],
                "uid": tfvars.get(fields["uid"], 100000),
                "gid": tfvars.get(fields["gid"], 100000),
            }
        )
    return datasets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tfvars", type=Path, default=DEFAULT_TFVARS)
    parser.add_argument("--settings", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        loaded_settings = settings.load_settings(args.settings)
        tfvars = load_tfvars(args.tfvars)
        payload = {"storage_datasets": build_storage_datasets(loaded_settings["services"], tfvars)}
    except (settings.SettingsError, StorageVarsError, OSError) as error:
        print(f"storage vars failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

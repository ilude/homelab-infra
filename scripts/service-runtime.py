#!/usr/bin/env python3
"""Print the configured runtime type for an enabled service."""
from __future__ import annotations

import argparse
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


class ServiceRuntimeError(ValueError):
    pass


def load_tfvars(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data = hcl2.load(file)
    except OSError as error:
        raise ServiceRuntimeError(f"cannot read {path}: {error}") from error
    except Exception as error:
        raise ServiceRuntimeError(f"cannot parse {path}: {error}") from error
    if not isinstance(data, dict):
        raise ServiceRuntimeError(f"{path} must contain an object")
    return data


def runtime_type(service: str, tfvars: dict[str, Any]) -> str:
    runtimes = tfvars.get("service_runtime", {})
    runtime = runtimes.get(service) if isinstance(runtimes, dict) else None
    if not isinstance(runtime, dict):
        runtime = tfvars.get(f"{service}_runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    default = "vm" if service == "onramp_host" else "lxc"
    selected = runtime.get("type", default)
    if selected not in {"lxc", "vm"}:
        raise ServiceRuntimeError(f"unsupported runtime for {service}: {selected}")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service")
    parser.add_argument("--tfvars", type=Path, default=DEFAULT_TFVARS)
    parser.add_argument("--settings", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        enabled = settings.load_settings(args.settings)["services"]
        if args.service not in enabled:
            raise ServiceRuntimeError(f"service is not enabled: {args.service}")
        print(runtime_type(args.service, load_tfvars(args.tfvars)))
    except (settings.SettingsError, ServiceRuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Ansible dynamic inventory derived from OpenTofu tfvars."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import settings

try:
    import hcl2
except ImportError as error:  # pragma: no cover - exercised in tooling container
    print(f"missing python-hcl2 dependency: {error}", file=sys.stderr)
    raise SystemExit(1) from error

REPO = Path(__file__).resolve().parents[3]
DEFAULT_TFVARS = REPO / "values" / "terraform.tfvars"
DEFAULT_ANSIBLE_USER = "root"

SERVICE_HOSTS = {
    name: dict(config["inventory"])
    for name, config in settings.SERVICE_REGISTRY_DATA["services"].items()
}


class InventoryError(ValueError):
    pass


def load_tfvars(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = hcl2.load(file)
    except OSError as error:
        raise InventoryError(f"cannot read {path}: {error}") from error
    except Exception as error:
        raise InventoryError(f"cannot parse {path}: {error}") from error
    if not isinstance(data, dict):
        raise InventoryError(f"{path} must contain an object")
    return data


def host_address(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text == "dhcp":
        return ""
    return text.split("/", 1)[0]


def enabled_services(settings_path: Path | None) -> list[str]:
    loaded = settings.load_settings(settings_path)
    return loaded["services"]


def service_play_vars(service: str, tfvars: dict[str, Any]) -> dict[str, Any]:
    config = SERVICE_HOSTS.get(service)
    if config is None:
        return {}
    vars_for_play: dict[str, Any] = {}
    vmid = tfvars.get(config["tf_vmid"])
    if vmid is not None:
        vars_for_play[config["vmid_var"]] = vmid
    domain_var = config.get("domain_var")
    tf_domain = config.get("tf_domain")
    if domain_var and tf_domain and tfvars.get(tf_domain):
        vars_for_play[domain_var] = tfvars[tf_domain]
    user_var = config.get("user_var")
    tf_user = config.get("tf_user")
    if user_var and tf_user and tfvars.get(tf_user):
        vars_for_play[user_var] = tfvars[tf_user]
    for var_name, tf_key in config.get("extra_play_vars", {}).items():
        if tf_key in tfvars:
            vars_for_play[var_name] = tfvars[tf_key]
    return vars_for_play


def service_hostvars(service: str, tfvars: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    config = SERVICE_HOSTS.get(service)
    if config is None:
        return None
    host = config["host"]
    group = config["group"]
    hostvars: dict[str, Any] = {"ansible_user": DEFAULT_ANSIBLE_USER}
    tf_user = config.get("tf_user")
    if tf_user and tfvars.get(tf_user):
        hostvars["ansible_user"] = str(tfvars[tf_user])
        hostvars["ansible_become"] = True

    address = host_address(tfvars.get(config["tf_host"]))
    if address:
        hostvars["ansible_host"] = address

    hostvars.update(service_play_vars(service, tfvars))

    return host, group, hostvars


def build_inventory(tfvars: dict[str, Any], services: list[str]) -> dict[str, Any]:
    inventory: dict[str, Any] = {
        "_meta": {"hostvars": {}},
        "all": {"vars": {}},
        "services": {"children": []},
    }
    hostvars = inventory["_meta"]["hostvars"]
    for service in services:
        inventory["all"]["vars"].update(service_play_vars(service, tfvars))
        rendered = service_hostvars(service, tfvars)
        if rendered is None:
            continue
        host, group, vars_for_host = rendered
        inventory[group] = {"hosts": [host]}
        if group not in inventory["services"]["children"]:
            inventory["services"]["children"].append(group)
        hostvars[host] = vars_for_host
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--host", default=None)
    parser.add_argument("--tfvars", type=Path, default=Path(os.environ.get("ANSIBLE_TFVARS_FILE", DEFAULT_TFVARS)))
    parser.add_argument("--settings", type=Path, default=None)
    args = parser.parse_args(argv)

    settings_path = args.settings or (Path(os.environ["INFRA_SETTINGS_FILE"]) if "INFRA_SETTINGS_FILE" in os.environ else None)
    try:
        inventory = build_inventory(load_tfvars(args.tfvars), enabled_services(settings_path))
    except (InventoryError, settings.SettingsError) as error:
        print(error, file=sys.stderr)
        return 1

    if args.host:
        print(json.dumps(inventory.get("_meta", {}).get("hostvars", {}).get(args.host, {})))
    else:
        print(json.dumps(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

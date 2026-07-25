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
from values_context import ValuesContextError, from_environment

try:
    import hcl2
except ImportError as error:  # pragma: no cover - exercised in tooling container
    print(f"missing python-hcl2 dependency: {error}", file=sys.stderr)
    raise SystemExit(1) from error

REPO = Path(__file__).resolve().parents[3]
try:
    DEFAULT_TFVARS = from_environment(REPO).path("terraform.tfvars")
except ValuesContextError as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(1) from error
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
    add_env_tfvar_fallbacks(data)
    return data


def env_list_var(name: str) -> list[str] | None:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        parsed = [raw_value]
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise InventoryError(f"{name} must be a JSON string list when used by dynamic inventory")
    return parsed


def add_env_tfvar_fallbacks(tfvars: dict[str, Any]) -> None:
    if not tfvars.get("lxc_ssh_public_keys"):
        env_keys = env_list_var("TF_VAR_lxc_ssh_public_keys")
        if env_keys:
            tfvars["lxc_ssh_public_keys"] = env_keys


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


def service_runtime(service: str, tfvars: dict[str, Any]) -> dict[str, Any]:
    runtimes = tfvars.get("service_runtime", {})
    if isinstance(runtimes, dict) and isinstance(runtimes.get(service), dict):
        return runtimes[service]
    legacy_runtime = tfvars.get(f"{service}_runtime", {})
    if isinstance(legacy_runtime, dict):
        return legacy_runtime
    return {}


def service_play_vars(service: str, tfvars: dict[str, Any]) -> dict[str, Any]:
    config = SERVICE_HOSTS.get(service)
    if config is None:
        return {}
    vars_for_play: dict[str, Any] = {}
    storage = tfvars.get("service_storage", {})
    if isinstance(storage, dict) and isinstance(storage.get(service), dict):
        vars_for_play[f"{service}_storage"] = storage[service]
    runtime = service_runtime(service, tfvars)
    if runtime:
        vars_for_play[f"{service}_runtime"] = runtime
        vars_for_play["service_runtime_current"] = runtime
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
            value = tfvars[tf_key]
            if var_name == "onramp_host_ssh_public_keys" and not value:
                value = tfvars.get("lxc_ssh_public_keys", value)
            vars_for_play[var_name] = value
    return vars_for_play


def service_hostvars(service: str, tfvars: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    config = SERVICE_HOSTS.get(service)
    if config is None:
        return None
    host = config["host"]
    group = config["group"]
    hostvars: dict[str, Any] = {"ansible_user": DEFAULT_ANSIBLE_USER}
    tf_user = config.get("tf_user")
    user_runtime = config.get("tf_user_runtime")
    runtime = service_runtime(service, tfvars)
    runtime_type = runtime.get("type", "lxc") if isinstance(runtime, dict) else "lxc"
    if runtime_type == "vm" and isinstance(runtime, dict) and runtime.get("cloud_init_user"):
        hostvars["ansible_user"] = str(runtime["cloud_init_user"])
        hostvars["ansible_become"] = hostvars["ansible_user"] != DEFAULT_ANSIBLE_USER
    if tf_user and tfvars.get(tf_user) and (user_runtime is None or runtime_type == user_runtime):
        hostvars["ansible_user"] = str(tfvars[tf_user])
        hostvars["ansible_become"] = True

    address = host_address(tfvars.get(config["tf_host"]))
    if address:
        hostvars["ansible_host"] = address

    hostvars.update(service_play_vars(service, tfvars))

    return host, group, hostvars


def build_inventory(tfvars: dict[str, Any], services: list[str]) -> dict[str, Any]:
    context = from_environment(REPO)
    known_hosts = context.path("ansible/known_hosts")
    inventory: dict[str, Any] = {
        "_meta": {"hostvars": {}},
        "all": {
            "vars": {
                "ansible_ssh_common_args": f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes",
            }
        },
        "services": {"children": []},
    }
    hostvars = inventory["_meta"]["hostvars"]
    # Keep registry-known groups resolvable even when their service is disabled.
    # Selection remains governed by settings; no disabled host is added here.
    for group in sorted({str(config["group"]) for config in SERVICE_HOSTS.values()}):
        inventory[group] = {"hosts": []}
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

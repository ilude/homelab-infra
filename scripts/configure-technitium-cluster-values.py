#!/usr/bin/env python3
"""Prepare private tfvars for staged Technitium cluster deployment."""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
VALUES = REPO / "values"
TFVARS = VALUES / "terraform.tfvars"
ENV_FILE = VALUES / ".env"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


envfile = load_module("cluster_values_envfile", REPO / "scripts" / "envfile.py")
migrations = load_module("cluster_values_migrations", REPO / "scripts" / "migrate-values.py")


def scalar(lines: list[str], key: str) -> str:
    value = migrations.tfvars_scalar_value(lines, key)
    if not value:
        raise RuntimeError(f"missing required private tfvar {key}")
    return value


def raw(lines: list[str], key: str) -> str:
    value = migrations.tfvars_raw_value(lines, key)
    if not value:
        raise RuntimeError(f"missing required private tfvar {key}")
    return value


def set_raw(lines: list[str], key: str, value: str) -> bool:
    if migrations.tfvars_key_exists(lines, key):
        return migrations.replace_tfvars_raw(lines, key, value)
    return migrations.set_tfvars_raw(lines, key, value)


def all_private_ipv4_addresses() -> set[ipaddress.IPv4Address]:
    addresses: set[ipaddress.IPv4Address] = set()
    for path in (
        TFVARS,
        VALUES / "dns-records.local.json",
        VALUES / "ansible" / "inventory" / "local.yml",
        ENV_FILE,
    ):
        text = path.read_text(encoding="utf-8")
        for candidate in re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text):
            try:
                addresses.add(ipaddress.IPv4Address(candidate))
            except ipaddress.AddressValueError:
                continue
    return addresses


def next_unused_address(interface: ipaddress.IPv4Interface) -> ipaddress.IPv4Address:
    used = all_private_ipv4_addresses()
    for number in range(int(interface.ip) + 1, int(interface.network.broadcast_address)):
        candidate = ipaddress.IPv4Address(number)
        if candidate not in used:
            return candidate
    raise RuntimeError("no unused address remains after the current Technitium address")


def secondary_pve_host() -> str:
    host = envfile.get_env_value(ENV_FILE, "SECONDARY_PVE_HOST")
    if not host:
        raise RuntimeError("SECONDARY_PVE_HOST is not configured in values/.env")
    return host


def secondary_node_name() -> str:
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            secondary_pve_host(),
            "hostname",
            "--short",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    name = result.stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", name):
        raise RuntimeError("secondary Proxmox returned an invalid short hostname")
    return name


def secondary_vmid(lines: list[str]) -> int:
    configured_raw = migrations.tfvars_scalar_value(
        lines, "technitium_secondary_container_vmid"
    )
    configured = int(configured_raw or scalar(lines, "technitium_container_vmid"))
    qemu_conflict = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", secondary_pve_host(), "qm", "config", str(configured)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not qemu_conflict:
        return configured
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", secondary_pve_host(), "pvesh", "get", "/cluster/nextid"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def prepare_canary(lines: list[str]) -> bool:
    primary = ipaddress.IPv4Interface(scalar(lines, "technitium_container_ipv4_address"))
    existing_secondary = migrations.tfvars_scalar_value(
        lines, "technitium_secondary_container_ipv4_address"
    )
    secondary = (
        ipaddress.IPv4Interface(existing_secondary).ip
        if existing_secondary
        else next_unused_address(primary)
    )
    hostname = scalar(lines, "technitium_container_hostname")
    secondary_hostname = f"{hostname}-2"
    if len(secondary_hostname) > 63:
        raise RuntimeError("derived secondary Technitium hostname exceeds 63 characters")

    values = {
        "technitium_cluster_enabled": "false",
        "technitium_cluster_domain": migrations.hcl_quote(
            f"dns-cluster.{scalar(lines, 'technitium_container_search_domain')}"
        ),
        "technitium_virtual_ipv4_address": migrations.hcl_quote(str(primary)),
        "secondary_proxmox_insecure": raw(lines, "proxmox_insecure"),
        "secondary_proxmox_node_name": migrations.hcl_quote(secondary_node_name()),
        "secondary_proxmox_rootfs_datastore_id": raw(lines, "rootfs_datastore_id"),
        "secondary_proxmox_template_datastore_id": raw(lines, "template_datastore_id"),
        "technitium_secondary_container_vmid": str(secondary_vmid(lines)),
        "technitium_secondary_container_hostname": migrations.hcl_quote(secondary_hostname),
        "technitium_secondary_container_description": migrations.hcl_quote(
            "Technitium DNS secondary resolver managed by OpenTofu."
        ),
        "technitium_secondary_container_ipv4_address": migrations.hcl_quote(
            f"{secondary}/{primary.network.prefixlen}"
        ),
        "technitium_secondary_container_ipv4_gateway": raw(
            lines, "technitium_container_ipv4_gateway"
        ),
        "technitium_secondary_container_dns_servers": raw(
            lines, "technitium_container_dns_servers"
        ),
        "technitium_secondary_container_search_domain": raw(
            lines, "technitium_container_search_domain"
        ),
        "technitium_secondary_container_bridge": raw(lines, "technitium_container_bridge"),
        "technitium_secondary_container_vlan_id": raw(
            lines, "technitium_container_vlan_id"
        ),
        "technitium_secondary_container_cores": raw(lines, "technitium_container_cores"),
        "technitium_secondary_container_memory_mb": raw(
            lines, "technitium_container_memory_mb"
        ),
        "technitium_secondary_container_swap_mb": raw(
            lines, "technitium_container_swap_mb"
        ),
        "technitium_secondary_container_disk_gb": raw(lines, "technitium_container_disk_gb"),
    }
    changed = False
    for key, value in values.items():
        changed = set_raw(lines, key, value) or changed
    return changed


def activate_cluster(lines: list[str]) -> bool:
    enabled = scalar(lines, "technitium_cluster_enabled").lower() == "true"
    primary = ipaddress.IPv4Interface(scalar(lines, "technitium_container_ipv4_address"))
    if enabled:
        envfile.set_env_value(
            ENV_FILE, "TECHNITIUM_API_URL", f"http://{primary.ip}:5380/api"
        )
        return False
    virtual = ipaddress.IPv4Interface(scalar(lines, "technitium_virtual_ipv4_address"))
    if primary.ip != virtual.ip:
        raise RuntimeError("primary address already differs from the disabled cluster virtual address")
    direct = next_unused_address(primary)
    changed = set_raw(
        lines,
        "technitium_container_ipv4_address",
        migrations.hcl_quote(f"{direct}/{primary.network.prefixlen}"),
    )
    envfile.set_env_value(ENV_FILE, "TECHNITIUM_API_URL", f"http://{direct}:5380/api")
    return set_raw(lines, "technitium_cluster_enabled", "true") or changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("canary", "activate"))
    args = parser.parse_args()

    lines = TFVARS.read_text(encoding="utf-8").splitlines()
    changed = prepare_canary(lines) if args.phase == "canary" else activate_cluster(lines)
    if changed:
        TFVARS.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Technitium cluster private values phase {args.phase} is configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

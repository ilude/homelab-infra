#!/usr/bin/env python3
"""Migrate private values files to the current layout."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import secrets
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

GENERATED_SECRET_KEYS = {
    "INFISICAL_ENCRYPTION_KEY": lambda: secrets.token_hex(32),
    "INFISICAL_AUTH_SECRET": lambda: secrets.token_hex(32),
    "INFISICAL_POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(32),
}

SECRET_KEYS = {
    "PROXMOX_VE_API_TOKEN",
    "PROXMOX_VE_PASSWORD",
    "TECHNITIUM_API_TOKEN",
    "TF_VAR_technitium_api_token",
    "TF_VAR_container_root_password",
    "TF_VAR_lxc_root_password",
    "CF_DNS_API_TOKEN",
    "FORGEJO_RUNNER_REGISTRATION_SECRET",
    "TAILSCALE_AUTH_KEY",
    "INFISICAL_ENCRYPTION_KEY",
    "INFISICAL_AUTH_SECRET",
    "INFISICAL_POSTGRES_PASSWORD",
}

ENV_TO_INVENTORY = {
    "SERVER_NAME": "caddy_server_name",
    "FORGEJO_DOMAIN": "forgejo_domain",
    "FORGEJO_VERSION": "forgejo_version",
    "FORGEJO_SSH_PORT": "forgejo_ssh_port",
    "FORGEJO_ENABLE_CADDY": "forgejo_enable_caddy",
}
HISTORICAL_ENV_KEYS = ("FORGEJO_SERVER_NAME", "FORGEJO_UPSTREAM")
TF_VAR_RENAMES = {
    "TF_VAR_container_root_password": "TF_VAR_lxc_root_password",
    "TF_VAR_container_ssh_public_keys": "TF_VAR_lxc_ssh_public_keys",
}

TECHNITIUM_TFVARS_RENAMES = {
    "container_root_password": "lxc_root_password",
    "container_ssh_public_keys": "lxc_ssh_public_keys",
    "container_vmid": "technitium_container_vmid",
    "container_hostname": "technitium_container_hostname",
    "container_description": "technitium_container_description",
    "container_ipv4_address": "technitium_container_ipv4_address",
    "container_ipv4_gateway": "technitium_container_ipv4_gateway",
    "container_dns_servers": "technitium_container_dns_servers",
    "container_search_domain": "technitium_container_search_domain",
    "container_bridge": "technitium_container_bridge",
    "container_cores": "technitium_container_cores",
    "container_memory_mb": "technitium_container_memory_mb",
    "container_swap_mb": "technitium_container_swap_mb",
    "container_disk_gb": "technitium_container_disk_gb",
}

MIGRATION_ENV_KEYS = {
    "TF_VAR_technitium_api_token",
    *TF_VAR_RENAMES,
    *TF_VAR_RENAMES.values(),
    "TECHNITIUM_API_TOKEN",
    "TECHNITIUM_API_URL",
    "DNS_RECORDS_FILE",
    *GENERATED_SECRET_KEYS,
    *ENV_TO_INVENTORY,
    *HISTORICAL_ENV_KEYS,
}

ENV_LINE_RE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>=)(?P<value>.*)$")
TFVARS_LINE_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*?)(?:\s*#.*)?$")


class MigrationError(ValueError):
    pass


@dataclass
class EnvEntry:
    index: int
    key: str
    value: str


def parse_scalar(raw_value: str) -> str:
    try:
        parts = shlex.split(raw_value, posix=True, comments=False)
    except ValueError as error:
        raise MigrationError(f"invalid quoting: {error}") from error
    if len(parts) != 1:
        raise MigrationError("expected exactly one scalar value")
    return parts[0]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_env_lines(lines: list[str], path: Path) -> dict[str, EnvEntry]:
    entries: dict[str, EnvEntry] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key not in MIGRATION_ENV_KEYS:
            continue
        if key in entries:
            raise MigrationError(f"{path}: duplicate environment key {key}")
        entries[key] = EnvEntry(index, key, parse_scalar(match.group("value")))
    return entries


def set_env(lines: list[str], entries: dict[str, EnvEntry], key: str, value: str) -> bool:
    line = f"export {key}={shell_quote(value)}"
    if key in entries:
        if entries[key].value == value:
            return False
        lines[entries[key].index] = line
        entries[key].value = value
        return True
    if lines and lines[-1].strip():
        lines.append("")
    entries[key] = EnvEntry(len(lines), key, value)
    lines.append(line)
    return True


def remove_env(lines: list[str], entries: dict[str, EnvEntry], key: str) -> bool:
    entry = entries.get(key)
    if entry is None:
        return False
    lines[entry.index] = None  # type: ignore[assignment]
    del entries[key]
    for other in entries.values():
        if other.index > entry.index:
            other.index -= 1
    lines[:] = [line for line in lines if line is not None]
    return True


def tfvars_raw_value(lines: list[str], key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(?P<value>.+?)\s*(?:#.*)?$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group("value")
    return ""


def tfvars_scalar_value(lines: list[str], key: str) -> str:
    raw = tfvars_raw_value(lines, key)
    if not raw or raw == "null":
        return ""
    try:
        return parse_scalar(raw)
    except MigrationError:
        return ""


def set_tfvars_raw(lines: list[str], key: str, raw_value: str) -> bool:
    if tfvars_key_exists(lines, key):
        return False
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"{key} = {raw_value}")
    return True


def hcl_quote(value: str) -> str:
    return json.dumps(value)


def parse_tfvars(lines: list[str], path: Path) -> dict[str, tuple[int, str]]:
    values: dict[str, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = TFVARS_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key not in {"technitium_api_url", "dns_records_file"}:
            continue
        if key in values:
            raise MigrationError(f"{path}: duplicate tfvars key {key}")
        values[key] = (index, parse_scalar(match.group("value")))
    return values


def tfvars_key_exists(lines: list[str], key: str) -> bool:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    return any(pattern.match(line) for line in lines)


def rename_tfvars_key(lines: list[str], old_key: str, new_key: str) -> bool:
    old_pattern = re.compile(rf"^(?P<prefix>\s*){re.escape(old_key)}(?P<suffix>\s*=.*)$")
    old_indexes = [index for index, line in enumerate(lines) if old_pattern.match(line)]
    if not old_indexes:
        return False
    if tfvars_key_exists(lines, new_key):
        for index in reversed(old_indexes):
            lines.pop(index)
        return True
    index = old_indexes[0]
    match = old_pattern.match(lines[index])
    if match is None:
        return False
    lines[index] = f"{match.group('prefix')}{new_key}{match.group('suffix')}"
    for extra_index in reversed(old_indexes[1:]):
        lines.pop(extra_index)
    return True


def remove_tfvars(lines: list[str], values: dict[str, tuple[int, str]], key: str) -> bool:
    item = values.get(key)
    if item is None:
        return False
    index, _value = item
    lines[index] = None  # type: ignore[assignment]
    del values[key]
    for other_key, (other_index, other_value) in list(values.items()):
        if other_index > index:
            values[other_key] = (other_index - 1, other_value)
    lines[:] = [line for line in lines if line is not None]
    return True


def rename_env_key(
    lines: list[str], entries: dict[str, EnvEntry], old_key: str, new_key: str
) -> bool:
    old_entry = entries.get(old_key)
    if old_entry is None:
        return False
    new_entry = entries.get(new_key)
    if new_entry is not None and new_entry.value != old_entry.value:
        raise MigrationError(f"{old_key} and {new_key} differ")
    if new_entry is None:
        set_env(lines, entries, new_key, old_entry.value)
    remove_env(lines, entries, old_key)
    return True


def inventory_has_key(text: str, key: str) -> bool:
    return re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text) is not None


def service_domain(tfvars_lines: list[str]) -> str:
    domain = tfvars_scalar_value(tfvars_lines, "technitium_container_search_domain")
    if domain:
        return domain
    forgejo_server = tfvars_scalar_value(tfvars_lines, "forgejo_server_name")
    return forgejo_server.removeprefix("git.") if forgejo_server.startswith("git.") else "example.internal"


def subnet_ip(tfvars_lines: list[str], host_octet: int) -> str:
    for key in ("forgejo_lan_ip", "technitium_container_ipv4_address"):
        value = tfvars_scalar_value(tfvars_lines, key).split("/", 1)[0]
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address):
            parts = str(address).split(".")
            parts[-1] = str(host_octet)
            return ".".join(parts)
    return f"192.0.2.{host_octet}"


def ensure_optional_service_tfvars(tfvars_lines: list[str]) -> list[str]:
    changes: list[str] = []
    domain = service_domain(tfvars_lines)
    bridge = tfvars_scalar_value(tfvars_lines, "forgejo_container_bridge") or tfvars_scalar_value(tfvars_lines, "technitium_container_bridge") or "vmbr0"
    dns_servers = tfvars_raw_value(tfvars_lines, "forgejo_container_dns_servers") or tfvars_raw_value(tfvars_lines, "technitium_container_dns_servers") or '["1.1.1.1", "9.9.9.9"]'
    defaults = {
        "infisical_container_vmid": "110",
        "infisical_container_hostname": hcl_quote("infisical"),
        "infisical_container_description": hcl_quote("Infisical secrets service managed by OpenTofu."),
        "infisical_container_ipv4_address": hcl_quote("dhcp"),
        "infisical_container_ipv4_gateway": "null",
        "infisical_container_mac_address": hcl_quote("BC:24:11:00:00:03"),
        "infisical_lan_ip": hcl_quote(subnet_ip(tfvars_lines, 70)),
        "infisical_server_name": hcl_quote(f"infisical.{domain}"),
        "infisical_container_dns_servers": dns_servers,
        "infisical_container_search_domain": hcl_quote(domain),
        "infisical_container_bridge": hcl_quote(bridge),
        "infisical_container_cores": "2",
        "infisical_container_memory_mb": "4096",
        "infisical_container_swap_mb": "1024",
        "infisical_container_disk_gb": "20",
        "infisical_started": "true",
        "infisical_start_on_boot": "true",
        "hermes_container_vmid": "111",
        "hermes_container_hostname": hcl_quote("hermes"),
        "hermes_container_description": hcl_quote("Hermes management LXC managed by OpenTofu."),
        "hermes_container_ipv4_address": hcl_quote("dhcp"),
        "hermes_container_ipv4_gateway": "null",
        "hermes_container_mac_address": hcl_quote("BC:24:11:00:00:04"),
        "hermes_lan_ip": hcl_quote(subnet_ip(tfvars_lines, 71)),
        "hermes_server_name": hcl_quote(f"hermes.{domain}"),
        "hermes_container_dns_servers": dns_servers,
        "hermes_container_search_domain": hcl_quote(domain),
        "hermes_container_bridge": hcl_quote(bridge),
        "hermes_container_cores": "2",
        "hermes_container_memory_mb": "2048",
        "hermes_container_swap_mb": "512",
        "hermes_container_disk_gb": "64",
        "hermes_started": "true",
        "hermes_start_on_boot": "true",
    }
    for key, raw_value in defaults.items():
        if set_tfvars_raw(tfvars_lines, key, raw_value):
            changes.append(f"added {key}")
    for key in ("infisical_data_dataset", "infisical_data_host_path", "infisical_data_mount_path"):
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        original_len = len(tfvars_lines)
        tfvars_lines[:] = [line for line in tfvars_lines if not pattern.match(line)]
        if len(tfvars_lines) != original_len:
            changes.append(f"removed {key}")
    return changes


def ensure_inventory_vars(path: Path, text: str, domain: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    replacements = {
        "{{ lookup('env', 'FORGEJO_DOMAIN') }}": f"git.{domain}",
        "{{ lookup('env', 'SERVER_NAME') }}": f"dns.{domain}",
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
            changes.append("replaced legacy inventory env lookup")

    additions = {
        "infisical_vmid": "    infisical_vmid: 110",
        "infisical_domain": f"    infisical_domain: infisical.{domain}",
        "infisical_version": "    infisical_version: latest",
        "infisical_data_dir": "    infisical_data_dir: /var/lib/infisical",
        "infisical_encryption_key": "    infisical_encryption_key: \"{{ lookup('env', 'INFISICAL_ENCRYPTION_KEY') }}\"",
        "infisical_auth_secret": "    infisical_auth_secret: \"{{ lookup('env', 'INFISICAL_AUTH_SECRET') }}\"",
        "infisical_postgres_user": "    infisical_postgres_user: infisical",
        "infisical_postgres_db": "    infisical_postgres_db: infisical",
        "infisical_postgres_password": "    infisical_postgres_password: \"{{ lookup('env', 'INFISICAL_POSTGRES_PASSWORD') }}\"",
        "hermes_vmid": "    hermes_vmid: 111",
        "hermes_domain": f"    hermes_domain: hermes.{domain}",
        "hermes_repo_path": "    hermes_repo_path: /srv/homelab-infra",
    }
    lines = text.rstrip().splitlines() if text.strip() else ["---", "all:", "  vars:"]
    for key, line in additions.items():
        if inventory_has_key("\n".join(lines), key):
            continue
        lines.append(line)
        changes.append(f"added inventory {key}")
    return "\n".join(lines) + "\n", changes


def ensure_dns_records(path: Path, domain: str, infisical_ip: str, hermes_ip: str) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.setdefault("a_records", {})
    if not isinstance(records, dict):
        raise MigrationError(f"{path}: a_records must be an object")
    changes: list[str] = []
    for name, address in {f"infisical.{domain}": infisical_ip, f"hermes.{domain}": hermes_ip}.items():
        if records.get(name) == address:
            continue
        records[name] = address
        changes.append("added optional service DNS record")
    if changes:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changes


def enabled_optional_services(values_dir: Path) -> set[str]:
    if values_dir != Path("values"):
        return set()
    settings_path = Path("settings.local.json")
    if not settings_path.exists():
        return set()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    services = data.get("services", [])
    return {service for service in ("infisical", "hermes") if service in services}


def migrate(values_dir: Path) -> list[str]:
    env_path = values_dir / ".env"
    tfvars_path = values_dir / "terraform.tfvars"
    inventory_path = values_dir / "ansible" / "inventory" / "local.yml"

    changes: list[str] = []
    env_lines = read_lines(env_path)
    tfvars_lines = read_lines(tfvars_path)
    inventory_text = inventory_path.read_text(encoding="utf-8") if inventory_path.exists() else ""

    env_entries = parse_env_lines(env_lines, env_path)

    for old_key, new_key in TF_VAR_RENAMES.items():
        if rename_env_key(env_lines, env_entries, old_key, new_key):
            changes.append(f"renamed {old_key} to {new_key}")

    for old_key, new_key in TECHNITIUM_TFVARS_RENAMES.items():
        if rename_tfvars_key(tfvars_lines, old_key, new_key):
            changes.append(f"renamed {old_key} to {new_key}")
    optional_services = enabled_optional_services(values_dir)
    if optional_services:
        changes.extend(ensure_optional_service_tfvars(tfvars_lines))
    tfvars_values = parse_tfvars(tfvars_lines, tfvars_path)

    inventory_changes: list[str] = []
    if optional_services:
        for key, generator in GENERATED_SECRET_KEYS.items():
            if key not in env_entries:
                set_env(env_lines, env_entries, key, generator())
                changes.append(f"generated {key}")

        domain = service_domain(tfvars_lines)
        inventory_text, inventory_changes = ensure_inventory_vars(inventory_path, inventory_text, domain)
        changes.extend(inventory_changes)
        changes.extend(
            ensure_dns_records(
                values_dir / "dns-records.local.json",
                domain,
                tfvars_scalar_value(tfvars_lines, "infisical_lan_ip"),
                tfvars_scalar_value(tfvars_lines, "hermes_lan_ip"),
            )
        )

    old_token = env_entries.get("TF_VAR_technitium_api_token")
    new_token = env_entries.get("TECHNITIUM_API_TOKEN")
    if old_token and new_token and old_token.value != new_token.value:
        raise MigrationError(
            f"{env_path}: TF_VAR_technitium_api_token and TECHNITIUM_API_TOKEN differ"
        )
    if old_token and not new_token:
        set_env(env_lines, env_entries, "TECHNITIUM_API_TOKEN", old_token.value)
        changes.append("moved TF_VAR_technitium_api_token to TECHNITIUM_API_TOKEN")
    if remove_env(env_lines, env_entries, "TF_VAR_technitium_api_token"):
        changes.append("removed TF_VAR_technitium_api_token")

    old_url = tfvars_values.get("technitium_api_url")
    if old_url and "TECHNITIUM_API_URL" not in env_entries:
        set_env(env_lines, env_entries, "TECHNITIUM_API_URL", old_url[1])
        changes.append("moved technitium_api_url to TECHNITIUM_API_URL")
    if remove_tfvars(tfvars_lines, tfvars_values, "technitium_api_url"):
        changes.append("removed technitium_api_url from terraform.tfvars")

    old_dns_file = tfvars_values.get("dns_records_file")
    if old_dns_file and "DNS_RECORDS_FILE" not in env_entries:
        dns_file = old_dns_file[1]
        if dns_file == "../../values/dns-records.local.json":
            dns_file = "values/dns-records.local.json"
        set_env(env_lines, env_entries, "DNS_RECORDS_FILE", dns_file)
        changes.append("moved dns_records_file to DNS_RECORDS_FILE")
    if remove_tfvars(tfvars_lines, tfvars_values, "dns_records_file"):
        changes.append("removed dns_records_file from terraform.tfvars")

    for env_key, inventory_key in ENV_TO_INVENTORY.items():
        if env_key not in env_entries:
            continue
        if not inventory_has_key(inventory_text, inventory_key):
            key_label = f"{env_key} remains in .env because {inventory_key} is missing"
            changes.append(key_label)
            continue
        if remove_env(env_lines, env_entries, env_key):
            changes.append(f"removed duplicate {env_key}; inventory owns {inventory_key}")

    for env_key in HISTORICAL_ENV_KEYS:
        if remove_env(env_lines, env_entries, env_key):
            changes.append(f"removed historical unused {env_key}")

    if "DNS_RECORDS_FILE" not in env_entries:
        set_env(env_lines, env_entries, "DNS_RECORDS_FILE", "values/dns-records.local.json")
        changes.append("added DNS_RECORDS_FILE default")

    if changes:
        write_lines(env_path, env_lines)
        write_lines(tfvars_path, tfvars_lines)
        if inventory_path.exists() or inventory_changes:
            inventory_path.write_text(inventory_text, encoding="utf-8")
    return changes


def redact_change(change: str) -> str:
    for key in SECRET_KEYS:
        change = change.replace(key, key)
    return change


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    args = parser.parse_args(argv)

    try:
        changes = migrate(args.values_dir)
    except MigrationError as error:
        print(f"values migration failed: {error}", file=sys.stderr)
        return 1

    if changes:
        print("migrated values:")
        for change in changes:
            print(f"- {redact_change(change)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

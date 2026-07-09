#!/usr/bin/env python3
"""Migrate private values files to the current layout."""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import EnvEntry, EnvFileError, parse_env_lines as parse_envfile_lines, parse_scalar as envfile_parse_scalar, read_lines, remove_env, set_env, write_lines

GENERATED_SECRET_KEYS = {
    "INFISICAL_ENCRYPTION_KEY": lambda: secrets.token_hex(16),
    "INFISICAL_AUTH_SECRET": lambda: base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    "INFISICAL_POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(32),
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET": lambda: secrets.token_urlsafe(48),
    "SEARXNG_SECRET_KEY": lambda: secrets.token_urlsafe(48),
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
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
    "HERMES_WEB_SEARXNG_URL",
    "SEARXNG_SECRET_KEY",
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
    "container_vlan_id": "technitium_container_vlan_id",
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
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_WEB_SEARXNG_URL",
    *ENV_TO_INVENTORY,
    *HISTORICAL_ENV_KEYS,
}

TFVARS_LINE_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*?)(?:\s*#.*)?$")
HERMES_SCRYPT_N = 2**14
HERMES_SCRYPT_R = 8
HERMES_SCRYPT_P = 1
HERMES_SCRYPT_DKLEN = 32
HERMES_SCRYPT_SALT_BYTES = 16


class MigrationError(ValueError):
    pass


def hermes_hash_password(password: str) -> str:
    salt = secrets.token_bytes(HERMES_SCRYPT_SALT_BYTES)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=HERMES_SCRYPT_N,
        r=HERMES_SCRYPT_R,
        p=HERMES_SCRYPT_P,
        dklen=HERMES_SCRYPT_DKLEN,
        maxmem=0,
    )
    return (
        f"scrypt${HERMES_SCRYPT_N}${HERMES_SCRYPT_R}${HERMES_SCRYPT_P}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(derived_key).decode()}"
    )


def parse_scalar(raw_value: str) -> str:
    try:
        return envfile_parse_scalar(raw_value)
    except EnvFileError as error:
        raise MigrationError(str(error)) from error


def parse_env_lines(lines: list[str], path: Path) -> dict[str, EnvEntry]:
    try:
        return parse_envfile_lines(lines, path, allowed_keys=set(MIGRATION_ENV_KEYS), skip_unknown=True)
    except ValueError as error:
        raise MigrationError(str(error)) from error


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


def replace_tfvars_raw(lines: list[str], key: str, raw_value: str) -> bool:
    pattern = re.compile(rf"^(?P<prefix>\s*{re.escape(key)}\s*=\s*).*$")
    for index, line in enumerate(lines):
        if pattern.match(line):
            new_line = pattern.sub(rf"\g<prefix>{raw_value}", line)
            if new_line == line:
                return False
            lines[index] = new_line
            return True
    return False


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


def migrate_infisical_secret_formats(lines: list[str], entries: dict[str, EnvEntry]) -> list[str]:
    entry = entries.get("INFISICAL_ENCRYPTION_KEY")
    if entry is None:
        return []
    value = envfile_parse_scalar(entry.value)
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return []
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        set_env(lines, entries, "INFISICAL_ENCRYPTION_KEY", value[:32].lower())
        return ["normalized INFISICAL_ENCRYPTION_KEY to Infisical 16-byte hex format"]
    return []


def migrate_hermes_dashboard_password_hash(lines: list[str], entries: dict[str, EnvEntry]) -> list[str]:
    plaintext = entries.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD")
    password_hash = entries.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH")
    if plaintext is None:
        return []
    changes: list[str] = []
    if password_hash is None:
        set_env(lines, entries, "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH", hermes_hash_password(plaintext.value))
        changes.append("hashed HERMES_DASHBOARD_BASIC_AUTH_PASSWORD to HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH")
    if remove_env(lines, entries, "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"):
        changes.append("removed plaintext HERMES_DASHBOARD_BASIC_AUTH_PASSWORD")
    return changes


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


def cidr_prefix(value: str) -> str:
    match = re.search(r"/(\d+)$", value)
    return match.group(1) if match else "24"


def direct_technitium_api_url(tfvars_lines: list[str]) -> str:
    address = tfvars_scalar_value(tfvars_lines, "technitium_container_ipv4_address")
    host = address.split("/", 1)[0]
    return f"http://{host}:5380/api" if host else ""


def should_rewrite_technitium_api_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = parsed.hostname or ""
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return host.startswith(("dns.", "technitium."))


def ensure_direct_technitium_api_url(
    env_lines: list[str], env_entries: dict[str, EnvEntry], tfvars_lines: list[str]
) -> list[str]:
    entry = env_entries.get("TECHNITIUM_API_URL")
    direct_url = direct_technitium_api_url(tfvars_lines)
    if entry is None or not direct_url or not should_rewrite_technitium_api_url(entry.value):
        return []
    if set_env(env_lines, env_entries, "TECHNITIUM_API_URL", direct_url):
        return ["set TECHNITIUM_API_URL to direct Technitium LXC API endpoint"]
    return []


def ensure_static_service_addresses(tfvars_lines: list[str]) -> list[str]:
    changes: list[str] = []
    prefix = cidr_prefix(tfvars_scalar_value(tfvars_lines, "technitium_container_ipv4_address"))
    gateway = tfvars_scalar_value(tfvars_lines, "technitium_container_ipv4_gateway")
    service_keys = {
        "forgejo": ("forgejo_container_ipv4_address", "forgejo_container_ipv4_gateway", "forgejo_lan_ip"),
        "infisical": ("infisical_container_ipv4_address", "infisical_container_ipv4_gateway", "infisical_lan_ip"),
        "hermes": ("hermes_container_ipv4_address", "hermes_container_ipv4_gateway", "hermes_lan_ip"),
    }
    for service, (address_key, gateway_key, lan_key) in service_keys.items():
        lan_ip = tfvars_scalar_value(tfvars_lines, lan_key)
        if not lan_ip or tfvars_scalar_value(tfvars_lines, address_key) != "dhcp":
            continue
        if replace_tfvars_raw(tfvars_lines, address_key, hcl_quote(f"{lan_ip}/{prefix}")):
            changes.append(f"set {service} static IPv4 address from {lan_key}")
        if gateway and tfvars_raw_value(tfvars_lines, gateway_key) == "null":
            replace_tfvars_raw(tfvars_lines, gateway_key, hcl_quote(gateway))
            changes.append(f"set {service} IPv4 gateway")
    return changes


def ensure_vlan_tfvars(tfvars_lines: list[str]) -> list[str]:
    changes: list[str] = []
    service_prefixes = (
        "technitium_container",
        "forgejo_container",
        "forgejo_runner",
        "infisical_container",
        "hermes_container",
        "onramp_host",
        "tailscale_client",
    )
    for prefix in service_prefixes:
        if not (tfvars_key_exists(tfvars_lines, f"{prefix}_vmid") or tfvars_key_exists(tfvars_lines, f"{prefix}_bridge")):
            continue
        key = f"{prefix}_vlan_id"
        if set_tfvars_raw(tfvars_lines, key, "null"):
            changes.append(f"added {key}")
    return changes


def ensure_optional_service_tfvars(tfvars_lines: list[str], optional_services: set[str]) -> list[str]:
    changes: list[str] = []
    domain = service_domain(tfvars_lines)
    bridge = tfvars_scalar_value(tfvars_lines, "forgejo_container_bridge") or tfvars_scalar_value(tfvars_lines, "technitium_container_bridge") or "vmbr0"
    dns_servers = tfvars_raw_value(tfvars_lines, "forgejo_container_dns_servers") or tfvars_raw_value(tfvars_lines, "technitium_container_dns_servers") or '["1.1.1.1", "9.9.9.9"]'
    defaults: dict[str, str] = {}
    if "infisical" in optional_services:
        defaults.update({
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
        })
    if "hermes" in optional_services:
        defaults.update({
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
        })
    if "onramp_host" in optional_services or "searxng_onramp" in optional_services:
        defaults.update({
            "onramp_host_vmid": "112",
            "onramp_host_hostname": hcl_quote("onramp-host"),
            "onramp_host_description": hcl_quote("Debian 13 Podman onramp host for Onramp-managed services."),
            "onramp_host_image_datastore_id": hcl_quote("local"),
            "onramp_host_image_url": hcl_quote("https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2"),
            "onramp_host_image_file_name": hcl_quote("debian-13-genericcloud-amd64.qcow2"),
            "onramp_host_datastore_id": hcl_quote("local-lvm"),
            "onramp_host_ipv4_address": hcl_quote(f"{subnet_ip(tfvars_lines, 72)}/{cidr_prefix(tfvars_scalar_value(tfvars_lines, 'technitium_container_ipv4_address'))}"),
            "onramp_host_ipv4_gateway": hcl_quote(tfvars_scalar_value(tfvars_lines, "technitium_container_ipv4_gateway") or "192.0.2.1"),
            "onramp_host_dns_servers": dns_servers,
            "onramp_host_search_domain": hcl_quote(domain),
            "onramp_host_bridge": hcl_quote(bridge),
            "onramp_host_vlan_id": "null",
            "onramp_host_cores": "2",
            "onramp_host_memory_mb": "4096",
            "onramp_host_disk_gb": "32",
            "onramp_host_cloud_init_user": hcl_quote("onramp"),
            "onramp_host_ssh_public_keys": "[]",
            "onramp_host_password_authentication": "false",
            "onramp_host_permit_root_login": "false",
            "onramp_host_deploy_user": hcl_quote("onramp"),
            "onramp_host_deploy_dir": hcl_quote("/srv/onramp"),
            "onramp_host_allow_passwordless_sudo": "true",
            "onramp_host_allowed_ssh_cidrs": json.dumps(["192.0.2.0/24"]),
            "onramp_host_started": "true",
            "onramp_host_start_on_boot": "true",
        })
    if "searxng_onramp" in optional_services:
        defaults.update({
            "searxng_server_name": hcl_quote(f"searxng.apps.{domain}"),
            "searxng_public_url": hcl_quote(f"https://searxng.apps.{domain}"),
            "searxng_container_image": hcl_quote("docker.io/searxng/searxng:latest"),
            "searxng_container_port": "8080",
            "searxng_bind_address": hcl_quote("127.0.0.1"),
            "searxng_instance_name": hcl_quote("Homelab SearXNG"),
            "searxng_enable_public_url": "true",
        })
    for key, raw_value in defaults.items():
        if set_tfvars_raw(tfvars_lines, key, raw_value):
            changes.append(f"added {key}")
    obsolete_keys = (
        "infisical_data_dataset",
        "infisical_data_host_path",
        "infisical_data_mount_path",
        "onramp_host_template_vmid",
        "onramp_host_template_node_name",
        "onramp_host_clone_datastore_id",
    )
    for key in obsolete_keys:
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
        "hermes_dashboard_basic_auth_password:": "hermes_dashboard_basic_auth_password_hash:",
        "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD')": "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH')",
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
        "hermes_dashboard_enabled": "    hermes_dashboard_enabled: true",
        "hermes_dashboard_port": "    hermes_dashboard_port: 9119",
        "hermes_dashboard_host": "    hermes_dashboard_host: 127.0.0.1",
        "hermes_dashboard_basic_auth_username": "    hermes_dashboard_basic_auth_username: admin",
        "hermes_dashboard_basic_auth_password_hash": "    hermes_dashboard_basic_auth_password_hash: \"{{ lookup('env', 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH') }}\"",
        "hermes_dashboard_basic_auth_secret": "    hermes_dashboard_basic_auth_secret: \"{{ lookup('env', 'HERMES_DASHBOARD_BASIC_AUTH_SECRET') }}\"",
        "hermes_web_searxng_url": "    hermes_web_searxng_url: \"{{ lookup('env', 'HERMES_WEB_SEARXNG_URL') }}\"",
        "searxng_server_name": f"    searxng_server_name: searxng.apps.{domain}",
        "searxng_public_url": f"    searxng_public_url: https://searxng.apps.{domain}",
        "searxng_secret_key": "    searxng_secret_key: \"{{ lookup('env', 'SEARXNG_SECRET_KEY') }}\"",
        "searxng_container_image": "    searxng_container_image: docker.io/searxng/searxng:latest",
        "searxng_container_port": "    searxng_container_port: 8080",
        "searxng_bind_address": "    searxng_bind_address: 127.0.0.1",
        "searxng_instance_name": "    searxng_instance_name: Homelab SearXNG",
    }
    lines = text.rstrip().splitlines() if text.strip() else ["---", "all:", "  vars:"]
    for key, line in additions.items():
        if inventory_has_key("\n".join(lines), key):
            continue
        lines.append(line)
        changes.append(f"added inventory {key}")
    return "\n".join(lines) + "\n", changes


def ensure_dns_records(
    path: Path,
    domain: str,
    infisical_ip: str,
    hermes_ip: str,
    searxng_ip: str = "",
) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.setdefault("a_records", {})
    if not isinstance(records, dict):
        raise MigrationError(f"{path}: a_records must be an object")
    changes: list[str] = []
    desired = {f"infisical.{domain}": infisical_ip, f"hermes.{domain}": hermes_ip}
    if searxng_ip:
        desired[f"searxng.apps.{domain}"] = searxng_ip
    for name, address in desired.items():
        if not address or records.get(name) == address:
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
    return {service for service in ("infisical", "hermes", "onramp_host", "searxng_onramp") if service in services}


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
    changes.extend(migrate_infisical_secret_formats(env_lines, env_entries))
    changes.extend(migrate_hermes_dashboard_password_hash(env_lines, env_entries))
    if optional_services:
        changes.extend(ensure_optional_service_tfvars(tfvars_lines, optional_services))
    changes.extend(ensure_vlan_tfvars(tfvars_lines))
    changes.extend(ensure_static_service_addresses(tfvars_lines))
    changes.extend(ensure_direct_technitium_api_url(env_lines, env_entries, tfvars_lines))
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
        if "searxng_onramp" in optional_services and "HERMES_WEB_SEARXNG_URL" not in env_entries:
            set_env(env_lines, env_entries, "HERMES_WEB_SEARXNG_URL", f"https://searxng.apps.{domain}")
            changes.append("added HERMES_WEB_SEARXNG_URL for SearXNG onramp")
        changes.extend(
            ensure_dns_records(
                values_dir / "dns-records.local.json",
                domain,
                tfvars_scalar_value(tfvars_lines, "infisical_lan_ip"),
                tfvars_scalar_value(tfvars_lines, "hermes_lan_ip"),
                tfvars_scalar_value(tfvars_lines, "onramp_host_ipv4_address").split("/", 1)[0]
                if "searxng_onramp" in optional_services
                else "",
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
        direct_url = direct_technitium_api_url(tfvars_lines)
        api_url = direct_url if should_rewrite_technitium_api_url(old_url[1]) and direct_url else old_url[1]
        set_env(env_lines, env_entries, "TECHNITIUM_API_URL", api_url)
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

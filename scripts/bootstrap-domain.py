#!/usr/bin/env python3
"""Interactively derive domain-based private values for a new checkout."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import get_env_value, set_env_value
import settings

DEFAULT_VALUES_DIR = Path("values")
PLACEHOLDER_DOMAINS = ("example.internal", "example.net", "example.com")


def env_value(path: Path, key: str) -> str:
    return get_env_value(path, key)


def tfvar_value(path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        raw = match.group(1)
        if raw == "null":
            return ""
        try:
            parts = shlex.split(raw, posix=True, comments=False)
        except ValueError:
            return ""
        return parts[0] if parts else ""
    return ""


def set_tfvar_string(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = f'{key} = "{value}"'
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(replacement, text, count=1)
    else:
        text = text.rstrip() + "\n" + replacement + "\n"
    path.write_text(text, encoding="utf-8")


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def confirm(label: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def domain_from_hostname(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        return ""
    domain = value.removeprefix(prefix).split(":", 1)[0].rstrip("/")
    return domain if domain and not is_placeholder_domain(domain) else ""


def configured_domain(env_path: Path, tfvars_path: Path) -> str:
    api_url = env_value(env_path, "TECHNITIUM_API_URL")
    match = re.match(r"^https?://([^/:]+)", api_url)
    if match:
        domain = domain_from_hostname(match.group(1), "dns.")
        if domain:
            return domain

    search_domain = tfvar_value(tfvars_path, "technitium_container_search_domain")
    if search_domain and not is_placeholder_domain(search_domain):
        return search_domain

    for key, prefix in (("SERVER_NAME", "dns."), ("FORGEJO_DOMAIN", "git.")):
        domain = domain_from_hostname(env_value(env_path, key), prefix)
        if domain:
            return domain
    return ""


def is_placeholder_domain(domain: str) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in PLACEHOLDER_DOMAINS)


def validate_domain(domain: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or "." not in domain:
        raise ValueError("domain must contain only letters, numbers, dots, and dashes and include at least one dot")
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise ValueError("domain must not start/end with a dot or contain empty labels")


def validate_ip(value: str, label: str) -> None:
    try:
        ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an IP address") from error


def ip_without_cidr(value: str) -> str:
    return value.split("/", 1)[0]


def cidr_prefix(value: str) -> int:
    try:
        return ipaddress.ip_interface(value).network.prefixlen
    except ValueError:
        return 24


def ip_with_host(ip_value: str, host_octet: int) -> str:
    try:
        address = ipaddress.ip_address(ip_without_cidr(ip_value))
    except ValueError:
        return f"192.0.2.{host_octet}"
    if not isinstance(address, ipaddress.IPv4Address):
        return f"192.0.2.{host_octet}"
    octets = str(address).split(".")
    octets[-1] = str(host_octet)
    return ".".join(octets)


def service_ip_sequence(start_ip: str, count: int) -> list[str]:
    try:
        start = ipaddress.ip_address(start_ip)
    except ValueError as error:
        raise ValueError("service IP range start must be an IPv4 address") from error
    if not isinstance(start, ipaddress.IPv4Address):
        raise ValueError("service IP range start must be an IPv4 address")
    return [str(start + offset) for offset in range(count)]


def host_lan_defaults() -> tuple[str, str, int]:
    env_ip = os.environ.get("HOST_LAN_IP", "")
    env_gateway = os.environ.get("HOST_LAN_GATEWAY", "")
    env_prefix = os.environ.get("HOST_LAN_PREFIX", "")
    if env_ip and env_gateway:
        try:
            return env_ip, env_gateway, int(env_prefix or "24")
        except ValueError:
            return env_ip, env_gateway, 24

    local_ip = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("1.1.1.1", 53))
            local_ip = probe.getsockname()[0]
    except OSError:
        pass

    gateway = ""
    for command in (("ip", "route", "show", "default"), ("netstat", "-rn")):
        try:
            result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in result.stdout.splitlines():
            if command[0] == "ip" and line.startswith("default "):
                parts = line.split()
                if "via" in parts:
                    gateway = parts[parts.index("via") + 1]
                    break
            default_route = ".".join(("0", "0", "0", "0"))
            if command[0] == "netstat" and (line.startswith(default_route) or line.strip().startswith("default")):
                parts = line.split()
                if len(parts) >= 2:
                    gateway = parts[1]
                    break
        if gateway:
            break

    if local_ip.startswith(("172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")):
        return "", "", 24
    return local_ip, gateway, 24


def update_inventory(path: Path, domain: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    block = (
        f"    caddy_server_name: dns.{domain}\n"
        "    caddy_server_names:\n"
        f"      - dns.{domain}\n"
        f"      - technitium.{domain}\n"
        "    caddy_upstream: 127.0.0.1:5380"
    )
    pattern = re.compile(
        r"^    caddy_server_name:.*\n"
        r"(?:    caddy_server_names:\n(?:      - .*\n)+)?"
        r"    caddy_upstream: 127\.0\.0\.1:5380",
        re.MULTILINE,
    )
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
    else:
        text = text.rstrip() + "\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


def infisical_dns_target(services: set[str], legacy_ip: str, onramp_ip: str) -> str:
    legacy_enabled = "infisical" in services
    onramp_enabled = "infisical_onramp" in services
    if legacy_enabled and onramp_enabled:
        raise ValueError("infisical and infisical_onramp are mutually exclusive deployment modes")
    if onramp_enabled:
        return onramp_ip
    if legacy_enabled:
        return legacy_ip
    return ""


def update_dns_records(
    path: Path,
    domain: str,
    technitium_ip: str,
    forgejo_ip: str,
    infisical_ip: str,
    hermes_ip: str,
    searxng_ip: str,
) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.setdefault("a_records", {})
    if not isinstance(records, dict):
        raise ValueError(f"{path}: a_records must be an object")
    for placeholder in (
        "dns.example.internal",
        "technitium.example.internal",
        "git.example.internal",
        "infisical.example.internal",
        "hermes.example.internal",
        "searxng.apps.example.net",
    ):
        records.pop(placeholder, None)
    records[f"dns.{domain}"] = technitium_ip
    records[f"technitium.{domain}"] = technitium_ip
    records[f"git.{domain}"] = forgejo_ip
    infisical_record = f"infisical.{domain}"
    if infisical_ip:
        records[infisical_record] = infisical_ip
    else:
        records.pop(infisical_record, None)
    records[f"hermes.{domain}"] = hermes_ip
    records[f"searxng.apps.{domain}"] = searxng_ip
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    values_dir = args.values_dir
    env_path = values_dir / ".env"
    tfvars_path = values_dir / "terraform.tfvars"
    inventory_path = values_dir / "ansible" / "inventory" / "local.yml"
    dns_records_path = values_dir / "dns-records.local.json"

    missing = [path for path in (env_path, tfvars_path, inventory_path, dns_records_path) if not path.exists()]
    if missing:
        print("Missing values files. Run just setup first.", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    try:
        services = set(settings.load_settings()["services"])
    except settings.SettingsError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        infisical_dns_target(services, "", "")
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    existing_domain = configured_domain(env_path, tfvars_path)
    if args.if_needed and existing_domain and not args.force:
        print(f"Domain values already configured for {existing_domain}; skipping domain wizard.")
        return 0

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Skipping domain wizard because stdin/stdout is not interactive.")
        return 0

    if existing_domain and not args.force:
        if not confirm(f"Domain values already look configured for {existing_domain}. Reconfigure?", False):
            return 0

    default_domain = existing_domain or "example.internal"
    domain = prompt("Base domain for service hostnames", default_domain).lower()
    try:
        validate_domain(domain)
    except ValueError as error:
        print(f"Invalid domain: {error}", file=sys.stderr)
        return 1

    technitium_address = tfvar_value(tfvars_path, "technitium_container_ipv4_address") or "192.0.2.53/24"
    default_technitium_ip = ip_without_cidr(technitium_address)
    default_gateway = tfvar_value(tfvars_path, "technitium_container_ipv4_gateway") or "192.0.2.1"
    default_prefix = cidr_prefix(technitium_address)
    host_ip, host_gateway, host_prefix = host_lan_defaults()
    if host_ip and is_placeholder_domain(default_domain):
        default_technitium_ip = ip_with_host(host_ip, 22)
        default_gateway = host_gateway or ip_with_host(host_ip, 1)
        default_prefix = host_prefix

    default_service_start = tfvar_value(tfvars_path, "forgejo_lan_ip") or ip_with_host(default_technitium_ip, 23)
    technitium_ip = prompt("Technitium DNS/UI IP", default_technitium_ip)
    gateway = prompt("LXC IPv4 gateway", default_gateway)
    service_start_ip = prompt("First managed service IP (Forgejo; following services increment from this)", default_service_start)
    try:
        validate_ip(technitium_ip, "Technitium DNS/UI IP")
        validate_ip(gateway, "LXC IPv4 gateway")
        forgejo_ip, forgejo_runner_ip, tailscale_ip, legacy_infisical_ip, hermes_ip, searxng_ip = service_ip_sequence(service_start_ip, 6)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    set_env_value(env_path, "TECHNITIUM_API_URL", f"http://{technitium_ip}:5380/api")
    set_env_value(env_path, "DNS_RECORDS_FILE", "values/dns-records.local.json")
    set_env_value(env_path, "HERMES_WEB_SEARXNG_URL", f"https://searxng.apps.{domain}")

    set_tfvar_string(tfvars_path, "technitium_container_ipv4_address", f"{technitium_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "technitium_container_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "technitium_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "forgejo_server_name", f"git.{domain}")
    set_tfvar_string(tfvars_path, "forgejo_lan_ip", forgejo_ip)
    set_tfvar_string(tfvars_path, "forgejo_container_ipv4_address", f"{forgejo_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "forgejo_container_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "forgejo_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "forgejo_runner_ipv4_address", f"{forgejo_runner_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "forgejo_runner_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "forgejo_runner_search_domain", domain)
    set_tfvar_string(tfvars_path, "infisical_server_name", f"infisical.{domain}")
    set_tfvar_string(tfvars_path, "infisical_lan_ip", legacy_infisical_ip)
    set_tfvar_string(tfvars_path, "infisical_container_ipv4_address", f"{legacy_infisical_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "infisical_container_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "infisical_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "hermes_server_name", f"hermes.{domain}")
    set_tfvar_string(tfvars_path, "hermes_lan_ip", hermes_ip)
    set_tfvar_string(tfvars_path, "hermes_container_ipv4_address", f"{hermes_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "hermes_container_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "hermes_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "tailscale_client_ipv4_address", f"{tailscale_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "tailscale_client_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "tailscale_client_search_domain", domain)
    set_tfvar_string(tfvars_path, "onramp_host_ipv4_address", f"{searxng_ip}/{default_prefix}")
    set_tfvar_string(tfvars_path, "onramp_host_ipv4_gateway", gateway)
    set_tfvar_string(tfvars_path, "onramp_host_search_domain", domain)
    set_tfvar_string(tfvars_path, "searxng_server_name", f"searxng.apps.{domain}")
    set_tfvar_string(tfvars_path, "searxng_public_url", f"https://searxng.apps.{domain}")

    update_inventory(inventory_path, domain)
    inventory_text = inventory_path.read_text(encoding="utf-8")
    inventory_text = inventory_text.replace("infisical.example.internal", f"infisical.{domain}")
    inventory_text = inventory_text.replace("hermes.example.internal", f"hermes.{domain}")
    inventory_text = inventory_text.replace("searxng.apps.example.net", f"searxng.apps.{domain}")
    inventory_path.write_text(inventory_text, encoding="utf-8")
    infisical_ip = infisical_dns_target(
        services,
        legacy_infisical_ip,
        ip_without_cidr(tfvar_value(tfvars_path, "onramp_host_ipv4_address")),
    )
    update_dns_records(dns_records_path, domain, technitium_ip, forgejo_ip, infisical_ip, hermes_ip, searxng_ip)

    print("Updated domain-derived values:")
    print(f"  TECHNITIUM_API_URL=http://{technitium_ip}:5380/api")
    print(f"  LXC gateway: {gateway}")
    print(f"  Managed service IPs: git={forgejo_ip}, runner={forgejo_runner_ip}, tailscale={tailscale_ip}, infisical={infisical_ip}, hermes={hermes_ip}, searxng={searxng_ip}")
    print(f"  DNS records: dns.{domain}, technitium.{domain}, git.{domain}, infisical.{domain}, hermes.{domain}, searxng.apps.{domain}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=DEFAULT_VALUES_DIR)
    parser.add_argument("--if-needed", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

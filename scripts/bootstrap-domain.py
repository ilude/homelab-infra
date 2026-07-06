#!/usr/bin/env python3
"""Interactively derive domain-based private values for a new checkout."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import get_env_value, set_env_value

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


def update_dns_records(
    path: Path,
    domain: str,
    technitium_ip: str,
    forgejo_ip: str,
    infisical_ip: str,
    hermes_ip: str,
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
    ):
        records.pop(placeholder, None)
    records[f"dns.{domain}"] = technitium_ip
    records[f"technitium.{domain}"] = technitium_ip
    records[f"git.{domain}"] = forgejo_ip
    records[f"infisical.{domain}"] = infisical_ip
    records[f"hermes.{domain}"] = hermes_ip
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

    default_technitium_ip = ip_without_cidr(tfvar_value(tfvars_path, "technitium_container_ipv4_address") or "192.0.2.53")
    default_forgejo_ip = tfvar_value(tfvars_path, "forgejo_lan_ip") or "192.0.2.62"
    default_infisical_ip = tfvar_value(tfvars_path, "infisical_lan_ip") or "192.0.2.70"
    default_hermes_ip = tfvar_value(tfvars_path, "hermes_lan_ip") or "192.0.2.71"
    technitium_ip = prompt("Technitium DNS/UI IP", default_technitium_ip)
    forgejo_ip = prompt("Forgejo LAN IP", default_forgejo_ip)
    infisical_ip = prompt("Infisical LAN IP", default_infisical_ip)
    hermes_ip = prompt("Hermes LAN IP", default_hermes_ip)
    try:
        validate_ip(technitium_ip, "Technitium DNS/UI IP")
        validate_ip(forgejo_ip, "Forgejo LAN IP")
        validate_ip(infisical_ip, "Infisical LAN IP")
        validate_ip(hermes_ip, "Hermes LAN IP")
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    set_env_value(env_path, "TECHNITIUM_API_URL", f"https://dns.{domain}/api")
    set_env_value(env_path, "DNS_RECORDS_FILE", "values/dns-records.local.json")

    set_tfvar_string(tfvars_path, "technitium_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "forgejo_server_name", f"git.{domain}")
    set_tfvar_string(tfvars_path, "forgejo_lan_ip", forgejo_ip)
    set_tfvar_string(tfvars_path, "forgejo_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "forgejo_runner_search_domain", domain)
    set_tfvar_string(tfvars_path, "infisical_server_name", f"infisical.{domain}")
    set_tfvar_string(tfvars_path, "infisical_lan_ip", infisical_ip)
    set_tfvar_string(tfvars_path, "infisical_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "hermes_server_name", f"hermes.{domain}")
    set_tfvar_string(tfvars_path, "hermes_lan_ip", hermes_ip)
    set_tfvar_string(tfvars_path, "hermes_container_search_domain", domain)
    set_tfvar_string(tfvars_path, "tailscale_client_search_domain", domain)

    update_inventory(inventory_path, domain)
    inventory_text = inventory_path.read_text(encoding="utf-8")
    inventory_text = inventory_text.replace("infisical.example.internal", f"infisical.{domain}")
    inventory_text = inventory_text.replace("hermes.example.internal", f"hermes.{domain}")
    inventory_path.write_text(inventory_text, encoding="utf-8")
    update_dns_records(dns_records_path, domain, technitium_ip, forgejo_ip, infisical_ip, hermes_ip)

    print("Updated domain-derived values:")
    print(f"  TECHNITIUM_API_URL=https://dns.{domain}/api")
    print(f"  DNS records: dns.{domain}, technitium.{domain}, git.{domain}, infisical.{domain}, hermes.{domain}")
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

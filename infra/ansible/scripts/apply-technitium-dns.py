#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

DNS_NAME_RE = re.compile(r"^(?=.{1,253}\.?$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$")
TOP_LEVEL_KEYS = {"settings", "zones", "a_records", "cname_records"}
SETTINGS_KEYS = {
    "forwarders",
    "forwarderProtocol",
    "concurrentForwarding",
    "dnssecValidation",
    "preferIPv6",
}
FORWARDER_PROTOCOLS = {"Udp", "Tcp", "Tls", "Https"}


class ConfigError(ValueError):
    pass


class TechnitiumClient:
    def __init__(self, api_url: str, token: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    def call(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        data = urllib.parse.urlencode(params).encode()
        request = urllib.request.Request(
            f"{self.api_url}{path}", data=data, headers=self.headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode()
        result = json.loads(body)
        if result.get("status") != "ok":
            raise RuntimeError(result)
        return result


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("DNS records file must contain a JSON object")
    return data


def validate_dns_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{field} must be a non-empty DNS name")
    name = value.rstrip(".")
    if not DNS_NAME_RE.match(name):
        raise ConfigError(f"{field} must be a valid DNS name")
    return name


def validate_forwarder(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty string")
    if any(ord(char) < 32 for char in value):
        raise ConfigError(f"{field} must not contain control characters")
    return value


def zone_for(domain: str, zones: Mapping[str, Sequence[str]]) -> str:
    matches = [zone for zone in zones if domain == zone or domain.endswith(f".{zone}")]
    if not matches:
        raise ConfigError(f"No configured zone for {domain}")
    return max(matches, key=len)


def require_object(config: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be an object")
    return value


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    missing = {"zones", "a_records", "cname_records"} - set(config)
    if missing:
        raise ConfigError(f"Missing required top-level keys: {', '.join(sorted(missing))}")
    unknown = set(config) - TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(f"Unknown top-level keys: {', '.join(sorted(unknown))}")

    zones_raw = require_object(config, "zones")
    zones: dict[str, list[str]] = {}
    for zone_raw, forwarders_raw in zones_raw.items():
        zone = validate_dns_name(zone_raw, f"zones.{zone_raw}")
        if not isinstance(forwarders_raw, list) or not forwarders_raw:
            raise ConfigError(f"zones.{zone} must be a non-empty list")
        zones[zone] = [
            validate_forwarder(forwarder, f"zones.{zone}[{index}]")
            for index, forwarder in enumerate(forwarders_raw)
        ]

    a_records_raw = require_object(config, "a_records")
    a_records: dict[str, str] = {}
    for domain_raw, ip_raw in a_records_raw.items():
        domain = validate_dns_name(domain_raw, f"a_records.{domain_raw}")
        zone_for(domain, zones)
        if not isinstance(ip_raw, str):
            raise ConfigError(f"a_records.{domain} must be an IPv4 address string")
        try:
            ip_address = str(ipaddress.IPv4Address(ip_raw))
        except ipaddress.AddressValueError as error:
            raise ConfigError(f"a_records.{domain} must be an IPv4 address") from error
        a_records[domain] = ip_address

    cname_records_raw = require_object(config, "cname_records")
    cname_records: dict[str, str] = {}
    for domain_raw, cname_raw in cname_records_raw.items():
        domain = validate_dns_name(domain_raw, f"cname_records.{domain_raw}")
        if domain in a_records:
            raise ConfigError(f"{domain} cannot have both A and CNAME records")
        zone_for(domain, zones)
        cname_records[domain] = validate_dns_name(cname_raw, f"cname_records.{domain}")

    validated: dict[str, Any] = {
        "zones": zones,
        "a_records": a_records,
        "cname_records": cname_records,
    }

    settings = config.get("settings")
    if settings is not None:
        if not isinstance(settings, dict):
            raise ConfigError("settings must be an object")
        missing_settings = SETTINGS_KEYS - set(settings)
        if missing_settings:
            raise ConfigError(
                f"Missing settings keys: {', '.join(sorted(missing_settings))}"
            )
        unknown_settings = set(settings) - SETTINGS_KEYS
        if unknown_settings:
            raise ConfigError(
                f"Unknown settings keys: {', '.join(sorted(unknown_settings))}"
            )
        forwarders = settings["forwarders"]
        if not isinstance(forwarders, list) or not forwarders:
            raise ConfigError("settings.forwarders must be a non-empty list")
        protocol = settings["forwarderProtocol"]
        if protocol not in FORWARDER_PROTOCOLS:
            raise ConfigError(
                "settings.forwarderProtocol must be one of Udp, Tcp, Tls, Https"
            )
        for key in ("concurrentForwarding", "dnssecValidation", "preferIPv6"):
            if not isinstance(settings[key], bool):
                raise ConfigError(f"settings.{key} must be a boolean")
        validated["settings"] = {
            "forwarders": [
                validate_forwarder(forwarder, f"settings.forwarders[{index}]")
                for index, forwarder in enumerate(forwarders)
            ],
            "forwarderProtocol": protocol,
            "concurrentForwarding": settings["concurrentForwarding"],
            "dnssecValidation": settings["dnssecValidation"],
            "preferIPv6": settings["preferIPv6"],
        }

    return validated


def bool_param(value: bool) -> str:
    return "true" if value else "false"


def response_records(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("records", "response"):
        value = result.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, Mapping)]
        if isinstance(value, dict):
            records = value.get("records")
            if isinstance(records, list):
                return [record for record in records if isinstance(record, Mapping)]
            if value.get("name") or value.get("domain"):
                return [value]
    record = result.get("record")
    if isinstance(record, dict):
        return [record]
    return []


def record_matches(
    client: TechnitiumClient,
    zone: str,
    domain: str,
    record_type: str,
    value_field: str,
    desired_value: str,
) -> bool:
    try:
        result = client.call(
            "/zones/records/get",
            {"zone": zone, "domain": domain, "type": record_type},
        )
    except RuntimeError:
        return False
    for record in response_records(result):
        if str(record.get("type", record_type)).upper() != record_type:
            continue
        if str(record.get("name", record.get("domain", domain))).rstrip(".") != domain:
            continue
        if str(record.get(value_field, "")).rstrip(".") == desired_value.rstrip("."):
            return True
    return False


def apply_config(
    config: Mapping[str, Any], client: TechnitiumClient, catalog: str | None = None
) -> None:
    zones = config["zones"]
    settings = config.get("settings")
    if settings:
        client.call(
            "/settings/set",
            {
                "forwarders": ",".join(settings["forwarders"]),
                "forwarderProtocol": settings["forwarderProtocol"],
                "concurrentForwarding": bool_param(settings["concurrentForwarding"]),
                "dnssecValidation": bool_param(settings["dnssecValidation"]),
                "preferIPv6": bool_param(settings["preferIPv6"]),
            },
        )
        print("configured upstream DNS forwarders")

    for zone, forwarders in zones.items():
        try:
            client.call(
                "/zones/create",
                {"zone": zone, "type": "Forwarder", "initializeForwarder": "false"},
            )
            print(f"created zone {zone}")
        except RuntimeError as error:
            message = str(error).lower()
            if "already" in message or "exists" in message:
                print(f"zone exists {zone}")
            else:
                raise

        if catalog:
            client.call(
                "/zones/options/set",
                {"zone": zone, "catalog": catalog},
            )
            print(f"configured catalog membership {zone}")

        for index, forwarder in enumerate(forwarders):
            client.call(
                "/zones/records/add",
                {
                    "zone": zone,
                    "domain": zone,
                    "type": "FWD",
                    "ttl": "300",
                    "overwrite": "true" if index == 0 else "false",
                    "protocol": "Udp",
                    "forwarder": forwarder,
                    "forwarderPriority": "1",
                    "dnssecValidation": "false",
                    "proxyType": "NoProxy",
                },
            )
        print(f"configured forwarders {zone}")

    for domain, ip_address in config["a_records"].items():
        zone = zone_for(domain, zones)
        if record_matches(client, zone, domain, "A", "ipAddress", ip_address):
            print(f"unchanged A {domain}")
            continue
        client.call(
            "/zones/records/add",
            {
                "zone": zone,
                "domain": domain,
                "type": "A",
                "ttl": "300",
                "overwrite": "true",
                "ipAddress": ip_address,
            },
        )
        print(f"upserted A {domain}")

    for domain, cname in config["cname_records"].items():
        zone = zone_for(domain, zones)
        if record_matches(client, zone, domain, "CNAME", "cname", cname):
            print(f"unchanged CNAME {domain}")
            continue
        client.call(
            "/zones/records/add",
            {
                "zone": zone,
                "domain": domain,
                "type": "CNAME",
                "ttl": "300",
                "overwrite": "true",
                "cname": cname,
            },
        )
        print(f"upserted CNAME {domain}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply or validate Technitium DNS records JSON.")
    parser.add_argument("--check", action="store_true", help="validate JSON without API calls")
    parser.add_argument("--catalog", default="", help="catalog zone for managed zone membership")
    parser.add_argument("dns_records_file", type=Path)
    args = parser.parse_args(argv)

    try:
        config = validate_config(load_config(args.dns_records_file))
        if args.check:
            print(f"validated DNS records file {args.dns_records_file}")
            return 0

        api_url = os.environ["TECHNITIUM_API_URL"]
        token = os.environ["TECHNITIUM_API_TOKEN"]
        catalog = validate_dns_name(args.catalog, "catalog") if args.catalog else None
        apply_config(config, TechnitiumClient(api_url, token), catalog)
    except KeyError as error:
        print(f"Missing environment variable: {error.args[0]}", file=sys.stderr)
        return 1
    except (ConfigError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

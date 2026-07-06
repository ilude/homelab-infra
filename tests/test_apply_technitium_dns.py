from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "ansible" / "scripts" / "apply-technitium-dns.py"
spec = importlib.util.spec_from_file_location("apply_technitium_dns", SCRIPT)
assert spec and spec.loader
apply_dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_dns)


VALID_CONFIG = {
    "settings": {
        "forwarders": [
            "dns.quad9.net (9.9.9.9:853)",
            "dns.quad9.net (149.112.112.112:853)",
        ],
        "forwarderProtocol": "Tls",
        "concurrentForwarding": False,
        "dnssecValidation": True,
        "preferIPv6": False,
    },
    "zones": {
        "example.internal": ["192.0.2.10:54", "192.0.2.11:54"],
        "apps.example.net": ["192.0.2.20:54"],
    },
    "a_records": {
        "dns.example.internal": "192.0.2.53",
        "app.apps.example.net": "192.0.2.20",
    },
    "cname_records": {
        "www.example.internal": "dns.example.internal",
    },
}


class DnsValidationTests(unittest.TestCase):
    def test_valid_config_passes(self) -> None:
        validated = apply_dns.validate_config(VALID_CONFIG)
        self.assertEqual(validated["a_records"]["dns.example.internal"], "192.0.2.53")

    def test_check_mode_does_not_need_api_environment(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as file:
            json.dump(VALID_CONFIG, file)
            path = file.name
        old_api_url = os.environ.pop("TECHNITIUM_API_URL", None)
        old_token = os.environ.pop("TECHNITIUM_API_TOKEN", None)
        try:
            self.assertEqual(apply_dns.main(["--check", path]), 0)
        finally:
            Path(path).unlink()
            if old_api_url is not None:
                os.environ["TECHNITIUM_API_URL"] = old_api_url
            if old_token is not None:
                os.environ["TECHNITIUM_API_TOKEN"] = old_token

    def test_missing_required_key_fails(self) -> None:
        config = dict(VALID_CONFIG)
        del config["zones"]
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_unknown_top_level_key_fails(self) -> None:
        config = dict(VALID_CONFIG, extra={})
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_invalid_zone_name_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["zones"] = {"bad zone": ["192.0.2.10:54"]}
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_empty_forwarder_list_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["zones"] = {"example.internal": []}
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_invalid_a_record_ip_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["a_records"] = {"dns.example.internal": "999.0.2.53"}
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_record_outside_configured_zones_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["a_records"] = {"dns.example.invalid": "192.0.2.53"}
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_cname_source_conflicting_with_a_record_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["cname_records"] = {"dns.example.internal": "app.apps.example.net"}
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)

    def test_invalid_settings_type_fails(self) -> None:
        config = dict(VALID_CONFIG)
        config["settings"] = []
        with self.assertRaises(apply_dns.ConfigError):
            apply_dns.validate_config(config)


class FakeClient:
    def __init__(self, records: dict[tuple[str, str, str], dict[str, str]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.records = records or {}

    def call(self, path: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((path, params))
        if path == "/zones/records/get":
            record = self.records.get((params["zone"], params["domain"], params["type"]))
            return {"status": "ok", "records": [record] if record else []}
        return {"status": "ok"}


class DnsApplyTests(unittest.TestCase):
    def test_apply_uses_client_without_opening_sockets(self) -> None:
        client = FakeClient()
        apply_dns.apply_config(apply_dns.validate_config(VALID_CONFIG), client)
        paths = [path for path, _params in client.calls]
        self.assertIn("/zones/create", paths)
        self.assertIn("/zones/records/add", paths)

    def test_apply_sends_expected_payloads(self) -> None:
        client = FakeClient()
        apply_dns.apply_config(apply_dns.validate_config(VALID_CONFIG), client)

        settings = client.calls[0]
        self.assertEqual(settings[0], "/settings/set")
        self.assertEqual(settings[1]["forwarderProtocol"], "Tls")
        self.assertEqual(settings[1]["concurrentForwarding"], "false")
        self.assertEqual(settings[1]["dnssecValidation"], "true")
        self.assertIn(",", settings[1]["forwarders"])

        zone_create = next(
            params for path, params in client.calls if path == "/zones/create"
        )
        self.assertEqual(zone_create["type"], "Forwarder")
        self.assertEqual(zone_create["initializeForwarder"], "false")

        fwd_records = [
            params
            for path, params in client.calls
            if path == "/zones/records/add"
            and params["type"] == "FWD"
            and params["domain"] == "example.internal"
        ]
        self.assertEqual(fwd_records[0]["overwrite"], "true")
        self.assertEqual(fwd_records[1]["overwrite"], "false")
        self.assertEqual(fwd_records[0]["protocol"], "Udp")
        self.assertEqual(fwd_records[0]["ttl"], "300")
        self.assertEqual(fwd_records[0]["proxyType"], "NoProxy")

        a_record = next(
            params
            for path, params in client.calls
            if path == "/zones/records/add" and params.get("domain") == "app.apps.example.net"
        )
        self.assertEqual(a_record["zone"], "apps.example.net")
        self.assertEqual(a_record["type"], "A")
        self.assertEqual(a_record["ipAddress"], "192.0.2.20")

        cname_record = next(
            params
            for path, params in client.calls
            if path == "/zones/records/add" and params["type"] == "CNAME"
        )
        self.assertEqual(cname_record["zone"], "example.internal")
        self.assertEqual(cname_record["cname"], "dns.example.internal")

    def test_matching_a_and_cname_records_are_not_upserted(self) -> None:
        client = FakeClient(
            {
                ("example.internal", "dns.example.internal", "A"): {
                    "type": "A",
                    "domain": "dns.example.internal",
                    "ipAddress": "192.0.2.53",
                },
                ("apps.example.net", "app.apps.example.net", "A"): {
                    "type": "A",
                    "domain": "app.apps.example.net",
                    "ipAddress": "192.0.2.20",
                },
                ("example.internal", "www.example.internal", "CNAME"): {
                    "type": "CNAME",
                    "domain": "www.example.internal",
                    "cname": "dns.example.internal",
                },
            }
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            apply_dns.apply_config(apply_dns.validate_config(VALID_CONFIG), client)

        changed_records = [
            params
            for path, params in client.calls
            if path == "/zones/records/add" and params["type"] in {"A", "CNAME"}
        ]
        self.assertEqual(changed_records, [])
        self.assertNotIn("upserted A", buffer.getvalue())
        self.assertNotIn("upserted CNAME", buffer.getvalue())

    def test_changed_a_record_is_upserted(self) -> None:
        client = FakeClient(
            {
                ("example.internal", "dns.example.internal", "A"): {
                    "type": "A",
                    "domain": "dns.example.internal",
                    "ipAddress": "192.0.2.54",
                }
            }
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            apply_dns.apply_config(apply_dns.validate_config(VALID_CONFIG), client)

        changed_a_records = [
            params
            for path, params in client.calls
            if path == "/zones/records/add" and params["type"] == "A"
        ]
        self.assertTrue(any(record["domain"] == "dns.example.internal" for record in changed_a_records))
        self.assertIn("upserted A dns.example.internal", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

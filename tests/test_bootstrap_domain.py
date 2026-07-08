from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap-domain.py"
spec = importlib.util.spec_from_file_location("bootstrap_domain", SCRIPT)
assert spec and spec.loader
bootstrap_domain = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bootstrap_domain
spec.loader.exec_module(bootstrap_domain)


class BootstrapDomainTests(unittest.TestCase):
    def test_configured_domain_uses_technitium_api_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env_path = root / ".env"
            tfvars_path = root / "terraform.tfvars"
            env_path.write_text(
                'export TECHNITIUM_API_URL="https://dns.lab.example/api"\n',
                encoding="utf-8",
            )
            tfvars_path.write_text('technitium_container_search_domain = "example.internal"\n', encoding="utf-8")

            self.assertEqual(
                bootstrap_domain.configured_domain(env_path, tfvars_path),
                "lab.example",
            )

    def test_configured_domain_uses_tfvars_when_env_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env_path = root / ".env"
            tfvars_path = root / "terraform.tfvars"
            env_path.write_text(
                'export TECHNITIUM_API_URL="https://dns.example.internal/api"\n',
                encoding="utf-8",
            )
            tfvars_path.write_text('technitium_container_search_domain = "lab.example"\n', encoding="utf-8")

            self.assertEqual(
                bootstrap_domain.configured_domain(env_path, tfvars_path),
                "lab.example",
            )

    def test_configured_domain_uses_tfvars_when_api_url_is_direct_ip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env_path = root / ".env"
            tfvars_path = root / "terraform.tfvars"
            env_path.write_text(
                'export TECHNITIUM_API_URL="http://192.0.2.53:5380/api"\n',
                encoding="utf-8",
            )
            tfvars_path.write_text('technitium_container_search_domain = "lab.example"\n', encoding="utf-8")

            self.assertEqual(
                bootstrap_domain.configured_domain(env_path, tfvars_path),
                "lab.example",
            )

    def test_service_ip_sequence_allocates_contiguous_addresses(self) -> None:
        self.assertEqual(
            bootstrap_domain.service_ip_sequence("192.0.2.23", 5),
            [
                "192.0.2.23",
                "192.0.2.24",
                "192.0.2.25",
                "192.0.2.26",
                "192.0.2.27",
            ],
        )

    def test_update_dns_records_adds_searxng_onramp_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dns_path = Path(temp) / "dns-records.local.json"
            dns_path.write_text(
                '{"a_records":{"searxng.apps.example.net":"192.0.2.72"}}\n',
                encoding="utf-8",
            )

            bootstrap_domain.update_dns_records(
                dns_path,
                "lab.example",
                "192.0.2.53",
                "192.0.2.62",
                "192.0.2.70",
                "192.0.2.71",
                "192.0.2.72",
            )

            text = dns_path.read_text(encoding="utf-8")
            self.assertIn('"searxng.apps.lab.example": "192.0.2.72"', text)
            self.assertNotIn("searxng.apps.example.net", text)

    def test_update_inventory_writes_concrete_caddy_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            inventory_path = Path(temp) / "local.yml"
            inventory_path.write_text(
                "all:\n"
                "  vars:\n"
                "    caddy_server_name: dns.example.internal\n"
                "    caddy_server_names:\n"
                "      - dns.example.internal\n"
                "      - technitium.example.internal\n"
                "    caddy_upstream: 127.0.0.1:5380\n",
                encoding="utf-8",
            )

            bootstrap_domain.update_inventory(inventory_path, "lab.example")

            text = inventory_path.read_text(encoding="utf-8")
            self.assertIn("caddy_server_name: dns.lab.example", text)
            self.assertIn("- dns.lab.example", text)
            self.assertIn("- technitium.lab.example", text)
            self.assertNotIn("SERVER_NAME", text)


if __name__ == "__main__":
    unittest.main()

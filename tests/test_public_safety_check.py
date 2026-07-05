from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "public-safety-check.py"
spec = importlib.util.spec_from_file_location("public_safety_check", SCRIPT)
assert spec and spec.loader
public_safety = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = public_safety
spec.loader.exec_module(public_safety)


class PublicSafetyScanTests(unittest.TestCase):
    def test_rfc5737_address_passes(self) -> None:
        findings = public_safety.scan_ips("README.md", 1, "host 192.0.2.10")
        self.assertEqual(findings, [])

    def test_rfc1918_address_fails(self) -> None:
        findings = public_safety.scan_ips("README.md", 1, "host 192.168.1.10")  # public-safety: allow-ip
        self.assertEqual(len(findings), 1)

    def test_cgnat_address_fails(self) -> None:
        findings = public_safety.scan_ips("README.md", 1, "host 100.64.1.10")  # public-safety: allow-ip
        self.assertEqual(len(findings), 1)

    def test_ipv6_ula_fails(self) -> None:
        findings = public_safety.scan_ips("README.md", 1, "host fd00::1")  # public-safety: allow-ip
        self.assertEqual(len(findings), 1)

    def test_allow_comment_skips_ip_scan(self) -> None:
        findings = public_safety.scan_ips(
            "README.md", 1, "host 192.168.1.10 # public-safety: allow-ip"
        )
        self.assertEqual(findings, [])

    def test_placeholder_secret_assignment_passes(self) -> None:
        findings = public_safety.scan_secrets(
            "scaffold/.env.example", 1, 'CF_DNS_API_TOKEN="REPLACE_ME"'
        )
        self.assertEqual(findings, [])

    def test_real_secret_assignment_is_redacted(self) -> None:
        secret_line = "TECHNITIUM_ADMIN_PASSWORD=" + "supersecretvalue"  # public-safety: allow-secret
        findings = public_safety.scan_secrets("README.md", 1, secret_line)
        self.assertEqual(len(findings), 1)
        self.assertIn("<redacted>", findings[0].message)
        self.assertNotIn("supersecretvalue", findings[0].message)

    def test_python_requirement_with_token_in_name_passes(self) -> None:
        findings = public_safety.scan_secrets("tools/requirements.txt", 1, "pytokens==0.4.1")  # public-safety: allow-secret
        self.assertEqual(findings, [])

    def test_private_key_header_fails(self) -> None:
        findings = public_safety.scan_secrets(
            "README.md", 1, "-----BEGIN OPENSSH PRIVATE KEY-----"  # public-safety: allow-secret
        )
        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()

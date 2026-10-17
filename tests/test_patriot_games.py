from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "infra/ansible/roles/patriot_games/files/manage-caddy.py"
spec = importlib.util.spec_from_file_location("patriot_caddy", HELPER)
assert spec and spec.loader
caddy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caddy)


class PatriotCaddyTests(unittest.TestCase):
    def test_preserves_existing_routes_and_updates_only_managed_block(self) -> None:
        original = "{\n email ops@example.internal\n}\nold.example.internal {\n respond ok\n}\n"
        first = caddy.managed_config(original, "new.example.internal {\n respond first\n}\n")
        self.assertTrue(first.startswith(original))
        self.assertEqual(first, caddy.managed_config(first, "new.example.internal {\n respond first\n}\n"))
        updated = caddy.managed_config(first, "new.example.internal {\n respond second\n}\n")
        self.assertTrue(updated.startswith(original))
        self.assertNotIn("respond first", updated)
        self.assertIn("respond second", updated)
        self.assertEqual(updated.count(caddy.BEGIN), 1)

    def test_scopes_legacy_dns_once_preserving_email_routes_and_token(self) -> None:
        global_block = "{\n    email ops@example.internal\n    acme_dns cloudflare {$CF_DNS_API_TOKEN}\n}\n"
        routes = "    handle @old {\n        reverse_proxy old-service:80\n    }\n}\n"
        original = global_block + "*.example.internal {\n" + routes
        scoped = caddy.scope_legacy_dns(original, "*.example.internal")
        expected = (
            "{\n    email ops@example.internal\n}\n*.example.internal {\n"
            "    tls {\n        dns cloudflare {$CF_DNS_API_TOKEN}\n    }\n" + routes
        )
        self.assertEqual(scoped, expected)
        self.assertEqual(caddy.scope_legacy_dns(scoped, "*.example.internal"), scoped)
        combined = caddy.managed_config(scoped, "new.example.net {\n respond ok\n}\n")
        self.assertEqual(caddy.scope_legacy_dns(combined, "*.example.internal"), combined)

    def test_legacy_migration_rejects_wrong_site_without_modifying_config(self) -> None:
        original = "{\n acme_dns cloudflare {$CF_DNS_API_TOKEN}\n}\n*.example.internal {\n}\n"
        with self.assertRaisesRegex(ValueError, "exactly one configured"):
            caddy.scope_legacy_dns(original, "*.other.example.internal")

    def test_rejects_broken_block_instead_of_overwriting_old_routes(self) -> None:
        with self.assertRaises(ValueError):
            caddy.managed_config(f"{caddy.BEGIN}\nold route\n", "new route")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "infra/ansible/roles/patriot_games/files/manage-caddy.py"
spec = importlib.util.spec_from_file_location("patriot_caddy", HELPER)
assert spec and spec.loader
caddy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caddy)
world_spec = importlib.util.spec_from_file_location(
    "patriot_world", HELPER.with_name("configure-world.py")
)
assert world_spec and world_spec.loader
world = importlib.util.module_from_spec(world_spec)
world_spec.loader.exec_module(world)


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


SANDBOX = """SandboxVars = {
    VERSION = 6,
    StarterKit = false,
    FireSpread = true,
    Map = {
        AllowMiniMap = false,
    },
    ZombieConfig = {
        PopulationMultiplier = 0.65,
    },
}
"""


class PatriotWorldTests(unittest.TestCase):
    def test_changes_selected_nested_options_and_preserves_other_content(self) -> None:
        configured = world.sandbox_config(SANDBOX, {
            "StarterKit": True,
            "Map.AllowMiniMap": True,
            "ZombieConfig.PopulationMultiplier": 0.325,
        })
        expected = SANDBOX.replace("StarterKit = false", "StarterKit = true").replace(
            "AllowMiniMap = false", "AllowMiniMap = true"
        ).replace("PopulationMultiplier = 0.65", "PopulationMultiplier = 0.325")
        self.assertEqual(configured, expected)

    def test_rejects_unknown_fields_instead_of_appending_invalid_lua(self) -> None:
        with self.assertRaises(ValueError):
            world.sandbox_config(SANDBOX, {"Missing.Option": True})

    def test_file_changes_are_idempotent_and_leave_credentials_and_saves_intact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            server = base / "server-data/Server"
            server.mkdir(parents=True)
            ini = server / "pzserver.ini"
            ini.write_text("PVP=true\nPassword=test-join-password\nOpen=true\n")
            (server / "pzserver_SandboxVars.lua").write_text(SANDBOX)
            (server / "pzserver_spawnregions.lua").write_text("old spawn choices\n")
            save = base / "server-data/Saves/Multiplayer/pzserver/map.bin"
            save.parent.mkdir(parents=True)
            save.write_bytes(b"world data")
            for name in ("Town One", "Town Two"):
                points = base / "server-files/media/maps" / name / "spawnpoints.lua"
                points.parent.mkdir(parents=True)
                points.write_text("function SpawnPoints() return {} end\n")
            settings = {"sandbox": {"StarterKit": True}, "pvp": False,
                        "spawn_regions": ["Town One", "Town Two"]}
            changes = world.configured_files(base, "pzserver", settings)
            self.assertEqual(len(changes), 3)
            for path, content in changes.items():
                path.write_text(content)
            self.assertEqual(world.configured_files(base, "pzserver", settings), {})
            self.assertEqual(ini.read_text(), "PVP=false\nPassword=test-join-password\nOpen=true\n")
            self.assertIn('media/maps/Town Two/spawnpoints.lua', (server / "pzserver_spawnregions.lua").read_text())
            self.assertEqual(save.read_bytes(), b"world data")
            with self.assertRaises(ValueError):
                world.spawn_config(base / "server-files/media/maps", ["Missing Town"])


if __name__ == "__main__":
    unittest.main()

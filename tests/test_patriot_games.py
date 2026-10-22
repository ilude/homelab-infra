from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from jinja2 import Environment
import yaml

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "infra/ansible/roles/patriot_games/files/manage-caddy.py"
spec = importlib.util.spec_from_file_location("patriot_caddy", HELPER)
assert spec and spec.loader
caddy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caddy)
world_spec = importlib.util.spec_from_file_location(
    "patriot_world", HELPER.with_name("compare-config.py")
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


class PatriotComposeTests(unittest.TestCase):
    def test_optional_playit_uses_host_network_and_private_env_file(self) -> None:
        env = Environment()
        env.filters["to_json"] = json.dumps
        template = env.from_string((HELPER.parent.parent / "templates/compose.yml.j2").read_text())
        values = {
            "patriot_games_project": "test-games",
            "zomboid_image": "test/zomboid:pinned",
            "zomboid_web_image": "test/rcon:pinned",
            "patriot_dozzle_image": "test/dozzle:pinned",
            "patriot_games_stop_grace_period": "120s",
            "patriot_games_network": "test-network",
        }
        without = yaml.safe_load(template.render(**values))
        self.assertNotIn("playit", without["services"])
        values["patriot_playit_image"] = "ghcr.io/playit-cloud/playit-agent:1.0@sha256:" + "a" * 64
        enabled = yaml.safe_load(template.render(**values))
        playit = enabled["services"]["playit"]
        self.assertEqual(playit["network_mode"], "host")
        self.assertEqual(playit["restart"], "unless-stopped")
        self.assertEqual(playit["env_file"], [{"path": "playit.env", "format": "raw"}])
        self.assertNotIn("ports", playit)
        self.assertNotIn("environment", playit)
        self.assertEqual(enabled["services"]["zomboid"], without["services"]["zomboid"])


class PatriotWorldTests(unittest.TestCase):
    def test_ansible_renders_concrete_profile_filenames_before_comparing(self) -> None:
        role = HELPER.parent.parent
        tasks = yaml.safe_load((role / "tasks/main.yml").read_text())
        render = next(task for task in tasks
                      if task["name"] == "Render complete authoritative Zomboid configuration")
        identity = dict.fromkeys([
            "ResetID", "ServerPlayerID", "Seed", "PublicName", "PublicDescription",
            "ServerWelcomeMessage", "DiscordToken", "DiscordChatChannel", "DiscordLogChannel",
            "DiscordCommandChannel", "WebhookAddress", "server_browser_announced_ip",
            "BadWordListFile", "GoodWordListFile",
        ], "")
        expected = ["test-world.ini", "test-world_SandboxVars.lua", "test-world_spawnregions.lua"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "templates").mkdir()
            for name in ("server.ini.j2", "SandboxVars.lua.j2", "spawnregions.lua.j2"):
                (root / "templates" / name).write_text((role / "templates" / name).read_text())
            play = [{
                "hosts": "localhost", "gather_facts": False,
                "vars": {"patriot_games_server_name": "test-world",
                         "patriot_games_max_players": 16,
                         "patriot_games_server_identity": identity,
                         "expected_filenames": expected},
                "tasks": [render, {"name": "Check actual filenames",
                                   "ansible.builtin.assert": {"that": [
                                       "patriot_games_rendered_config.keys() | sort == expected_filenames | sort"
                                   ]}}],
            }]
            playbook = root / "render.yml"
            playbook.write_text(yaml.safe_dump(play, sort_keys=False))
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
                env={**os.environ, "ZOMBOID_JOIN_PASSWORD": "test-join",
                     "ZOMBOID_RCON_PASSWORD": "test-rcon"},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comparison_ignores_generated_comments_but_not_settings_or_strings(self) -> None:
        self.assertEqual(world.normalized("# generated\nPVP=false\nResetID=123\n", ".ini"),
                         world.normalized("ResetID=123\n\nPVP=false\n", ".ini"))
        original = 'SandboxVars = { MinutesPerPage = 0.5, Text = "a -- b", }'
        rewritten = '-- generated\nSandboxVars={MinutesPerPage=0.50,Text="a -- b",}'
        self.assertEqual(world.normalized(original, ".lua"), world.normalized(rewritten, ".lua"))
        self.assertNotEqual(world.normalized(original, ".lua"),
                            world.normalized(original.replace("0.5", "2.0"), ".lua"))
        self.assertNotEqual(world.normalized(original, ".lua"),
                            world.normalized(original.replace("a -- b", "a--b"), ".lua"))

    def test_complete_templates_preserve_baseline_and_render_identity_and_secrets(self) -> None:
        templates = HELPER.parent.parent / "templates"
        env = Environment()
        env.globals["lookup"] = lambda kind, key: {
            "ZOMBOID_JOIN_PASSWORD": "test-join", "ZOMBOID_RCON_PASSWORD": "test-rcon",
        }[key]
        identity = dict.fromkeys([
            "PublicName", "PublicDescription", "ServerWelcomeMessage", "DiscordToken",
            "DiscordChatChannel", "DiscordLogChannel", "DiscordCommandChannel", "WebhookAddress",
            "server_browser_announced_ip", "BadWordListFile", "GoodWordListFile",
        ], "")
        identity.update(ResetID=123, ServerPlayerID="456", Seed="preserved-seed")
        ini = env.from_string((templates / "server.ini.j2").read_text()).render(
            patriot_games_server_identity=identity, patriot_games_max_players=16)
        for option in ["MapRemotePlayerVisibility=4", "PlayerSafehouse=true",
                       "SafehouseAllowRespawn=true", "AdminSafehouse=false", "TrashDeleteAll=false",
                       "SafehouseAllowTrepass=true", "SafehouseAllowFire=true", "SafehouseAllowLoot=true",
                       "SafehouseDaySurvivedToClaim=0", "SafeHouseRemovalTime=144",
                       "SafehouseAllowNonResidential=false", "ResetID=123", "ServerPlayerID=456",
                       "Seed=preserved-seed", "Password=test-join", "RCONPassword=test-rcon"]:
            self.assertIn(option + "\n", ini)
        sandbox = (templates / "SandboxVars.lua.j2").read_text()
        self.assertIn("MinutesPerPage = 0.5,", sandbox)
        self.assertIn("Global = 2.0,", sandbox)
        self.assertIn("GlobalToggle = true,", sandbox)
        configs = {"pzserver.ini": ini, "pzserver_SandboxVars.lua": sandbox,
                   "pzserver_spawnregions.lua": (templates / "spawnregions.lua.j2").read_text()}
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory)
            self.assertTrue(world.differs(server, configs))
            for filename, content in configs.items():
                (server / filename).write_text(content)
            self.assertFalse(world.differs(server, configs))
            (server / "pzserver.ini").write_text(ini.replace("ResetID=123", "ResetID=789"))
            self.assertTrue(world.differs(server, configs))


if __name__ == "__main__":
    unittest.main()

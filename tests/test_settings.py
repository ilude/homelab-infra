from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "settings.py"
spec = importlib.util.spec_from_file_location("settings_script", SCRIPT)
assert spec and spec.loader
settings_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings_script)


class SettingsTests(unittest.TestCase):
    def write_settings(self, data: object) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with handle:
            json.dump(data, handle)
        return Path(handle.name)

    def test_missing_settings_uses_defaults(self) -> None:
        path = Path(tempfile.gettempdir()) / "missing-homelab-settings.json"
        settings = settings_script.load_settings(path)
        self.assertEqual(settings["values_repo"]["remote"], "")
        self.assertEqual(settings["services"], ["technitium", "forgejo"])

    def test_values_remote_is_loaded(self) -> None:
        path = self.write_settings({"values_repo": {"remote": "git@example.invalid:repo.git"}})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(settings["values_repo"]["remote"], "git@example.invalid:repo.git")

    def test_unknown_service_fails(self) -> None:
        path = self.write_settings({"services": ["unknown"]})
        try:
            with self.assertRaises(settings_script.SettingsError):
                settings_script.load_settings(path)
        finally:
            path.unlink()

    def write_registry(self, services: dict[str, object]) -> Path:
        return self.write_settings({"default_services": ["first"], "services": services})

    def test_registry_rejects_unknown_self_and_cyclic_dependencies(self) -> None:
        cases = {
            "unknown": {
                "first": {"playbooks": ["first.yml"], "dependencies": ["missing"]},
            },
            "self": {
                "first": {"playbooks": ["first.yml"], "dependencies": ["first"]},
            },
            "cycle": {
                "first": {"playbooks": ["first.yml"], "dependencies": ["second"]},
                "second": {"playbooks": ["second.yml"], "dependencies": ["first"]},
            },
        }
        for name, services in cases.items():
            with self.subTest(name=name):
                path = self.write_registry(services)
                try:
                    with self.assertRaisesRegex(ValueError, name if name != "cycle" else "cyclic"):
                        settings_script.load_service_registry(path)
                finally:
                    path.unlink()

    def test_registry_rejects_duplicate_playbooks_and_invalid_execution_resources(self) -> None:
        cases = {
            "duplicate playbook": {
                "first": {"playbooks": ["shared.yml"], "dependencies": []},
                "second": {"playbooks": ["shared.yml"], "dependencies": []},
            },
            "execution_resource": {
                "first": {"playbooks": ["first.yml"], "dependencies": [], "execution_resource": ""},
            },
            "terraform_module": {
                "first": {"playbooks": ["first.yml"], "dependencies": [], "terraform_module": ""},
            },
        }
        for message, services in cases.items():
            with self.subTest(message=message):
                path = self.write_registry(services)
                try:
                    with self.assertRaisesRegex(ValueError, message):
                        settings_script.load_service_registry(path)
                finally:
                    path.unlink()

    def test_registry_requires_reciprocal_conflicts(self) -> None:
        path = self.write_registry(
            {
                "first": {"playbooks": ["first.yml"], "dependencies": [], "conflicts": ["second"]},
                "second": {"playbooks": ["second.yml"], "dependencies": []},
            }
        )
        try:
            with self.assertRaisesRegex(ValueError, "reciprocal"):
                settings_script.load_service_registry(path)
        finally:
            path.unlink()

    def test_technitium_adds_dns_playbook(self) -> None:
        path = self.write_settings({"services": ["technitium"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            [
                "infra/ansible/playbooks/technitium.yml",
                "infra/ansible/playbooks/caddy-proxy.yml",
                "infra/ansible/playbooks/technitium-dns.yml",
            ],
        )

    def test_tailscale_client_adds_playbook(self) -> None:
        path = self.write_settings({"services": ["tailscale_client"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            ["infra/ansible/playbooks/tailscale-client.yml"],
        )

    def test_forgejo_runner_requires_forgejo(self) -> None:
        path = self.write_settings({"services": ["forgejo_runner"]})
        try:
            with self.assertRaises(settings_script.SettingsError):
                settings_script.load_settings(path)
        finally:
            path.unlink()

    def test_forgejo_runner_adds_runner_playbook(self) -> None:
        path = self.write_settings({"services": ["forgejo", "forgejo_runner"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            [
                "infra/ansible/playbooks/forgejo.yml",
                "infra/ansible/playbooks/forgejo-runner.yml",
            ],
        )

    def test_infisical_deployment_modes_are_mutually_exclusive(self) -> None:
        path = self.write_settings({"services": ["onramp_host", "infisical", "infisical_onramp"]})
        try:
            with self.assertRaisesRegex(settings_script.SettingsError, "conflicts with"):
                settings_script.load_settings(path)
        finally:
            path.unlink()

    def test_infisical_and_hermes_add_playbooks(self) -> None:
        path = self.write_settings({"services": ["infisical", "hermes"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            [
                "infra/ansible/playbooks/infisical.yml",
                "infra/ansible/playbooks/hermes.yml",
            ],
        )

    def test_onramp_host_adds_playbook_without_hermes_dependency(self) -> None:
        path = self.write_settings({"services": ["onramp_host"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(settings["services"], ["onramp_host"])
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            ["infra/ansible/playbooks/onramp-host.yml"],
        )

    def test_searxng_onramp_requires_onramp_host(self) -> None:
        path = self.write_settings({"services": ["searxng_onramp"]})
        try:
            with self.assertRaises(settings_script.SettingsError):
                settings_script.load_settings(path)
        finally:
            path.unlink()

    def test_searxng_onramp_adds_playbook_after_onramp_host(self) -> None:
        path = self.write_settings({"services": ["onramp_host", "searxng_onramp"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            [
                "infra/ansible/playbooks/onramp-host.yml",
                "infra/ansible/playbooks/searxng-onramp.yml",
            ],
        )

    def test_hermes_does_not_require_onramp_host(self) -> None:
        path = self.write_settings({"services": ["hermes"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(settings["services"], ["hermes"])

    def test_playbooks_follow_service_order(self) -> None:
        path = self.write_settings({"services": ["technitium", "forgejo", "tailscale_client"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(
            settings_script.ansible_playbooks(settings["services"]),
            [
                "infra/ansible/playbooks/technitium.yml",
                "infra/ansible/playbooks/caddy-proxy.yml",
                "infra/ansible/playbooks/technitium-dns.yml",
                "infra/ansible/playbooks/forgejo.yml",
                "infra/ansible/playbooks/tailscale-client.yml",
            ],
        )

    def test_tofu_target_returns_enabled_service_module(self) -> None:
        settings = {"services": ["forgejo"]}
        self.assertEqual(settings_script.tofu_target(settings, "forgejo"), "module.forgejo")
        with self.assertRaisesRegex(settings_script.SettingsError, "not enabled"):
            settings_script.tofu_target(settings, "hermes")

    def test_tofu_target_command_returns_enabled_service_module(self) -> None:
        path = self.write_settings({"services": ["hermes"]})
        try:
            with tempfile.TemporaryFile("w+", encoding="utf-8") as stdout:
                original_stdout = settings_script.sys.stdout
                settings_script.sys.stdout = stdout
                try:
                    rc = settings_script.main(["--settings", str(path), "tofu-target", "hermes"])
                finally:
                    settings_script.sys.stdout = original_stdout
                stdout.seek(0)
                output = stdout.read().strip()
        finally:
            path.unlink()
        self.assertEqual(rc, 0)
        self.assertEqual(output, "module.hermes")

    def test_all_ansible_playbooks_are_unique(self) -> None:
        playbooks = settings_script.all_ansible_playbooks()
        self.assertIn("infra/ansible/playbooks/tailscale-client.yml", playbooks)
        self.assertEqual(len(playbooks), len(set(playbooks)))

    def test_summary_lists_services_and_playbooks(self) -> None:
        path = self.write_settings({"services": ["tailscale_client"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        summary = settings_script.settings_summary(settings)
        self.assertIn("Enabled services: tailscale_client", summary)
        self.assertIn("infra/ansible/playbooks/tailscale-client.yml", summary)


if __name__ == "__main__":
    unittest.main()

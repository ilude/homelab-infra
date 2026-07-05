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

    def test_technitium_implies_caddy_proxy_playbook(self) -> None:
        path = self.write_settings({"services": ["technitium"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        playbooks = [
            playbook
            for service in settings["services"]
            for playbook in settings_script.SERVICE_PLAYBOOKS[service]
        ]
        self.assertEqual(
            playbooks,
            [
                "infra/ansible/playbooks/technitium.yml",
                "infra/ansible/playbooks/caddy-proxy.yml",
            ],
        )

    def test_tailscale_client_is_valid_without_ansible_playbook(self) -> None:
        path = self.write_settings({"services": ["tailscale_client"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        self.assertEqual(settings["services"], ["tailscale_client"])

    def test_technitium_has_post_apply_dns_hook(self) -> None:
        self.assertEqual(
            settings_script.SERVICES["technitium"]["post_apply"],
            ("scripts/apply-technitium-dns.sh",),
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
        playbooks = [
            playbook
            for service in settings["services"]
            for playbook in settings_script.SERVICE_PLAYBOOKS[service]
        ]
        self.assertEqual(
            playbooks,
            [
                "infra/ansible/playbooks/forgejo.yml",
                "infra/ansible/playbooks/forgejo-runner.yml",
            ],
        )

    def test_playbooks_follow_service_order(self) -> None:
        path = self.write_settings({"services": ["technitium", "forgejo", "tailscale_client"]})
        try:
            settings = settings_script.load_settings(path)
        finally:
            path.unlink()
        playbooks = [
            playbook
            for service in settings["services"]
            for playbook in settings_script.SERVICE_PLAYBOOKS[service]
        ]
        self.assertEqual(
            playbooks,
            [
                "infra/ansible/playbooks/technitium.yml",
                "infra/ansible/playbooks/caddy-proxy.yml",
                "infra/ansible/playbooks/forgejo.yml",
            ],
        )


if __name__ == "__main__":
    unittest.main()

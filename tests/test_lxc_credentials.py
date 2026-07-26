from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = ROOT / "infra/ansible/roles/lxc_credentials/tasks/main.yml"
ROLE_DEFAULTS = ROOT / "infra/ansible/roles/lxc_credentials/defaults/main.yml"


class LxcCredentialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = ROLE_TASKS.read_text(encoding="utf-8")
        cls.defaults = ROLE_DEFAULTS.read_text(encoding="utf-8")

    def test_root_password_comes_from_private_environment_and_is_hidden(self) -> None:
        self.assertIn("TF_VAR_lxc_root_password", self.tasks)
        self.assertIn("no_log: true", self.tasks)
        self.assertIn("password_hash('sha512', lxc_credentials_root_password_hash_salt)", self.tasks)
        self.assertIn("update_password: always", self.tasks)

    def test_hash_salt_is_stable_for_idempotent_rotation(self) -> None:
        self.assertIn("lxc_credentials_root_password_hash_salt:", self.defaults)

    def test_service_playbooks_include_lxc_credentials(self) -> None:
        for service in ("hermes", "technitium", "forgejo", "infisical", "tailscale-client"):
            playbook = ROOT / f"infra/ansible/playbooks/{service}.yml"
            text = playbook.read_text(encoding="utf-8")
            self.assertIn("role: lxc_credentials", text)
            self.assertIn("default('lxc') == 'lxc'", text)


if __name__ == "__main__":
    unittest.main()

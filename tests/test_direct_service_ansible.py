from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "scripts" / "check-direct-service-ansible.py"


class DirectServiceAnsibleHelperTests(unittest.TestCase):
    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_help_exits_zero(self) -> None:
        result = self.run_helper("--help")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inventory_maps_caddy_proxy_to_technitium(self) -> None:
        result = self.run_helper("inventory", "--settings", "settings.example.json", "--redacted")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("playbook=caddy-proxy.yml group=technitium", result.stdout)
        self.assertIn("playbook=technitium-dns.yml group=localhost", result.stdout)

    def test_bootstrap_plan_mentions_reusable_handoff(self) -> None:
        result = self.run_helper("bootstrap-plan", "--settings", "settings.example.json", "--redacted")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("direct_access_ready", result.stdout)
        self.assertIn("known_hosts", result.stdout)

    def test_proxmox_access_is_bootstrapped_before_host_tasks(self) -> None:
        playbook = (REPO / "infra" / "ansible" / "playbooks" / "proxmox-access-ready.yml").read_text(encoding="utf-8")
        self.assertIn("hosts: localhost", playbook)
        self.assertIn("hostvars['pve'].ansible_host", playbook)
        self.assertIn("proxmox_access_ready_accept_host_key_change", playbook)
        self.assertIn("Proxmox SSH host key changed", playbook)
        for name in (
            "hermes",
            "forgejo",
            "forgejo-runner",
            "technitium",
            "infisical",
            "tailscale-client",
            "caddy-proxy",
            "storage-prep",
            "guest-mount-feature-preflight",
        ):
            content = (REPO / "infra" / "ansible" / "playbooks" / f"{name}.yml").read_text(encoding="utf-8")
            self.assertIn("import_playbook: proxmox-access-ready.yml", content)

    def test_direct_access_known_hosts_fails_closed_on_unapproved_key_change(self) -> None:
        playbook = (REPO / "infra" / "ansible" / "playbooks" / "direct-access-ready.yml").read_text(encoding="utf-8")
        self.assertIn("lookup('env', 'INFRA_VALUES_DIR')", playbook)
        self.assertIn("/ansible/known_hosts", playbook)
        self.assertIn("direct_access_ready_accept_host_key_change", playbook)
        self.assertIn("SSH host key changed", playbook)
        self.assertNotIn("ssh-keygen -R {{ hostvars", playbook)

    def test_redaction_blocks_private_values(self) -> None:
        spec = importlib.util.spec_from_file_location("check_direct_service_ansible", HELPER)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert_redacted = module.assert_redacted
        with self.assertRaises(Exception):
            assert_redacted("token=super-secret-value 192.168.1.10")  # public-safety: allow-ip
        assert_redacted("service=technitium endpoint=example.internal address=192.0.2.10")


if __name__ == "__main__":
    unittest.main()

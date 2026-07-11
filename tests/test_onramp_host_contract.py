from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VARIABLES = REPO / "infra" / "opentofu" / "variables.tf"
ONRAMP_HOST_TF = REPO / "infra" / "opentofu" / "onramp-host.tf"
SCAFFOLD_TFVARS = REPO / "scaffold" / "terraform.tfvars"
ONRAMP_HOST_TASKS = REPO / "infra" / "ansible" / "roles" / "onramp_host" / "tasks" / "main.yml"


class OnrampHostContractTests(unittest.TestCase):
    def test_onramp_host_vm_is_gated_by_service_selection(self) -> None:
        text = ONRAMP_HOST_TF.read_text(encoding="utf-8")
        self.assertIn('resource "proxmox_virtual_environment_vm" "onramp_host"', text)
        self.assertRegex(text, r"count\s*=\s*local\.onramp_host_enabled \? 1 : 0")
        self.assertIn('resource "proxmox_download_file" "debian_13_onramp_host_image"', text)
        self.assertIn("import_from", text)
        self.assertIn("onramp_host_image_url", text)
        self.assertNotIn("clone {", text)
        self.assertNotIn("proxmox_virtual_environment_container", text)

    def test_onramp_host_vars_cover_boot_network_user_and_policy(self) -> None:
        text = VARIABLES.read_text(encoding="utf-8")
        for name in (
            "onramp_host_vmid",
            "onramp_host_image_url",
            "onramp_host_image_file_name",
            "onramp_host_image_checksum_algorithm",
            "onramp_host_image_checksum",
            "onramp_host_ipv4_address",
            "onramp_host_ipv4_gateway",
            "onramp_host_dns_servers",
            "onramp_host_vlan_id",
            "onramp_host_cloud_init_user",
            "onramp_host_ssh_public_keys",
            "onramp_host_deploy_user",
            "onramp_host_deploy_dir",
            "onramp_host_allowed_ssh_cidrs",
        ):
            self.assertIn(f'variable "{name}"', text)

    def test_scaffold_onramp_host_vmid_and_address_are_unique(self) -> None:
        text = SCAFFOLD_TFVARS.read_text(encoding="utf-8")
        vmids = re.findall(r"(?m)^\w+(?:_container)?_vmid\s*=\s*(\d+)", text)
        self.assertEqual(len(vmids), len(set(vmids)))
        addresses = [match.split("/", 1)[0] for match in re.findall(r'(?m)^\w+(?:_container)?_ipv4_address\s*=\s*"([^\"]+)"', text) if match != "dhcp"]
        self.assertEqual(len(addresses), len(set(addresses)))

    def test_onramp_host_role_declares_hardening_and_no_host_published_ports_contract(self) -> None:
        text = ONRAMP_HOST_TASKS.read_text(encoding="utf-8")
        self.assertIn("PasswordAuthentication", text)
        self.assertIn("PermitRootLogin", text)
        self.assertIn("default-deny onramp-host firewall", text)
        self.assertIn("Allow approved Onramp reverse-proxy ports only", text)
        self.assertIn("Rootless Podman", text)


if __name__ == "__main__":
    unittest.main()

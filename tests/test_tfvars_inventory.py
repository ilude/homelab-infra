from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "ansible" / "inventory" / "tfvars.py"
spec = importlib.util.spec_from_file_location("tfvars_inventory", SCRIPT)
assert spec and spec.loader
tfvars_inventory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tfvars_inventory
spec.loader.exec_module(tfvars_inventory)


class TfvarsInventoryTests(unittest.TestCase):
    def test_build_inventory_uses_tfvars_addresses_and_vmids(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "technitium_container_vmid": 106,
                "technitium_container_ipv4_address": "192.0.2.53/24",
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "forgejo_server_name": "git.example.internal",
                "forgejo_data_host_path": "/srv/forgejo",
                "forgejo_data_mount_path": "/var/lib/forgejo",
                "proxmox_node_name": "pve-a",
            },
            ["technitium", "forgejo"],
            pve_host="root@proxmox.example.internal",
        )

        hostvars = inventory["_meta"]["hostvars"]
        self.assertEqual(hostvars["technitium_dns"]["ansible_host"], "192.0.2.53")
        self.assertEqual(hostvars["technitium_dns"]["technitium_vmid"], 106)
        self.assertEqual(hostvars["technitium_dns"]["direct_access_vmid"], 106)
        self.assertEqual(
            hostvars["technitium_dns"]["ansible_ssh_common_args"],
            "-o UserKnownHostsFile=/tmp/homelab-infra/ansible/known_hosts "
            "-o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o ForwardAgent=no",
        )
        self.assertEqual(hostvars["forgejo_lxc"]["ansible_host"], "192.0.2.62")
        self.assertEqual(hostvars["forgejo_lxc"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(inventory["all"]["vars"]["technitium_vmid"], 106)
        self.assertEqual(inventory["all"]["vars"]["forgejo_vmid"], 107)
        self.assertEqual(inventory["all"]["vars"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(inventory["all"]["vars"]["forgejo_data_host_path"], "/srv/forgejo")
        self.assertEqual(inventory["all"]["vars"]["forgejo_data_mount_path"], "/var/lib/forgejo")
        self.assertEqual(inventory["services"]["children"], ["technitium", "forgejo"])
        self.assertEqual(inventory["pve"]["hosts"], ["pve_target"])
        self.assertEqual(hostvars["pve_target"]["ansible_host"], "proxmox.example.internal")
        self.assertEqual(hostvars["pve_target"]["ansible_user"], "root")
        self.assertEqual(inventory["all"]["vars"]["proxmox_node_name"], "pve-a")

    def test_forgejo_runner_promotes_configured_pve_node_identity(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_runner_vmid": 109,
                "forgejo_runner_ipv4_address": "192.0.2.64/24",
                "proxmox_node_name": "pve",
            },
            ["forgejo_runner"],
            pve_host="proxmox.example.internal",
        )

        self.assertEqual(inventory["pve"]["hosts"], ["pve_target"])
        self.assertEqual(inventory["_meta"]["hostvars"]["pve_target"]["proxmox_node_name"], "pve")
        self.assertEqual(inventory["all"]["vars"]["proxmox_node_name"], "pve")

    def test_dhcp_address_is_not_used_as_ansible_host(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "dhcp",
                "proxmox_node_name": "pve",
            },
            ["forgejo"],
            pve_host="proxmox.example.internal",
        )

        self.assertNotIn("ansible_host", inventory["_meta"]["hostvars"]["forgejo_lxc"])

    def test_onramp_host_uses_tfvars_address_user_and_policy_vars(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "onramp_host_vmid": 112,
                "onramp_host_ipv4_address": "192.0.2.72/24",
                "onramp_host_hostname": "onramp-host",
                "onramp_host_deploy_user": "onramp",
                "onramp_host_deploy_dir": "/srv/onramp",
                "onramp_host_password_authentication": False,
                "onramp_host_permit_root_login": False,
                "onramp_host_allowed_ssh_cidrs": ["192.0.2.0/24"],
            },
            ["onramp_host"],
        )

        hostvars = inventory["_meta"]["hostvars"]["onramp_host_vm"]
        self.assertEqual(hostvars["ansible_host"], "192.0.2.72")
        self.assertEqual(hostvars["ansible_user"], "onramp")
        self.assertTrue(hostvars["ansible_become"])
        self.assertEqual(hostvars["onramp_host_vmid"], 112)
        self.assertEqual(hostvars["onramp_host_deploy_dir"], "/srv/onramp")
        self.assertEqual(inventory["services"]["children"], ["onramp_host"])

    def test_searxng_onramp_reuses_onramp_host_and_promotes_endpoint_vars(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "onramp_host_vmid": 112,
                "onramp_host_ipv4_address": "192.0.2.72/24",
                "onramp_host_deploy_user": "onramp",
                "onramp_host_deploy_dir": "/srv/onramp",
                "searxng_server_name": "searxng.apps.example.net",
                "searxng_public_url": "https://searxng.apps.example.net",
            },
            ["onramp_host", "searxng_onramp"],
        )

        hostvars = inventory["_meta"]["hostvars"]["onramp_host_vm"]
        self.assertEqual(hostvars["ansible_host"], "192.0.2.72")
        self.assertEqual(hostvars["ansible_user"], "onramp")
        self.assertEqual(inventory["all"]["vars"]["searxng_server_name"], "searxng.apps.example.net")
        self.assertEqual(inventory["all"]["vars"]["searxng_public_url"], "https://searxng.apps.example.net")
        self.assertEqual(inventory["services"]["children"], ["onramp_host"])

    def test_tailscale_enabled_is_promoted_to_all_vars(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "tailscale_client_vmid": 108,
                "tailscale_client_ipv4_address": "192.0.2.63",
                "tailscale_client_enabled": False,
                "proxmox_node_name": "pve",
            },
            ["tailscale_client"],
            pve_host="proxmox.example.internal",
        )

        self.assertFalse(inventory["all"]["vars"]["tailscale_client_enabled"])
        self.assertEqual(inventory["all"]["vars"]["tailscale_client_vmid"], 108)

    def test_pve_workflow_rejects_missing_or_malformed_authority(self) -> None:
        tfvars = {"proxmox_node_name": "pve"}
        with mock.patch.dict("os.environ", {}, clear=True), self.assertRaises(tfvars_inventory.InventoryError):
            tfvars_inventory.build_inventory(tfvars, ["technitium"])
        for value in (
            "",
            "admin@proxmox.example.internal",
            "root@host/path",
            "https://host",
            "999.999.999.999",
            "[2001:db8::not-an-address]",
        ):
            with self.subTest(value=value), self.assertRaises(tfvars_inventory.InventoryError):
                tfvars_inventory.build_inventory(tfvars, ["technitium"], pve_host=value)

    def test_non_pve_workflow_does_not_require_pve_authority(self) -> None:
        inventory = tfvars_inventory.build_inventory({}, ["onramp_host"])

        self.assertNotIn("pve", inventory)

    def test_load_tfvars_uses_python_hcl2(self) -> None:
        fake_file = mock.mock_open(read_data='technitium_container_vmid = 106\n')
        with mock.patch("pathlib.Path.open", fake_file), mock.patch.object(
            tfvars_inventory.hcl2, "load", return_value={"technitium_container_vmid": 106}
        ) as hcl_load:
            values = tfvars_inventory.load_tfvars(Path("values/terraform.tfvars"))

        self.assertEqual(values["technitium_container_vmid"], 106)
        hcl_load.assert_called_once()


if __name__ == "__main__":
    unittest.main()

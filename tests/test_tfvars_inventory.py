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
            },
            ["technitium", "forgejo"],
        )

        hostvars = inventory["_meta"]["hostvars"]
        self.assertEqual(hostvars["technitium_dns"]["ansible_host"], "192.0.2.53")
        self.assertEqual(hostvars["technitium_dns"]["technitium_vmid"], 106)
        self.assertEqual(hostvars["forgejo_lxc"]["ansible_host"], "192.0.2.62")
        self.assertEqual(hostvars["forgejo_lxc"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(inventory["all"]["vars"]["technitium_vmid"], 106)
        self.assertEqual(inventory["all"]["vars"]["forgejo_vmid"], 107)
        self.assertEqual(inventory["all"]["vars"]["forgejo_domain"], "git.example.internal")
        self.assertEqual(inventory["services"]["children"], ["technitium", "forgejo"])
        self.assertEqual(
            inventory["all"]["vars"]["ansible_ssh_common_args"],
            "-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes",
        )

    def test_dhcp_address_is_not_used_as_ansible_host(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {"forgejo_container_vmid": 107, "forgejo_lan_ip": "dhcp"},
            ["forgejo"],
        )

        self.assertNotIn("ansible_host", inventory["_meta"]["hostvars"]["forgejo_lxc"])

    def test_disabled_service_groups_exist_without_hosts(self) -> None:
        inventory = tfvars_inventory.build_inventory({}, [])

        expected_groups = {config["group"] for config in tfvars_inventory.SERVICE_HOSTS.values()}
        self.assertEqual({group for group in inventory if group in expected_groups}, expected_groups)
        for group in expected_groups:
            with self.subTest(group=group):
                self.assertEqual(inventory[group]["hosts"], [])
        self.assertEqual(inventory["services"]["children"], [])
        self.assertEqual(inventory["_meta"]["hostvars"], {})

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

    def test_forgejo_vm_uses_cloud_init_user_when_runtime_is_vm(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "service_runtime": {"forgejo": {"type": "vm"}},
                "forgejo_vm_cloud_init_user": "forgejo-admin",
            },
            ["forgejo"],
        )

        hostvars = inventory["_meta"]["hostvars"]["forgejo_lxc"]
        self.assertEqual(hostvars["ansible_user"], "forgejo-admin")
        self.assertTrue(hostvars["ansible_become"])

    def test_service_vm_uses_runtime_cloud_init_user(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "hermes_container_vmid": 111,
                "hermes_lan_ip": "192.0.2.71",
                "service_runtime": {"hermes": {"type": "vm", "cloud_init_user": "hermes-admin"}},
            },
            ["hermes"],
        )

        hostvars = inventory["_meta"]["hostvars"]["hermes_lxc"]
        self.assertEqual(hostvars["ansible_user"], "hermes-admin")
        self.assertTrue(hostvars["ansible_become"])
        self.assertEqual(hostvars["hermes_runtime"], {"type": "vm", "cloud_init_user": "hermes-admin"})

    def test_forgejo_lxc_ignores_vm_cloud_init_user(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "forgejo_runtime": {"type": "lxc"},
                "forgejo_vm_cloud_init_user": "forgejo-admin",
            },
            ["forgejo"],
        )

        hostvars = inventory["_meta"]["hostvars"]["forgejo_lxc"]
        self.assertEqual(hostvars["ansible_user"], "root")
        self.assertNotIn("ansible_become", hostvars)

    def test_service_runtime_is_promoted_to_service_play_vars(self) -> None:
        runtime = {"type": "vm"}
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "service_runtime": {"forgejo": runtime},
            },
            ["forgejo"],
        )

        self.assertEqual(inventory["all"]["vars"]["forgejo_runtime"], runtime)
        self.assertEqual(inventory["_meta"]["hostvars"]["forgejo_lxc"]["forgejo_runtime"], runtime)

    def test_legacy_forgejo_runtime_is_promoted_to_service_play_vars(self) -> None:
        runtime = {"type": "vm"}
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "forgejo_runtime": runtime,
            },
            ["forgejo"],
        )

        self.assertEqual(inventory["all"]["vars"]["forgejo_runtime"], runtime)
        self.assertEqual(inventory["_meta"]["hostvars"]["forgejo_lxc"]["forgejo_runtime"], runtime)

    def test_forgejo_database_is_promoted_to_play_vars(self) -> None:
        database = {"type": "postgres", "managed": True, "name": "forgejo", "user": "forgejo"}
        inventory = tfvars_inventory.build_inventory(
            {
                "forgejo_container_vmid": 107,
                "forgejo_lan_ip": "192.0.2.62",
                "forgejo_database": database,
            },
            ["forgejo"],
        )

        self.assertEqual(inventory["all"]["vars"]["forgejo_database"], database)
        self.assertEqual(inventory["_meta"]["hostvars"]["forgejo_lxc"]["forgejo_database"], database)

    def test_tailscale_enabled_is_promoted_to_all_vars(self) -> None:
        inventory = tfvars_inventory.build_inventory(
            {
                "tailscale_client_vmid": 108,
                "tailscale_client_ipv4_address": "192.0.2.63",
                "tailscale_client_enabled": False,
            },
            ["tailscale_client"],
        )

        self.assertFalse(inventory["all"]["vars"]["tailscale_client_enabled"])
        self.assertEqual(inventory["all"]["vars"]["tailscale_client_vmid"], 108)

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

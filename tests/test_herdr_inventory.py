from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
TFVARS_INVENTORY = REPO / "infra" / "ansible" / "inventory" / "tfvars.py"
FIXTURE = REPO / "tests" / "fixtures" / "site-config" / "terraform.tfvars"
SERVICE_REGISTRY = REPO / "infra" / "services.json"

spec = importlib.util.spec_from_file_location("tfvars_inventory", TFVARS_INVENTORY)
assert spec and spec.loader
tfvars_inventory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tfvars_inventory
spec.loader.exec_module(tfvars_inventory)


class HerdrInventoryTests(unittest.TestCase):
    def test_registry_contract_and_dynamic_inventory(self) -> None:
        registry = json.loads(SERVICE_REGISTRY.read_text(encoding="utf-8"))
        services = registry["services"]
        herdr = services["herdr"]

        self.assertEqual(herdr["dependencies"], ["onramp_host"])
        self.assertEqual(herdr["execution_resource"], "direct_lxc_known_hosts")
        self.assertFalse(herdr["state_capable"])
        self.assertEqual(herdr["terraform_module"], "herdr")
        self.assertNotIn("terraform_target", herdr)
        self.assertEqual(herdr["playbooks"], ["infra/ansible/playbooks/herdr.yml"])
        self.assertEqual(
            herdr["inventory"],
            {
                "host": "herdr_lxc",
                "group": "herdr",
                "vmid_var": "herdr_vmid",
                "tf_vmid": "herdr_container_vmid",
                "tf_host": "herdr_lan_ip",
                "user_var": "herdr_operator_user",
                "tf_user": "herdr_operator_user",
                "extra_play_vars": {
                    "herdr_operator_user": "herdr_operator_user",
                    "herdr_ssh_public_keys": "lxc_ssh_public_keys",
                    "herdr_password_authentication": "herdr_password_authentication",
                    "herdr_permit_root_login": "herdr_permit_root_login",
                    "herdr_allowed_ssh_cidrs": "herdr_allowed_ssh_cidrs",
                },
            },
        )

        searxng = services["searxng_onramp"]
        self.assertEqual(searxng["dependencies"], ["onramp_host"])
        self.assertEqual(searxng["execution_resource"], "onramp_host")
        self.assertTrue(searxng["state_capable"])
        self.assertEqual(
            searxng["playbooks"], ["infra/ansible/playbooks/searxng-onramp.yml"]
        )
        self.assertEqual(
            {
                key: searxng["inventory"][key]
                for key in ("host", "group", "tf_vmid", "tf_host", "tf_user")
            },
            {
                "host": "onramp_host_vm",
                "group": "onramp_host",
                "tf_vmid": "onramp_host_vmid",
                "tf_host": "onramp_host_ipv4_address",
                "tf_user": "onramp_host_deploy_user",
            },
        )
        self.assertEqual(
            searxng["terraform_target"], "proxmox_virtual_environment_vm.onramp_host"
        )

        tfvars = tfvars_inventory.load_tfvars(FIXTURE)
        inventory = tfvars_inventory.build_inventory(
            tfvars,
            ["onramp_host", "herdr", "searxng_onramp"],
            pve_host="proxmox.example.internal",
        )
        hostvars = inventory["_meta"]["hostvars"]
        herdr_host = hostvars["herdr_lxc"]
        all_vars = inventory["all"]["vars"]

        self.assertEqual(inventory["herdr"]["hosts"], ["herdr_lxc"])
        self.assertIn("herdr", inventory["services"]["children"])
        self.assertEqual(herdr_host["ansible_user"], "herdr")
        self.assertTrue(herdr_host["ansible_become"])
        self.assertEqual(herdr_host["ansible_host"], "192.0.2.73")
        self.assertEqual(herdr_host["herdr_vmid"], 113)
        self.assertEqual(herdr_host["direct_access_vmid"], 113)
        self.assertEqual(herdr_host["direct_access_pve_host"], "pve_target")

        expected_ssh_args = (
            "-o UserKnownHostsFile=/tmp/homelab-infra/ansible/known_hosts "
            "-o GlobalKnownHostsFile=/dev/null "
            "-o StrictHostKeyChecking=yes -o ForwardAgent=no"
        )
        self.assertEqual(herdr_host["ansible_ssh_common_args"], expected_ssh_args)
        self.assertIn(
            "UserKnownHostsFile=/tmp/homelab-infra/ansible/known_hosts",
            expected_ssh_args,
        )
        self.assertIn("GlobalKnownHostsFile=/dev/null", expected_ssh_args)
        self.assertIn("StrictHostKeyChecking=yes", expected_ssh_args)
        self.assertIn("ForwardAgent=no", expected_ssh_args)

        expected_keys = tfvars["lxc_ssh_public_keys"]
        for key, value in {
            "herdr_operator_user": "herdr",
            "herdr_ssh_public_keys": expected_keys,
            "herdr_password_authentication": False,
            "herdr_permit_root_login": False,
            "herdr_allowed_ssh_cidrs": ["192.0.2.0/24"],
        }.items():
            with self.subTest(variable=key):
                self.assertEqual(herdr_host[key], value)
                self.assertEqual(all_vars[key], value)

        self.assertEqual(inventory["pve"]["hosts"], ["pve_target"])
        self.assertEqual(
            hostvars["pve_target"]["ansible_host"], "proxmox.example.internal"
        )
        self.assertEqual(hostvars["pve_target"]["ansible_user"], "root")
        self.assertEqual(all_vars["proxmox_node_name"], "pve")

        for key in (
            "searxng_server_name",
            "searxng_public_url",
            "searxng_container_image",
            "searxng_container_port",
            "searxng_bind_address",
            "searxng_instance_name",
            "searxng_enable_public_url",
        ):
            with self.subTest(variable=key):
                self.assertEqual(all_vars[key], tfvars[key])


if __name__ == "__main__":
    unittest.main()

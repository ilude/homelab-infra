from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

SETTINGS = REPO / "scripts" / "settings.py"
settings_spec = importlib.util.spec_from_file_location("settings_script", SETTINGS)
assert settings_spec and settings_spec.loader
settings_script = importlib.util.module_from_spec(settings_spec)
settings_spec.loader.exec_module(settings_script)

try:
    import hcl2  # noqa: F401
except ImportError:
    if "hcl2" not in sys.modules:
        hcl2_stub = types.ModuleType("hcl2")
        hcl2_stub.load = lambda _file: {}
        sys.modules["hcl2"] = hcl2_stub

TFVARS_INVENTORY = REPO / "infra" / "ansible" / "inventory" / "tfvars.py"
tfvars_spec = importlib.util.spec_from_file_location("tfvars_inventory", TFVARS_INVENTORY)
assert tfvars_spec and tfvars_spec.loader
tfvars_inventory = importlib.util.module_from_spec(tfvars_spec)
sys.modules[tfvars_spec.name] = tfvars_inventory
tfvars_spec.loader.exec_module(tfvars_inventory)

SERVICE_REGISTRY = REPO / "infra" / "services.json"
service_registry = json.loads(SERVICE_REGISTRY.read_text(encoding="utf-8"))


class ServiceRegistryParityTests(unittest.TestCase):
    def test_settings_services_are_derived_from_registry(self) -> None:
        expected_services = {
            name: {
                "playbooks": tuple(config["playbooks"]),
                "dependencies": tuple(config["dependencies"]),
                "conflicts": tuple(config.get("conflicts", [])),
                "execution_resource": str(config.get("execution_resource", name)),
                "terraform_module": config.get("terraform_module"),
            }
            for name, config in service_registry["services"].items()
        }
        self.assertEqual(tuple(service_registry["default_services"]), settings_script.DEFAULT_SERVICES)
        self.assertEqual(expected_services, settings_script.SERVICES)
        self.assertEqual(set(service_registry["services"]), settings_script.SERVICE_NAMES)

    def test_state_capability_metadata_matches_service_state_catalog(self) -> None:
        self.assertTrue(
            all(isinstance(config.get("state_capable"), bool) for config in service_registry["services"].values())
        )
        state_capable = [
            (name, config)
            for name, config in service_registry["services"].items()
            if config["state_capable"]
        ]
        orders = [config["state_order"] for _, config in state_capable]
        self.assertTrue(all(isinstance(order, int) and order > 0 for order in orders))
        self.assertEqual(len(orders), len(set(orders)))
        catalog = yaml.safe_load(
            (REPO / "infra" / "ansible" / "vars" / "service-state.yml").read_text(encoding="utf-8")
        )["managed_service_state_catalog"]
        state_capable_services = {
            name
            for name, config in service_registry["services"].items()
            if config["state_capable"]
        }
        self.assertEqual(state_capable_services, set(catalog))

    def test_inventory_service_hosts_are_derived_from_registry(self) -> None:
        expected_hosts = {
            name: config["inventory"]
            for name, config in service_registry["services"].items()
        }
        self.assertEqual(expected_hosts, tfvars_inventory.SERVICE_HOSTS)

    def test_opentofu_enabled_services_validation_reads_registry(self) -> None:
        variables = (REPO / "infra" / "opentofu" / "variables.tf").read_text(encoding="utf-8")
        services = (REPO / "infra" / "opentofu" / "services.tf").read_text(encoding="utf-8")
        self.assertIn('jsondecode(file("${path.module}/../services.json"))', services)
        self.assertIn('resource "terraform_data" "enabled_services_validation"', services)
        self.assertIn("invalid_enabled_services", services)
        self.assertNotIn('contains(["technitium"', variables)

    def test_settings_playbook_paths_exist(self) -> None:
        for playbook in settings_script.all_ansible_playbooks():
            self.assertTrue((REPO / playbook).is_file(), playbook)

    def test_direct_service_playbook_target_groups_are_known(self) -> None:
        special = {
            "infra/ansible/playbooks/caddy-proxy.yml": "technitium",
            "infra/ansible/playbooks/technitium-dns.yml": "localhost",
        }
        groups = {service: config["group"] for service, config in tfvars_inventory.SERVICE_HOSTS.items()}
        for service, config in settings_script.SERVICES.items():
            for playbook in config["playbooks"]:
                group = special.get(playbook, groups[service])
                self.assertTrue(group == "localhost" or group in groups.values(), playbook)
        self.assertEqual(special["infra/ansible/playbooks/caddy-proxy.yml"], "technitium")


if __name__ == "__main__":
    unittest.main()

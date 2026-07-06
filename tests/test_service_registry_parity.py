from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SETTINGS = REPO / "scripts" / "settings.py"
settings_spec = importlib.util.spec_from_file_location("settings_script", SETTINGS)
assert settings_spec and settings_spec.loader
settings_script = importlib.util.module_from_spec(settings_spec)
settings_spec.loader.exec_module(settings_script)

TFVARS_INVENTORY = REPO / "infra" / "ansible" / "inventory" / "tfvars.py"
tfvars_spec = importlib.util.spec_from_file_location("tfvars_inventory", TFVARS_INVENTORY)
assert tfvars_spec and tfvars_spec.loader
tfvars_inventory = importlib.util.module_from_spec(tfvars_spec)
sys.modules[tfvars_spec.name] = tfvars_inventory
tfvars_spec.loader.exec_module(tfvars_inventory)


class ServiceRegistryParityTests(unittest.TestCase):
    def test_settings_services_match_opentofu_enabled_services_validation(self) -> None:
        variables = (REPO / "infra" / "opentofu" / "variables.tf").read_text(encoding="utf-8")
        match = re.search(r"contains\(\[(?P<services>.*?)\], service\)", variables, re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        tofu_services = set(re.findall(r'"([A-Za-z0-9_]+)"', match.group("services")))
        self.assertEqual(set(settings_script.SERVICES), tofu_services)

    def test_settings_services_match_inventory_service_hosts(self) -> None:
        self.assertEqual(set(settings_script.SERVICES), set(tfvars_inventory.SERVICE_HOSTS))

    def test_settings_playbook_paths_exist(self) -> None:
        for playbook in settings_script.all_ansible_playbooks():
            self.assertTrue((REPO / playbook).is_file(), playbook)


if __name__ == "__main__":
    unittest.main()

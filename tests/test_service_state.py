from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "infra" / "ansible" / "vars" / "service-state.yml"
SERVICES = ROOT / "infra" / "services.json"
BACKUP = ROOT / "infra" / "ansible" / "playbooks" / "service-state-backup.yml"
RESTORE = ROOT / "infra" / "ansible" / "playbooks" / "service-state-restore.yml"
ONRAMP_DEFAULTS = ROOT / "infra" / "ansible" / "roles" / "onramp_host" / "defaults" / "main.yml"
COMPOSE = ROOT / "compose.yaml"
SERVICE_STATE_CLI = ROOT / "scripts" / "service-state.sh"


class ServiceStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["managed_service_state_catalog"]

    def test_stateful_services_have_catalog_entries(self) -> None:
        import json

        registry = json.loads(SERVICES.read_text(encoding="utf-8"))
        missing = [name for name, config in registry["services"].items() if config.get("state_capable") and name not in self.catalog]
        self.assertEqual(missing, [])

    def test_legacy_infisical_state_includes_application_data(self) -> None:
        definition = self.catalog["infisical"]
        self.assertIn("/etc/infisical", definition["paths"])
        self.assertIn("infisical_data_dir", "\n".join(definition["paths"]))

    def test_hermes_backup_includes_gateway_and_dashboard(self) -> None:
        self.assertEqual(
            self.catalog["hermes"]["services"],
            ["hermes-gateway", "hermes-dashboard"],
        )

    def test_forgejo_postgres_backup_and_restore_are_managed(self) -> None:
        backup = BACKUP.read_text(encoding="utf-8")
        restore = RESTORE.read_text(encoding="utf-8")
        self.assertIn("pg_dump", backup)
        self.assertIn("forgejo-postgres.dump", backup)
        self.assertIn("pg_restore", restore)
        self.assertIn("forgejo-postgres.dump", restore)

    def test_restore_uses_selected_site_root_and_local_preflight(self) -> None:
        restore = RESTORE.read_text(encoding="utf-8")
        self.assertIn("service_state_backup_root | regex_escape", restore)
        self.assertIn("delegate_to: localhost", restore)

    def test_onramp_recovery_dependencies_and_container_paths_are_wired(self) -> None:
        defaults = yaml.safe_load(ONRAMP_DEFAULTS.read_text(encoding="utf-8"))
        compose = COMPOSE.read_text(encoding="utf-8")
        cli = SERVICE_STATE_CLI.read_text(encoding="utf-8")

        self.assertIn("rsync", defaults["onramp_host_podman_packages"])
        self.assertIn("SERVICE_STATE_BACKUP_ROOT: ${SERVICE_STATE_BACKUP_ROOT:-}", compose)
        self.assertIn("SERVICE_STATE_RESTORE_FILE: ${SERVICE_STATE_RESTORE_FILE:-}", compose)
        self.assertIn('msys_env_conv_excl+="SERVICE_STATE_BACKUP_ROOT;SERVICE_STATE_RESTORE_FILE"', cli)


if __name__ == "__main__":
    unittest.main()

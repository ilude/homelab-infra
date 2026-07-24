from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "migrate_site_values", ROOT / "scripts" / "migrate-site-values.py"
)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class SiteMigrationTests(unittest.TestCase):
    def make_legacy_values(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        (values / "ansible" / "inventory").mkdir(parents=True)
        (values / ".env").write_text("PVE_HOST=proxmox.example.internal\n", encoding="utf-8")
        (values / "terraform.tfvars").write_text("x = 1\n", encoding="utf-8")
        (values / "dns-records.local.json").write_text("{}\n", encoding="utf-8")
        (values / "ansible" / "inventory" / "local.yml").write_text("---\n", encoding="utf-8")
        (root / "settings.local.json").write_text(
            json.dumps({"values_repo": {"remote": ""}, "services": ["hermes"]}),
            encoding="utf-8",
        )
        return temp, values

    def test_dry_run_does_not_mutate_legacy_values(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            actions = migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, False)
            self.assertTrue(any(action.startswith("move ") for action in actions))
            self.assertFalse((values / "sites" / "dev").exists())
            self.assertIn('"services"', (values.parent / "settings.local.json").read_text())

    def test_apply_moves_files_and_site_services(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)
            site = values / "sites" / "dev"
            self.assertEqual(json.loads((site / "site.json").read_text())["services"], ["hermes"])
            self.assertTrue((site / "terraform.tfvars").is_file())
            self.assertFalse((values / "terraform.tfvars").exists())
            self.assertNotIn("services", json.loads((values.parent / "settings.local.json").read_text()))

    def test_existing_site_is_never_overwritten(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            (values / "sites" / "dev").mkdir(parents=True)
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)


if __name__ == "__main__":
    unittest.main()

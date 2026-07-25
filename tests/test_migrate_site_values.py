from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
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

    def test_interrupted_move_is_rolled_back(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            original_settings = (values.parent / "settings.local.json").read_bytes()
            original_move = migration.shutil.move
            calls = 0

            def fail_on_second_move(source: str, destination: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated move failure")
                original_move(source, destination)

            with patch.object(migration.shutil, "move", side_effect=fail_on_second_move):
                with self.assertRaises(migration.SiteMigrationError):
                    migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)
            self.assertFalse((values / "sites" / "dev").exists())
            self.assertTrue((values / "terraform.tfvars").is_file())
            self.assertEqual((values.parent / "settings.local.json").read_bytes(), original_settings)

    def test_site_identifier_rejects_path_traversal(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, values.parent, "../prod", "production", "persistent", True, False, False)

    def test_existing_site_is_never_overwritten(self) -> None:
        temp, values = self.make_legacy_values()
        with temp:
            (values / "sites" / "dev").mkdir(parents=True)
            with self.assertRaises(migration.SiteMigrationError):
                migration.migrate(values, values.parent, "dev", "development", "disposable", True, True, True)


if __name__ == "__main__":
    unittest.main()

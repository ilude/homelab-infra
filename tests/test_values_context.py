from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


values_context = load_module("values_context", ROOT / "scripts" / "values_context.py")
sys.modules["values_context"] = values_context
settings = load_module("settings", ROOT / "scripts" / "settings.py")


class ValuesContextTests(unittest.TestCase):
    def test_legacy_values_root_remains_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            with patch.dict(os.environ, {}, clear=True):
                context = values_context.from_environment(repo)
            self.assertEqual(context.values_dir, repo / "values")
            self.assertIsNone(context.site)
            self.assertEqual(context.path("terraform.tfvars"), repo / "values" / "terraform.tfvars")

    def test_selected_site_resolves_under_sites_without_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            site = repo / "values" / "sites" / "dev"
            site.mkdir(parents=True)
            with patch.dict(os.environ, {"VALUES_SITE": "dev"}, clear=True):
                context = values_context.from_environment(repo)
            self.assertEqual(context.values_dir, site)
            with self.assertRaises(values_context.ValuesContextError):
                context.path("../prod/terraform.tfvars")

    def test_unknown_site_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"VALUES_SITE": "missing"}, clear=True):
                with self.assertRaises(values_context.ValuesContextError):
                    values_context.from_environment(Path(temp))

    def test_site_metadata_must_match_selected_site(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            site = repo / "values" / "sites" / "dev"
            site.mkdir(parents=True)
            (site / "site.json").write_text(json.dumps({"name": "prod"}), encoding="utf-8")
            with patch.dict(os.environ, {"VALUES_SITE": "dev"}, clear=True):
                context = values_context.from_environment(repo)
                with self.assertRaises(values_context.ValuesContextError):
                    values_context.load_metadata(context)


class SiteSettingsTests(unittest.TestCase):
    def test_site_policy_controls_apply_and_destroy(self) -> None:
        settings_data = {
            "site": "dev",
            "site_metadata": {"allow_apply": True, "allow_destroy": True},
        }
        settings.ensure_site_action_allowed(settings_data, "apply")
        settings.ensure_site_action_allowed(settings_data, "destroy")
        settings_data["site_metadata"]["allow_destroy"] = False
        with self.assertRaises(settings.SettingsError):
            settings.ensure_site_action_allowed(settings_data, "destroy")

    def test_dev_site_requires_disposable_development_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            site = repo / "values" / "sites" / "dev"
            site.mkdir(parents=True)
            site_settings = site / "site.json"
            site_settings.write_text(
                json.dumps({"name": "dev", "class": "production", "lifecycle": "persistent", "allow_apply": True, "allow_destroy": False, "services": ["hermes"]}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"VALUES_DIR": str(repo / "values"), "VALUES_SITE": "dev"}, clear=True):
                with self.assertRaises(settings.SettingsError):
                    settings.load_settings(site_settings)

    def test_site_settings_supply_services_while_root_supplies_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            site = repo / "values" / "sites" / "dev"
            site.mkdir(parents=True)
            (repo / "settings.local.json").write_text(
                json.dumps({"values_repo": {"remote": "ssh://private.example/values"}}),
                encoding="utf-8",
            )
            site_settings = site / "site.json"
            site_settings.write_text(
                json.dumps({"name": "dev", "class": "development", "lifecycle": "disposable", "allow_apply": True, "allow_destroy": True, "services": ["hermes"]}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"VALUES_DIR": str(repo / "values"), "VALUES_SITE": "dev"}, clear=True):
                with patch.object(settings, "DEFAULT_SETTINGS", repo / "settings.local.json"):
                    loaded = settings.load_settings(site_settings)
            self.assertEqual(loaded["services"], ["hermes"])
            self.assertEqual(loaded["values_repo"]["remote"], "ssh://private.example/values")
            self.assertEqual(loaded["site_metadata"]["class"], "development")


if __name__ == "__main__":
    unittest.main()

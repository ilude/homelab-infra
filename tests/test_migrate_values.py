from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate-values.py"
spec = importlib.util.spec_from_file_location("migrate_values", SCRIPT)
assert spec and spec.loader
migrate_values = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migrate_values
spec.loader.exec_module(migrate_values)


class MigrateValuesTests(unittest.TestCase):
    def make_values(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        inventory = values / "ansible" / "inventory"
        inventory.mkdir(parents=True)
        (inventory / "local.yml").write_text(
            "all:\n"
            "  vars:\n"
            "    forgejo_domain: git.example.internal\n"
            "    forgejo_version: \"12.0.4\"\n"
            "    caddy_server_name: dns.example.internal\n",
            encoding="utf-8",
        )
        return temp, values

    def test_migrates_technitium_values_from_old_locations(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TF_VAR_technitium_api_token='REPLACE_SECRET'\n"
                "export SERVER_NAME='dns.example.internal'\n"
                "export FORGEJO_SERVER_NAME='git.example.internal'\n"
                "export FORGEJO_UPSTREAM='192.0.2.10:3000'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text(
                'technitium_api_url = "http://192.0.2.53:5380/api"\n'
                'dns_records_file = "../../values/dns-records.local.json"\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            env_text = (values / ".env").read_text(encoding="utf-8")
            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn("TECHNITIUM_API_TOKEN=REPLACE_SECRET", env_text)
            self.assertIn("TECHNITIUM_API_URL=http://192.0.2.53:5380/api", env_text)
            self.assertIn("DNS_RECORDS_FILE=values/dns-records.local.json", env_text)
            self.assertNotIn("TF_VAR_technitium_api_token", env_text)
            self.assertNotIn("SERVER_NAME", env_text)
            self.assertNotIn("FORGEJO_SERVER_NAME", env_text)
            self.assertNotIn("FORGEJO_UPSTREAM", env_text)
            self.assertNotIn("technitium_api_url", tfvars_text)
            self.assertNotIn("dns_records_file", tfvars_text)
            self.assertTrue(changes)

    def test_conflicting_token_names_fail(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TF_VAR_technitium_api_token='REPLACE_OLD'\n"
                "export TECHNITIUM_API_TOKEN='REPLACE_NEW'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            with self.assertRaises(migrate_values.MigrationError):
                migrate_values.migrate(values)

    def test_idempotent_after_first_run(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TECHNITIUM_API_TOKEN='REPLACE_SECRET'\n"
                "export TECHNITIUM_API_URL='http://192.0.2.53:5380/api'\n"
                "export DNS_RECORDS_FILE='values/dns-records.local.json'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            self.assertEqual(migrate_values.migrate(values), [])


if __name__ == "__main__":
    unittest.main()

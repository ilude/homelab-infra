from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import-menos-values.py"
spec = importlib.util.spec_from_file_location("import_menos_values", SCRIPT)
assert spec and spec.loader
import_menos_values = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_menos_values)


class ImportMenosValuesTests(unittest.TestCase):
    def test_imports_mapped_values_and_public_keys_without_printing_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = root / "values"
            inventory = values / "ansible" / "inventory"
            inventory.mkdir(parents=True)
            (values / ".env").write_text("export EXISTING=value\n", encoding="utf-8")
            (inventory / "local.yml").write_text(
                "---\nall:\n  vars:\n    menos_authorized_keys: []\n",
                encoding="utf-8",
            )
            source = root / "legacy.env"
            source.write_text(
                "\n".join(
                    f"{key}=value-{index}"
                    for index, key in enumerate(import_menos_values.ENV_MAPPING.values())
                )
                + "\n",
                encoding="utf-8",
            )
            keys = root / "authorized_keys"
            keys.write_text(
                "# ignored\n"
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestMaterial test@example\n",
                encoding="utf-8",
            )

            changed, key_count = import_menos_values.import_values(source, keys, values)

            self.assertEqual(changed, len(import_menos_values.ENV_MAPPING))
            self.assertEqual(key_count, 1)
            env_text = (values / ".env").read_text(encoding="utf-8")
            for key in import_menos_values.ENV_MAPPING:
                self.assertIn(f"export {key}=", env_text)
            inventory_text = (inventory / "local.yml").read_text(encoding="utf-8")
            self.assertIn("menos_authorized_keys:\n", inventory_text)
            self.assertIn("ssh-ed25519", inventory_text)
            self.assertNotIn("menos_authorized_keys: []", inventory_text)

    def test_rejects_missing_source_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = root / "values"
            inventory = values / "ansible" / "inventory"
            inventory.mkdir(parents=True)
            (values / ".env").write_text("", encoding="utf-8")
            (inventory / "local.yml").write_text(
                "---\nall:\n  vars:\n    menos_authorized_keys: []\n",
                encoding="utf-8",
            )
            source = root / "legacy.env"
            source.write_text("SURREALDB_PASSWORD=value\n", encoding="utf-8")
            keys = root / "authorized_keys"
            keys.write_text(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestMaterial test@example\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing required keys"):
                import_menos_values.import_values(source, keys, values)


if __name__ == "__main__":
    unittest.main()

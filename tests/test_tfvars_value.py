from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tfvars-value.py"
spec = importlib.util.spec_from_file_location("tfvars_value", SCRIPT)
assert spec and spec.loader
tfvars_value = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tfvars_value
spec.loader.exec_module(tfvars_value)


class TfvarsValueTests(unittest.TestCase):
    def test_reads_quoted_scalar(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write('technitium_api_url = "https://dns.example.internal/api"\n')
            path = Path(handle.name)
        try:
            self.assertEqual(
                tfvars_value.load_value(path, "technitium_api_url"),
                "https://dns.example.internal/api",
            )
        finally:
            path.unlink()

    def test_missing_key_fails(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write('other = "value"\n')
            path = Path(handle.name)
        try:
            with self.assertRaises(tfvars_value.TfvarsError):
                tfvars_value.load_value(path, "technitium_api_url")
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()

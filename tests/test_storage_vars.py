from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storage-vars.py"
spec = importlib.util.spec_from_file_location("storage_vars", SCRIPT)
assert spec and spec.loader
storage_vars = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = storage_vars
spec.loader.exec_module(storage_vars)


class StorageVarsTests(unittest.TestCase):
    def test_builds_enabled_storage_dataset_vars(self) -> None:
        tfvars = {
            "forgejo_data_dataset": "tank/forgejo",
            "forgejo_data_host_path": "/tank/forgejo",
            "forgejo_data_host_uid": 100000,
            "forgejo_data_host_gid": 100000,
            "infisical_data_dataset": "tank/infisical",
            "infisical_data_host_path": "/tank/infisical",
            "infisical_data_host_uid": 100000,
            "infisical_data_host_gid": 100000,
        }

        datasets = storage_vars.build_storage_datasets(["technitium", "forgejo"], tfvars)

        self.assertEqual(
            datasets,
            [
                {
                    "name": "forgejo",
                    "dataset": "tank/forgejo",
                    "mountpoint": "/tank/forgejo",
                    "uid": 100000,
                    "gid": 100000,
                }
            ],
        )

    def test_selected_services_limits_storage_scope(self) -> None:
        self.assertEqual(storage_vars.selected_services(["forgejo", "hermes"], ["hermes"]), ["hermes"])
        with self.assertRaisesRegex(storage_vars.StorageVarsError, "not enabled"):
            storage_vars.selected_services(["forgejo"], ["hermes"])
        with self.assertRaisesRegex(storage_vars.StorageVarsError, "duplicates"):
            storage_vars.selected_services(["forgejo"], ["forgejo", "forgejo"])

    def test_format_storage_summary_outputs_none(self) -> None:
        self.assertEqual(storage_vars.format_storage_summary([]), "Storage prep summary:\n  none")

    def test_format_storage_summary_outputs_datasets(self) -> None:
        text = storage_vars.format_storage_summary(
            [{"name": "forgejo", "dataset": "tank/forgejo", "mountpoint": "/tank/forgejo", "uid": 100000, "gid": 100000}]
        )
        self.assertIn("forgejo", text)
        self.assertIn("dataset=tank/forgejo", text)

    def test_main_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["forgejo"]}\n', encoding="utf-8")
            tfvars_path.write_text(
                'forgejo_data_dataset = "tank/forgejo"\n'
                'forgejo_data_host_path = "/tank/forgejo"\n'
                'forgejo_data_host_uid = 100000\n'
                'forgejo_data_host_gid = 100000\n',
                encoding="utf-8",
            )

            import contextlib
            import io

            output: list[str] = []
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--settings", str(settings_path), "--tfvars", str(tfvars_path)])

            self.assertEqual(rc, 0)
            output.append(buffer.getvalue())
            payload = json.loads(output[0])
            self.assertEqual(payload["storage_datasets"][0]["dataset"], "tank/forgejo")

    def test_main_outputs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["technitium"]}\n', encoding="utf-8")
            tfvars_path.write_text("", encoding="utf-8")

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(["--settings", str(settings_path), "--tfvars", str(tfvars_path), "--summary"])

            self.assertEqual(rc, 0)
            self.assertIn("Storage prep summary:", buffer.getvalue())

    def test_main_filters_storage_summary_to_requested_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            tfvars_path = root / "terraform.tfvars"
            settings_path.write_text('{"services":["forgejo","hermes"]}\n', encoding="utf-8")
            tfvars_path.write_text(
                'forgejo_data_dataset = "tank/forgejo"\n'
                'forgejo_data_host_path = "/tank/forgejo"\n',
                encoding="utf-8",
            )

            import contextlib
            import io

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = storage_vars.main(
                    ["--settings", str(settings_path), "--tfvars", str(tfvars_path), "--service", "hermes", "--summary"]
                )

            self.assertEqual(rc, 0)
            self.assertEqual(buffer.getvalue().strip(), "Storage prep summary:\n  none")


if __name__ == "__main__":
    unittest.main()

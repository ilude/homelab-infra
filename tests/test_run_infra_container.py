from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-infra-container.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_infra_container_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunInfraContainerTests(unittest.TestCase):
    def test_allows_writeback_only_for_update_command(self) -> None:
        module = load_script()

        self.assertTrue(
            module.is_allowed_writeback_command(["python", "scripts/update.py"])
        )
        self.assertTrue(
            module.is_allowed_writeback_command(
                ["python", "scripts/update.py", "caddy", "hermes"]
            )
        )
        self.assertFalse(module.is_allowed_writeback_command(["true"]))
        self.assertFalse(
            module.is_allowed_writeback_command(
                ["python", "scripts/update.py", "--root", "/tmp"]
            )
        )

    def test_rejects_writeback_options_before_rendering(self) -> None:
        module = load_script()

        with mock.patch.object(module.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as context:
                module.main(
                    [
                        "--settings",
                        "settings.local.json",
                        "--writeback-update",
                        "--",
                        "python",
                        "scripts/update.py",
                        "--root",
                        "/tmp",
                    ]
                )

        self.assertEqual(context.exception.code, 2)
        run.assert_not_called()

    def test_rejects_writeback_before_rendering_an_arbitrary_command(self) -> None:
        module = load_script()

        with mock.patch.object(module.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as context:
                module.main(
                    [
                        "--settings",
                        "settings.local.json",
                        "--writeback-update",
                        "--",
                        "true",
                    ]
                )

        self.assertEqual(context.exception.code, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "ansible" / "scripts" / "service-state-capacity-preflight.py"
spec = importlib.util.spec_from_file_location("service_state_capacity", SCRIPT)
assert spec and spec.loader
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class CapacityPreflightTests(unittest.TestCase):
    def test_formula_reserves_archive_state_snapshot_and_margin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state"
            state.mkdir()
            (state / "data").write_bytes(b"x" * 4096)
            with patch.object(capacity, "filesystem_key", return_value=(1, root, 10**9)):
                result = capacity.preflight(100, root, [state], reserve_bytes=50)
            self.assertEqual(len(result), 1)
            self.assertGreaterEqual(result[0]["required_bytes"], 150)
            self.assertTrue(result[0]["ok"])

    def test_capacity_is_grouped_by_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()

            def filesystem(path: Path) -> tuple[int, Path, int]:
                return (1 if path == root else 2, path, 1000)

            with patch.object(capacity, "filesystem_key", side_effect=filesystem):
                with patch.object(capacity, "allocated_bytes", return_value=100):
                    result = capacity.preflight(50, root, [first, second], reserve_bytes=10)
            self.assertEqual({entry["filesystem"] for entry in result}, {str(root), str(first)})
            self.assertTrue(all(entry["ok"] for entry in result))

    def test_insufficient_capacity_reports_deficit_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(capacity, "filesystem_key", return_value=(1, root, 1)):
                result = capacity.preflight(100, root, [], reserve_bytes=50)
            self.assertFalse(result[0]["ok"])
            self.assertEqual(result[0]["deficit_bytes"], 149)

    def test_negative_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            capacity.preflight(-1, Path("/tmp"), [])

    def test_restore_playbook_preflights_before_stopping_services(self) -> None:
        restore = (SCRIPT.parents[1] / "playbooks" / "service-state-restore.yml").read_text(encoding="utf-8")
        self.assertIn("service-state-capacity-preflight.py", restore)
        self.assertIn("validate-service-state-archive.py", restore)
        self.assertIn("fetch-service-state.py", restore)
        self.assertNotIn("ansible.builtin.fetch:", restore)
        self.assertNotIn("failed_when: false", restore[:restore.index("Create temporary pre-restore")])
        self.assertNotIn("tar -tzf", restore)
        self.assertIn("- name: Restore service state with failure-safe service recovery\n      block:", restore)
        self.assertIn("      always:\n", restore)
        self.assertLess(restore.index("      always:"), restore.index("Report service-state restore result"))
        self.assertLess(
            restore.index("Preflight service-state restore capacity"),
            restore.index("Stop managed system services before restore"),
        )


if __name__ == "__main__":
    unittest.main()

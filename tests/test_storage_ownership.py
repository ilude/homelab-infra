from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
STORAGE_TASKS = {
    "directory": ROOT / "infra" / "ansible" / "tasks" / "host-storage-directory.yml",
    "zfs": ROOT / "infra" / "ansible" / "tasks" / "host-storage-zfs-dataset.yml",
    "nfs": ROOT / "infra" / "ansible" / "tasks" / "host-storage-nfs-mount.yml",
    "cifs": ROOT / "infra" / "ansible" / "tasks" / "host-storage-cifs-mount.yml",
}


def evaluate_when(expression: str, fixtures: dict[str, dict[str, Any]]) -> bool:
    """Evaluate the small registered-result guard grammar used by storage tasks."""
    values = {name: SimpleNamespace(**result) for name, result in fixtures.items()}

    def resolve(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError(f"unknown registered result: {node.id}")
            return values[node.id]
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            value = resolve(node.value)
            if not hasattr(value, node.attr):
                raise ValueError(f"unknown registered result attribute: {node.attr}")
            return getattr(value, node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int)):
            return node.value
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left, right = resolve(node.left), resolve(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        raise ValueError(f"unsupported storage ownership guard: {ast.dump(node)}")

    return bool(resolve(ast.parse(expression, mode="eval").body))


class StorageOwnershipTests(unittest.TestCase):
    def ownership_task(self, backend: str) -> dict[str, Any]:
        tasks = yaml.safe_load(STORAGE_TASKS[backend].read_text(encoding="utf-8"))
        ownership_tasks = [task for task in tasks if str(task.get("name", "")).startswith("Set initial host")]
        self.assertEqual(len(ownership_tasks), 1, backend)
        return ownership_tasks[0]

    def test_ownership_is_applied_only_on_initial_creation_or_mount(self) -> None:
        expected_guards = {
            "directory": "storage_host_directory.changed",
            "zfs": "storage_zfs_list.rc != 0",
            "nfs": "storage_host_nfs_mount.rc == 0",
            "cifs": "storage_host_cifs_mount.rc == 0",
        }
        for backend, guard in expected_guards.items():
            task = self.ownership_task(backend)
            self.assertEqual(task.get("when"), guard, backend)
            file_task = task["ansible.builtin.file"]
            self.assertIn("owner", file_task, backend)
            self.assertIn("group", file_task, backend)
            self.assertIn("mode", file_task, backend)

    def test_loaded_ownership_guards_apply_only_on_first_run_behavior_model(self) -> None:
        fixtures = {
            "directory": ("storage_host_directory", {"changed": True}, {"changed": False}),
            "zfs": ("storage_zfs_list", {"rc": 1}, {"rc": 0}),
            "nfs": ("storage_host_nfs_mount", {"rc": 0}, {"rc": 32}),
            "cifs": ("storage_host_cifs_mount", {"rc": 0}, {"rc": 32}),
        }
        for backend, (result_name, first_run, repeat_run) in fixtures.items():
            guard = self.ownership_task(backend)["when"]
            self.assertTrue(evaluate_when(guard, {result_name: first_run}), backend)
            self.assertFalse(evaluate_when(guard, {result_name: repeat_run}), backend)

    def test_directory_creation_does_not_reset_existing_ownership(self) -> None:
        tasks = yaml.safe_load(STORAGE_TASKS["directory"].read_text(encoding="utf-8"))
        create = tasks[0]["ansible.builtin.file"]
        self.assertNotIn("owner", create)
        self.assertNotIn("group", create)
        self.assertNotIn("mode", create)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace-preflight.py"
spec = importlib.util.spec_from_file_location("workspace_preflight", SCRIPT)
assert spec and spec.loader
workspace_preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = workspace_preflight
spec.loader.exec_module(workspace_preflight)


class WorkspacePreflightTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        opentofu = root / "infra" / "opentofu"
        opentofu.mkdir(parents=True)
        (opentofu / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
        values = root / "values"
        values.mkdir()
        (values / "terraform.tfstate").write_text("{}\n", encoding="utf-8")
        (values / "terraform.tfstate.backup").write_text("{}\n", encoding="utf-8")
        return temp, root

    def test_writable_workspace_passes(self) -> None:
        temp, root = self.make_repo()
        with temp:
            self.assertIsNone(workspace_preflight.run(root, require_values=True))

    def test_missing_values_fails_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)

    def test_missing_values_passes_when_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra" / "opentofu").mkdir(parents=True)
            self.assertIsNone(workspace_preflight.run(root, require_values=False))

    def test_state_lock_fails(self) -> None:
        temp, root = self.make_repo()
        with temp:
            (root / "values" / ".terraform.tfstate.lock.info").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(workspace_preflight.PreflightError):
                workspace_preflight.run(root, require_values=True)


if __name__ == "__main__":
    unittest.main()

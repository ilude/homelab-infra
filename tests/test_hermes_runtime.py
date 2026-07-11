from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "infra" / "ansible" / "roles" / "hermes"
LOCK = ROLE / "files" / "requirements-0.18.0.lock"
RUNTIME_TASKS = ROLE / "tasks" / "managed-runtime.yml"
MAIN_TASKS = ROLE / "tasks" / "main.yml"
UNIT = ROLE / "templates" / "hermes-dashboard.service.j2"
WHEEL_SHA256 = "bf75c02d59f7c464cd0d85026fb7ee2e6bb15f003beccab3442b572f1ae1fd37"


class HermesLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = LOCK.read_text(encoding="utf-8")

    def test_lock_is_targeted_and_complete_for_approved_dashboard_extras(self) -> None:
        self.assertIn("Debian 13 amd64, CPython 3.13", self.lock)
        self.assertIn("--python-platform x86_64-manylinux_2_40", self.lock)
        self.assertIn("hermes-agent[pty, web]==0.18.0", self.lock)
        for requirement in ("fastapi==0.133.1", "uvicorn[standard]==0.41.0", "starlette==1.0.1", "python-multipart==0.0.27"):
            self.assertIn(requirement, self.lock)
        packages = re.findall(r"(?m)^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==[^ \\]+ \\$", self.lock)
        self.assertEqual(len(packages), 60)

    def test_every_locked_requirement_has_a_sha256_and_no_external_source(self) -> None:
        blocks = re.split(r"(?m)(?=^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==)", self.lock)
        requirements = [block for block in blocks if re.match(r"^[a-z0-9]", block)]
        self.assertTrue(requirements)
        for block in requirements:
            self.assertRegex(block, r"--hash=sha256:[0-9a-f]{64}")
        self.assertNotRegex(self.lock, r"(?m)^[^#\n]*(?:https?://|git\+|--find-links)")
        self.assertIn(f"--hash=sha256:{WHEEL_SHA256}", self.lock)


class HermesRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = RUNTIME_TASKS.read_text(encoding="utf-8")
        cls.main = MAIN_TASKS.read_text(encoding="utf-8")
        cls.unit = UNIT.read_text(encoding="utf-8")

    def test_runtime_uses_only_hashed_wheels_without_upstream_installer(self) -> None:
        self.assertNotIn("hermes-agent.nousresearch.com/install.sh", self.main)
        self.assertNotIn("pip install -e", self.main)
        self.assertIn("--require-hashes", self.tasks)
        self.assertIn("--only-binary=:all:", self.tasks)
        self.assertIn("https://pypi.org/simple", self.tasks)
        self.assertIn("hermes_staged_wheel.stat.checksum != hermes_discovery_wheel_sha256", self.tasks)

    def test_activation_is_versioned_atomic_and_rolls_back(self) -> None:
        self.assertIn("/releases/{{ hermes_discovery_version }}-", self.tasks)
        self.assertIn("Atomically activate Hermes virtual environment", self.tasks)
        self.assertIn("mv\n          - -Tf", self.tasks)
        self.assertIn("Retain previous Hermes release link", self.tasks)
        self.assertIn("rescue:", self.tasks)
        self.assertIn("Restore previous managed Hermes virtual environment link", self.tasks)
        self.assertIn("Verify rolled-back Hermes dashboard", self.tasks)
        self.assertIn("Record healthy managed Hermes release", self.tasks)

    def test_launcher_systemd_and_runtime_state_contract_are_stable(self) -> None:
        self.assertIn("dest: /usr/local/bin/hermes", self.tasks)
        self.assertIn("exec /usr/local/lib/hermes-agent/venv/bin/hermes", self.tasks)
        self.assertIn("ExecStart=/usr/local/bin/hermes dashboard", self.unit)
        self.assertIn("User={{ hermes_runtime_user", self.unit)
        self.assertIn("HERMES_HOME=/home/{{ hermes_runtime_user", (ROLE / "templates" / "hermes-dashboard.env.j2").read_text(encoding="utf-8"))
        self.assertNotIn("/.hermes", self.tasks)


if __name__ == "__main__":
    unittest.main()

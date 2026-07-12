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
GATEWAY_UNIT = ROLE / "templates" / "hermes-gateway.service.j2"
ENV = ROLE / "templates" / "hermes-dashboard.env.j2"
PREFLIGHT = ROLE / "templates" / "hermes-dashboard-preflight.sh.j2"
WHEEL_SHA256 = "bf75c02d59f7c464cd0d85026fb7ee2e6bb15f003beccab3442b572f1ae1fd37"


class HermesLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = LOCK.read_text(encoding="utf-8")

    def test_lock_is_targeted_and_complete_for_dashboard_and_messaging(self) -> None:
        self.assertIn("Debian 13 amd64, CPython 3.13", self.lock)
        self.assertIn("--python-platform x86_64-manylinux_2_40", self.lock)
        self.assertIn("hermes-agent[messaging, pty, web]==0.18.0", self.lock)
        for requirement in (
            "fastapi==0.133.1",
            "uvicorn[standard]==0.41.0",
            "starlette==1.0.1",
            "python-multipart==0.0.27",
            "discord-py==2.7.1",
            "python-telegram-bot==22.6",
            "slack-bolt==1.27.0",
        ):
            self.assertIn(requirement, self.lock)
        packages = re.findall(r"(?m)^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==", self.lock)
        self.assertEqual(len(packages), 79)

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
        cls.gateway_unit = GATEWAY_UNIT.read_text(encoding="utf-8")

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
        self.assertIn("Stop Hermes gateway before activation", self.tasks)
        self.assertIn("Start activated Hermes gateway", self.tasks)
        self.assertIn("Restart rolled-back Hermes gateway", self.tasks)
        self.assertIn("Verify rolled-back Hermes dashboard", self.tasks)
        self.assertIn("Record healthy managed Hermes release", self.tasks)

    def test_launcher_systemd_and_runtime_state_contract_are_stable(self) -> None:
        self.assertIn("dest: /usr/local/bin/hermes", self.tasks)
        self.assertIn("exec /usr/local/lib/hermes-agent/venv/bin/hermes", self.tasks)
        self.assertIn("ExecStartPre=/usr/local/libexec/hermes-dashboard-preflight", self.unit)
        self.assertIn("ExecStart=/usr/local/bin/hermes dashboard", self.unit)
        self.assertIn("User={{ hermes_runtime_user", self.unit)
        self.assertIn("dest: /etc/systemd/system/hermes-gateway.service", self.main)
        self.assertIn("ExecStart=/usr/local/lib/hermes-agent/venv/bin/python -m hermes_cli.main gateway run", self.gateway_unit)
        self.assertIn("HERMES_DISABLE_LAZY_INSTALLS=1", self.gateway_unit)
        self.assertNotIn("/releases/", self.gateway_unit)
        env = ENV.read_text(encoding="utf-8")
        self.assertIn("HERMES_HOME=/home/{{ hermes_runtime_user", env)
        self.assertIn("HERMES_NODE=/usr/local/lib/hermes-node/current/bin/node", env)
        self.assertIn("HERMES_SKIP_NODE_BOOTSTRAP=1", env)
        self.assertIn("HERMES_DISABLE_LAZY_INSTALLS=1", env)
        self.assertIn("PATH=/usr/local/lib/hermes-node/current/bin:", env)
        self.assertNotIn("/.hermes", self.tasks)

    def test_dashboard_dependencies_are_preflighted_and_logs_are_gated(self) -> None:
        preflight = PREFLIGHT.read_text(encoding="utf-8")
        for marker in (
            "HERMES_PREFLIGHT_NODE_MISSING",
            "HERMES_PREFLIGHT_NODE_VERSION_MISMATCH",
            "HERMES_PREFLIGHT_TUI_MISSING",
            "HERMES_PREFLIGHT_TUI_INVALID",
            "HERMES_PREFLIGHT_PYTHON_IMPORT_FAILED",
        ):
            self.assertIn(marker, preflight)
        self.assertIn("--check", preflight)
        self.assertIn("Install verified managed Node.js runtime", self.main)
        self.assertIn("Link Hermes dashboard TUI bundle to the active release", self.main)
        self.assertIn("Verify active Hermes messaging imports", self.main)
        self.assertIn("Verify staged Hermes messaging imports", self.tasks)
        self.assertIn("import aiohttp, discord, slack_bolt, telegram", self.tasks)
        self.assertIn("hermes_requirements_lock_sha256", self.tasks)
        self.assertNotIn("import aiohttp", preflight)
        self.assertIn("Reject Hermes startup journal errors", self.main)
        self.assertIn("HERMES_PREFLIGHT_|Chat unavailable|node not found", self.main)


if __name__ == "__main__":
    unittest.main()

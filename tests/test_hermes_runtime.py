from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "infra" / "ansible" / "roles" / "hermes"
LOCK = ROLE / "files" / "requirements-0.18.0.lock"
RUNTIME_TASKS = ROLE / "tasks" / "managed-runtime.yml"
MAIN_TASKS = ROLE / "tasks" / "main.yml"
BOOTSTRAP_TASKS = ROLE / "tasks" / "bootstrap-state.yml"
DEFAULTS = ROLE / "defaults" / "main.yml"
UNIT = ROLE / "templates" / "hermes-dashboard.service.j2"
GATEWAY_UNIT = ROLE / "templates" / "hermes-gateway.service.j2"
ENV = ROLE / "templates" / "hermes-dashboard.env.j2"
PREFLIGHT = ROLE / "templates" / "hermes-dashboard-preflight.sh.j2"
OPERATOR_PLUGIN = ROLE / "files" / "homelab-infra-operator" / "__init__.py"
OPERATOR_MANIFEST = ROLE / "files" / "homelab-infra-operator" / "plugin.yaml"
OPERATOR_DASHBOARD_MANIFEST = ROLE / "files" / "homelab-infra-operator" / "dashboard" / "manifest.json"
OPERATOR_DASHBOARD_API = ROLE / "files" / "homelab-infra-operator" / "dashboard" / "plugin_api.py"
OPERATOR_DASHBOARD_JS = ROLE / "files" / "homelab-infra-operator" / "dashboard" / "dist" / "index.js"
WHEEL_SHA256 = "bf75c02d59f7c464cd0d85026fb7ee2e6bb15f003beccab3442b572f1ae1fd37"


class HermesLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = LOCK.read_text(encoding="utf-8")

    def test_lock_is_targeted_and_complete_for_dashboard_and_messaging_extras(self) -> None:
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
        cls.bootstrap = BOOTSTRAP_TASKS.read_text(encoding="utf-8")
        cls.defaults = DEFAULTS.read_text(encoding="utf-8")
        cls.unit = UNIT.read_text(encoding="utf-8")
        cls.gateway_unit = GATEWAY_UNIT.read_text(encoding="utf-8")
        cls.operator_plugin = OPERATOR_PLUGIN.read_text(encoding="utf-8")
        cls.operator_manifest = OPERATOR_MANIFEST.read_text(encoding="utf-8")
        cls.operator_dashboard_manifest = OPERATOR_DASHBOARD_MANIFEST.read_text(encoding="utf-8")
        cls.operator_dashboard_api = OPERATOR_DASHBOARD_API.read_text(encoding="utf-8")
        cls.operator_dashboard_js = OPERATOR_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_runtime_user_can_run_containerized_tasks(self) -> None:
        self.assertIn("Grant Hermes runtime user access to Docker", self.main)
        self.assertIn("groups: docker", self.main)
        self.assertIn("install -d -m 0755 -o", self.main)

    def test_managed_runtime_uses_hashed_wheels_and_legacy_fallback_is_scoped(self) -> None:
        self.assertIn("Detect Hermes managed wheel runtime support", self.main)
        self.assertIn("Reject unsupported Hermes runtime without explicit legacy opt-in", self.main)
        self.assertIn("Install legacy Hermes Agent CLI and dashboard dependencies", self.main)
        self.assertIn("not hermes_managed_runtime_supported", self.main)
        self.assertIn("hermes_allow_legacy_runtime", self.main)
        self.assertIn("--require-hashes", self.tasks)
        self.assertIn("--only-binary=:all:", self.tasks)
        self.assertIn("https://pypi.org/simple", self.tasks)
        self.assertIn("hermes_staged_wheel.stat.checksum != hermes_discovery_wheel_sha256", self.tasks)

    def test_activation_is_versioned_atomic_and_prepares_tui_before_health_check(self) -> None:
        self.assertIn("/releases/{{ hermes_discovery_version }}-", self.tasks)
        self.assertIn("Atomically activate Hermes virtual environment", self.tasks)
        self.assertIn("mv\n          - -Tf", self.tasks)
        self.assertIn("Link Hermes dashboard TUI bundle before activation health check", self.tasks)
        self.assertIn("hermes_requirements_lock_sha256", self.tasks)
        self.assertIn("Retain previous Hermes release link", self.tasks)
        self.assertIn("rescue:", self.tasks)
        self.assertIn("Stop Hermes gateway before activation", self.tasks)
        self.assertIn("Start activated Hermes gateway", self.tasks)
        self.assertIn("Restart rolled-back Hermes gateway", self.tasks)
        self.assertIn("Verify rolled-back Hermes dashboard", self.tasks)

    def test_launcher_systemd_and_runtime_state_contract_are_stable(self) -> None:
        self.assertIn("dest: /usr/local/bin/hermes", self.tasks)
        self.assertIn("exec /usr/local/lib/hermes-agent/venv/bin/hermes", self.tasks)
        self.assertIn("ExecStartPre=/usr/local/libexec/hermes-dashboard-preflight", self.unit)
        self.assertIn("ExecStart=/usr/local/bin/hermes dashboard", self.unit)
        self.assertIn('Environment="KUBERNETES_SERVICE_HOST=hermes-managed-runtime"', self.unit)
        self.assertIn("hermes_managed_runtime_supported", self.main)
        self.assertIn("dest: /etc/systemd/system/hermes-gateway.service", self.main)
        self.assertIn("hermes_managed_runtime_supported", self.main)
        self.assertIn("ExecStart=/usr/local/lib/hermes-agent/venv/bin/python -m hermes_cli.main gateway run", self.gateway_unit)
        self.assertIn("HERMES_DISABLE_LAZY_INSTALLS=1", self.gateway_unit)
        self.assertNotIn("/releases/", self.gateway_unit)
        env = ENV.read_text(encoding="utf-8")
        self.assertIn("hermes_managed_runtime_supported", env)
        self.assertIn("HERMES_NODE=/usr/local/lib/hermes-node/current/bin/node", env)
        self.assertIn("HERMES_SKIP_NODE_BOOTSTRAP=1", env)
        self.assertIn("HERMES_DISABLE_LAZY_INSTALLS=1", env)
        self.assertIn("PATH=/usr/local/lib/hermes-node/current/bin:", env)

    def test_operator_plugin_is_installed_enabled_and_approval_gated(self) -> None:
        self.assertIn("homelab-infra-operator/plugin.yaml", self.main)
        self.assertIn("homelab-infra-operator/__init__.py", self.main)
        self.assertIn("plugins", self.main)
        self.assertIn("HERMES_OPERATOR_REPO_PATH", self.gateway_unit)
        self.assertIn("HERMES_OPERATOR_REPO_PATH", ENV.read_text(encoding="utf-8"))
        self.assertIn("name: homelab-infra-operator", self.operator_manifest)
        self.assertIn('enum": list(_ACTIONS)', self.operator_plugin)
        self.assertIn('name="infra-apply"', self.operator_plugin)
        self.assertIn('"--approve"', self.operator_plugin)
        self.assertIn("unsupported apply argument", self.operator_plugin)
        self.assertIn("Configure Hermes SearXNG web-search backend", self.main)
        self.assertIn("web.search_backend", self.main)
        self.assertIn('"path": "/homelab-infra"', self.operator_dashboard_manifest)
        self.assertIn("@router.post(\"/apply\")", self.operator_dashboard_api)
        self.assertIn('body.get("confirm") != "APPLY"', self.operator_dashboard_api)
        self.assertIn('registry.register("homelab-infra-operator"', self.operator_dashboard_js)

    def test_full_state_bootstrap_restore_is_guarded_and_validated(self) -> None:
        self.assertIn("Restore guarded private Hermes state during bootstrap", self.main)
        self.assertIn("hermes-state-pre-restore-", self.bootstrap)
        self.assertIn("validate-service-state-archive.py", self.bootstrap)
        self.assertIn("Require customized soul state before automatic full restore", self.bootstrap)
        self.assertIn("Restore complete Hermes runtime state", self.bootstrap)
        self.assertIn("Repair restored Hermes runtime state ownership", self.bootstrap)
        self.assertIn("hermes_default_soul_sha256", self.defaults)
        self.assertLess(
            self.main.index("Restore guarded private Hermes state during bootstrap"),
            self.main.index("Ensure Hermes runtime state directory exists"),
        )

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
        self.assertIn("Link Hermes dashboard TUI bundle", self.main)
        self.assertIn("Verify active Hermes messaging imports", self.main)
        self.assertIn("Verify staged Hermes messaging imports", self.tasks)
        self.assertIn("import aiohttp, discord, slack_bolt, telegram", self.tasks)
        self.assertNotIn("import aiohttp", preflight)
        self.assertIn("Reject Hermes startup journal errors", self.main)
        self.assertIn("HERMES_PREFLIGHT_|Chat unavailable|node not found", self.main)


if __name__ == "__main__":
    unittest.main()

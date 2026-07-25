from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PARENT_TASKS = ROOT / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml"
CONTROL_TASKS = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "tasks" / "main.yml"
CONTROL_API_ENV = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "templates" / "api.env.j2"
CONTROL_BRIDGE_ENV = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "templates" / "bridge.env.j2"
CONTROL_PLUGIN_ENV = ROOT / "infra" / "ansible" / "roles" / "hermes_control" / "templates" / "plugin.env.j2"
GATEWAY_UNIT = ROOT / "infra" / "ansible" / "roles" / "hermes" / "templates" / "hermes-gateway.service.j2"
CADDYFILE = ROOT / "infra" / "ansible" / "roles" / "hermes" / "templates" / "Caddyfile.j2"
OPERATIONS_DOC = ROOT / "docs" / "hermes-control-operations.md"


class HermesControlRoleTests(unittest.TestCase):
    def test_parent_configures_control_after_caddy_is_active(self) -> None:
        text = PARENT_TASKS.read_text(encoding="utf-8")
        self.assertLess(text.index("Verify Hermes Caddy service is active"), text.index("Configure optional Hermes Control companion stack"))
        self.assertLess(text.index("Configure optional Hermes Control companion stack"), text.index("Verify Hermes Control HTTPS health through Caddy"))

    def test_control_role_enforces_pinned_source_and_readiness(self) -> None:
        text = CONTROL_TASKS.read_text(encoding="utf-8")
        for fragment in (
            "ansible.builtin.git:",
            "version: \"{{ hermes_control_source_ref }}\"",
            "hermes_control_source_ref is match('^[0-9a-f]{40}$')",
            "plugins",
            "install",
            "file://{{ hermes_control_checkout_path }}",
            "Flush Hermes Control service changes before readiness checks",
            "bridge socket accepts connections",
            "Verify authenticated Hermes Control diagnostics",
        ):
            self.assertIn(fragment, text)
        self.assertIn("no_log: true", text)
        self.assertIn("changed_when: true\n  notify: Restart hermes gateway", text)
        self.assertIn("CONTROL_API_REQUIRE_TASK_APPROVAL=1", CONTROL_API_ENV.read_text(encoding="utf-8"))
        self.assertIn("EnvironmentFile=-/etc/hermes-control/plugin.env", GATEWAY_UNIT.read_text(encoding="utf-8"))

    def test_restore_stops_are_inside_failure_safe_block(self) -> None:
        restore = (ROOT / "infra" / "ansible" / "playbooks" / "service-state-restore.yml").read_text(encoding="utf-8")
        block_start = restore.index("- name: Restore service state with failure-safe service recovery\n      block:\n        - name: Stop managed system services before restore")
        self.assertLess(block_start, restore.index("      always:"))
        self.assertLess(restore.index("Stop managed user services before restore"), restore.index("      always:"))

    def test_control_role_exposes_only_loopback_api_through_private_caddy(self) -> None:
        caddy = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("{% if hermes_control_enabled | default(false) %}", caddy)
        self.assertIn("reverse_proxy {{ hermes_control_api_host | default('127.0.0.1') }}:{{ hermes_control_api_port | default(8787) }}", caddy)
        self.assertIn("{{ hermes_control_domain }} {", caddy)
        self.assertIn("tls {", caddy)
        self.assertIn("hermes_control_api_host == '127.0.0.1'", CONTROL_TASKS.read_text(encoding="utf-8"))

    def test_control_environment_views_keep_tokens_scoped(self) -> None:
        api = CONTROL_API_ENV.read_text(encoding="utf-8")
        bridge = CONTROL_BRIDGE_ENV.read_text(encoding="utf-8")
        plugin = CONTROL_PLUGIN_ENV.read_text(encoding="utf-8")
        self.assertIn("CONTROL_API_TOKEN={{ hermes_control_api_token }}", api)
        self.assertIn("CONTROL_API_HERMES_PLUGIN_TOKEN={{ hermes_control_bridge_token }}", api)
        self.assertIn("HERMES_CONTROL_EXTENSION_TOKEN={{ hermes_control_bridge_token }}", bridge)
        self.assertNotIn("hermes_control_bridge_token", plugin)
        self.assertIn("CONTROL_API_TOKEN={{ hermes_control_api_token }}", plugin)

    def test_operations_doc_covers_deployed_verification_and_recovery(self) -> None:
        operations = OPERATIONS_DOC.read_text(encoding="utf-8")
        for marker in (
            "Five-state verification",
            "Rotation and rollback",
            "HERMES_PLUGINS_DEBUG=1",
            "HERMES_CONTROL_SOURCE_REF",
            "Do not expose port 8787",
        ):
            self.assertIn(marker, operations)

    def test_control_role_yaml_is_parseable(self) -> None:
        self.assertIsInstance(yaml.safe_load(CONTROL_TASKS.read_text(encoding="utf-8")), list)


if __name__ == "__main__":
    unittest.main()

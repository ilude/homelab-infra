from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hermes-operator.py"
spec = importlib.util.spec_from_file_location("hermes_operator", SCRIPT)
assert spec and spec.loader
hermes_operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hermes_operator
spec.loader.exec_module(hermes_operator)


class HermesOperatorTests(unittest.TestCase):
    def test_redaction_removes_secrets_private_addresses_and_paths(self) -> None:
        text = (
            "TOKEN=super-secret-value host=192.168.10.20 "  # public-safety: allow-ip # public-safety: allow-secret
            "path=/workspace/values/.env url=https://git.private.internal/"
        )
        redacted = hermes_operator.redact_output(text, {"super-secret-value"})
        self.assertNotIn("super-secret-value", redacted)
        self.assertNotIn("192.168.10.20", redacted)  # public-safety: allow-ip
        self.assertNotIn("git.private.example", redacted)
        self.assertNotIn("/workspace/values/.env", redacted)
        self.assertIn("<redacted>", redacted)

    def test_apply_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(Path(temp), "apply", approve=False, runner=lambda *_: 0)

    def test_apply_does_not_allow_destructive_plan_without_second_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata = root / "tfplan.meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "schema_version": hermes_operator.SCHEMA_VERSION,
                        "summary": {
                            "resource_changes": {"create": 0, "update": 0, "replace": 1, "delete": 0},
                            "destructive": True,
                            "destructive_changes": [{"address": "module.example", "actions": "delete/create"}],
                            "stateful_changes": [],
                            "stateful_targets": [],
                            "stateful_services": [],
                        },
                        "plan": {"sha256": "unused"},
                        "inputs": {},
                        "scope": {"target_service": "", "replace_service": ""},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(hermes_operator.OperatorError):
                hermes_operator.run_action(root, "apply", approve=True, runner=lambda *_: 0)

    def test_action_writes_audit_record_without_command_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = hermes_operator.run_action(
                root,
                "validate",
                runner=lambda *_: (0, "TOKEN=secret-value 192.168.1.5\n"),  # public-safety: allow-ip # public-safety: allow-secret
            )
            self.assertTrue(result["ok"])
            audit = json.loads((root / ".tmp" / "hermes-operator-audit.jsonl").read_text())
            self.assertEqual(audit["action"], "validate")
            self.assertNotIn("secret-value", (root / ".tmp" / "hermes-operator-audit.jsonl").read_text())

    def test_status_is_machine_readable_and_does_not_include_private_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "infra").mkdir()
            (root / "infra" / "services.json").write_text(
                json.dumps({"default_services": ["hermes"], "services": {"hermes": {}}}),
                encoding="utf-8",
            )
            (root / "settings.local.json").write_text(
                '{"services":["hermes"]}\n', encoding="utf-8"
            )
            status = hermes_operator.status(root)
            self.assertEqual(status["action"], "status")
            self.assertEqual(status["enabled_services"], ["hermes"])
            self.assertNotIn("settings.local.json", json.dumps(status))
            self.assertNotIn("terraform.tfvars", json.dumps(status))


if __name__ == "__main__":
    unittest.main()

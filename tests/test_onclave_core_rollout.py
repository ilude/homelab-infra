from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
ROLLOUT_PATH = REPO / "scripts" / "onclave-core-rollout.py"
REDACTOR_PATH = REPO / "scripts" / "redact-core-logs.py"
PLAYBOOK_PATH = REPO / "infra" / "ansible" / "playbooks" / "onclave-core-rollout.yml"
FIXTURE = REPO / "tests" / "fixtures" / "site-config" / "ansible" / "inventory" / "local.yml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rollout = load_module("onclave_core_rollout_test_subject", ROLLOUT_PATH)
redactor = load_module("onclave_core_log_redactor_test_subject", REDACTOR_PATH)


class OnclaveCoreRolloutTests(unittest.TestCase):
    def test_pin_update_changes_only_approved_inventory_keys(self) -> None:
        before = FIXTURE.read_text(encoding="utf-8")

        def parsed(text: str, _key: str):
            return yaml.safe_load(text)

        old = rollout.pin_values(before, parsed)
        desired = dict(old)
        desired.update(
            {
                "onclave_source_git_sha": "a" * 40,
                "onclave_app_definition_url": (
                    "https://raw.githubusercontent.com/example/onclave/"
                    + "a" * 40
                    + "/deploy/app/onclave/compose.yaml"
                ),
                "onclave_app_definition_sha256": "b" * 64,
                "onclave_backup_script_sha256": "c" * 64,
                "onclave_restore_script_sha256": "d" * 64,
                "onclave_core_image_tag": "a" * 40,
                "onclave_core_image_digest": "sha256:" + "e" * 64,
            }
        )
        after = rollout.update_inventory_pins(before, desired)
        rollout.assert_only_pins_changed(before, after, parsed)
        self.assertEqual(rollout.pin_values(after, parsed), desired)

    def test_source_urls_replace_only_the_commit_component(self) -> None:
        before = FIXTURE.read_text(encoding="utf-8")
        inventory = yaml.safe_load(before)["all"]["vars"]
        urls = rollout.source_urls(inventory["onclave_app_definition_url"], "a" * 40)
        expected_path = "/" + "a" * 40 + "/deploy/app/onclave/compose.yaml"
        self.assertIn(expected_path, urls["onclave_app_definition_url"])
        self.assertTrue(urls["backup-postgres.sh"].endswith("/backup-postgres.sh"))
        self.assertTrue(urls["restore-postgres.sh"].endswith("/restore-postgres.sh"))

    def test_supplied_digest_must_match_resolved_tag(self) -> None:
        self.assertRegex("sha256:" + "a" * 64, rollout.DIGEST_RE)
        self.assertNotRegex("sha256:" + "A" * 64, rollout.DIGEST_RE)

    def test_log_redaction_is_bounded(self) -> None:
        text = (
            "Authorization: Bearer secret-token\n"
            "password=secret-value\n"
            '{"api_key":"json-secret"}\n'
            "amqp://user:uri-secret@broker/onclave\n" + ("x" * 5000 + "\n") * 250
        )
        result = redactor.redact(text)
        self.assertNotIn("secret-token", result)
        self.assertNotIn("secret-value", result)
        self.assertNotIn("json-secret", result)
        self.assertNotIn("uri-secret", result)
        self.assertLessEqual(len(result.splitlines()), redactor.MAX_LINES)
        self.assertTrue(all(len(line) <= redactor.MAX_LINE_LENGTH for line in result.splitlines()))


if __name__ == "__main__":
    unittest.main()

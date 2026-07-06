from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER_TASKS = REPO / "infra" / "ansible" / "roles" / "forgejo_runner" / "tasks" / "main.yml"
CADDY_TASK_FILES = (
    REPO / "infra" / "ansible" / "roles" / "caddy_proxy" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "caddy.yml",
    REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
)


def task_block(text: str, name: str) -> str:
    pattern = re.compile(rf"(?ms)^- name: {re.escape(name)}\n(?P<body>.*?)(?=^- name: |\Z)")
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"missing task: {name}")
    return match.group("body")


def task_names(text: str) -> list[str]:
    return re.findall(r"(?m)^- name: (.+)$", text)


class AnsibleSafetyTests(unittest.TestCase):
    def test_forgejo_runner_secret_tasks_are_no_log(self) -> None:
        text = RUNNER_TASKS.read_text(encoding="utf-8")
        for name in (
            "Validate Forgejo Actions runner variables",
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Stage Forgejo runner config on Proxmox host",
            "Check Forgejo runner config drift",
            "Push Forgejo runner config into LXC",
            "Secure Forgejo runner config",
        ):
            self.assertRegex(task_block(text, name), r"(?m)^  no_log: true$")

    def test_caddy_validation_does_not_fmt_overwrite_managed_files(self) -> None:
        for path in CADDY_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("caddy fmt --overwrite", text, str(path))
            self.assertIn("caddy validate --config /etc/caddy/Caddyfile", text, str(path))

    def test_forgejo_runner_registration_is_guarded_by_existing_lookup(self) -> None:
        text = RUNNER_TASKS.read_text(encoding="utf-8")
        existing = task_block(text, "Check existing Forgejo Actions runner registration")
        registration = task_block(text, "Register Forgejo Actions runner with Forgejo")
        config = task_block(text, "Stage Forgejo runner config on Proxmox host")

        self.assertIn("action_runner", existing)
        self.assertIn("repository", existing)
        self.assertIn("repo_id", existing)
        self.assertIn("forgejo_runner_scope", existing)
        self.assertIn("forgejo_runner_name", existing)
        self.assertRegex(existing, r"(?m)^  changed_when: false$")
        self.assertIn('when: forgejo_runner_existing_registration.stdout | trim == ""', registration)
        self.assertNotIn("forgejo_runner_registration.stdout", config)
        self.assertIn("forgejo_runner_uuid", task_block(text, "Set Forgejo runner UUID"))

    def test_forgejo_runner_registration_task_order(self) -> None:
        names = task_names(RUNNER_TASKS.read_text(encoding="utf-8"))
        ordered = [
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Normalize Forgejo repository-scoped runner ownership",
            "Stage Forgejo runner config on Proxmox host",
        ]
        indexes = [names.index(name) for name in ordered]
        self.assertEqual(indexes, sorted(indexes))


if __name__ == "__main__":
    unittest.main()

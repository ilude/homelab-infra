from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
RUNNER_TASKS = REPO / "infra" / "ansible" / "roles" / "forgejo_runner" / "tasks" / "main.yml"
CADDY_TASK_FILES = (
    REPO / "infra" / "ansible" / "roles" / "caddy_proxy" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "caddy.yml",
    REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml",
)
ANSIBLE_TASK_FILES = tuple((REPO / "infra" / "ansible" / "roles").glob("*/tasks/*.yml"))
ALLOWLIST_PCT = {
    REPO / "infra" / "ansible" / "roles" / "lxc_ready" / "tasks" / "main.yml",
}


def load_tasks(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        return []
    return [task for task in data if isinstance(task, dict)]


def task_by_name(path: Path, name: str) -> dict[str, Any]:
    for task in load_tasks(path):
        if task.get("name") == name:
            return task
    raise AssertionError(f"missing task: {name}")


def task_names(path: Path) -> list[str]:
    return [str(task.get("name")) for task in load_tasks(path)]


def command_text(task: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
        value = task.get(key)
        if isinstance(value, dict):
            argv = value.get("argv")
            if isinstance(argv, list):
                values.extend(str(item) for item in argv)
            elif isinstance(value.get("cmd"), str):
                values.append(str(value["cmd"]))
        elif isinstance(value, str):
            values.append(value)
    return "\n".join(values)


class AnsibleSafetyTests(unittest.TestCase):
    def test_service_roles_do_not_use_pct_for_steady_state(self) -> None:
        for path in sorted((REPO / "infra" / "ansible" / "roles").glob("*/**/*.yml")):
            if path in ALLOWLIST_PCT:
                continue
            for task in load_tasks(path):
                self.assertNotRegex(command_text(task), r"(^|\s)pct(\s|$)", f"{path}: {task.get('name')}")

    def test_forgejo_runner_secret_tasks_are_no_log(self) -> None:
        for name in (
            "Validate Forgejo Actions runner variables",
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Install Forgejo runner config",
        ):
            self.assertTrue(task_by_name(RUNNER_TASKS, name).get("no_log"), name)

    def test_caddy_validation_does_not_fmt_overwrite_managed_files(self) -> None:
        for path in CADDY_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("caddy fmt --overwrite", text, str(path))
            self.assertIn("caddy validate --config /etc/caddy/Caddyfile", text, str(path))

    def test_curl_output_is_not_accidentally_streamed_to_ansible(self) -> None:
        for path in ANSIBLE_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"curl[^\n]*\n\s+-o\b",
                f"{path} has curl URL and -o split across YAML lines; folded blocks preserve the newline here, causing curl to stream binary to Ansible stdout",
            )

    def test_forgejo_runner_registration_is_guarded_by_existing_lookup(self) -> None:
        existing = task_by_name(RUNNER_TASKS, "Check existing Forgejo Actions runner registration")
        registration = task_by_name(RUNNER_TASKS, "Register Forgejo Actions runner with Forgejo")
        config = task_by_name(RUNNER_TASKS, "Install Forgejo runner config")

        existing_text = command_text(existing)
        self.assertIn("action_runner", existing_text)
        self.assertIn("repository", existing_text)
        self.assertIn("repo_id", existing_text)
        self.assertIn("forgejo_runner_scope", existing_text)
        self.assertIn("forgejo_runner_name", existing_text)
        self.assertEqual(existing.get("changed_when"), False)
        self.assertIn('forgejo_runner_existing_registration.stdout | trim == ""', str(registration.get("when")))
        self.assertEqual(existing.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(registration.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(task_by_name(RUNNER_TASKS, "Normalize Forgejo repository-scoped runner ownership").get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertNotIn("forgejo_runner_registration.stdout", str(config))
        self.assertIn("forgejo_runner_uuid", str(task_by_name(RUNNER_TASKS, "Set Forgejo runner UUID")))

    def test_forgejo_runner_registration_task_order(self) -> None:
        names = task_names(RUNNER_TASKS)
        ordered = [
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Normalize Forgejo repository-scoped runner ownership",
            "Install Forgejo runner config",
        ]
        indexes = [names.index(name) for name in ordered]
        self.assertEqual(indexes, sorted(indexes))

    def test_secret_files_are_direct_final_destinations_with_modes(self) -> None:
        checks = {
            "infra/ansible/roles/infisical/tasks/main.yml": "/etc/infisical/infisical.env",
            "infra/ansible/roles/hermes/tasks/main.yml": "/etc/hermes-dashboard.env",
            "infra/ansible/roles/caddy_proxy/tasks/main.yml": "/etc/caddy/env",
            "infra/ansible/roles/forgejo_runner/tasks/main.yml": "/etc/forgejo-runner/config.yml",
            "infra/ansible/roles/searxng_onramp/tasks/main.yml": "{{ searxng_onramp_base_dir }}/settings.yml",
        }
        for rel_path, dest in checks.items():
            tasks = load_tasks(REPO / rel_path)
            matches = [task for task in tasks if dest in str(task)]
            self.assertTrue(matches, rel_path)
            self.assertTrue(any(task.get("no_log") for task in matches), rel_path)
            self.assertTrue(any("mode" in str(task) for task in matches), rel_path)

    def test_hermes_exports_native_searxng_url_key(self) -> None:
        template = REPO / "infra" / "ansible" / "roles" / "hermes" / "templates" / "hermes-dashboard.env.j2"
        text = template.read_text(encoding="utf-8")
        self.assertIn("HERMES_WEB_SEARXNG_URL={{ hermes_web_searxng_url }}", text)
        self.assertIn("SEARXNG_URL={{ hermes_web_searxng_url }}", text)

    def test_searxng_onramp_ports_are_loopback_only(self) -> None:
        compose = REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "templates" / "docker-compose.yml.j2"
        text = compose.read_text(encoding="utf-8")
        self.assertIn("{{ searxng_onramp_bind_address }}:{{ searxng_onramp_container_port }}:8080", text)
        self.assertNotIn("0.0.0.0:{{ searxng_onramp_container_port }}:8080", text)  # public-safety: allow-ip
        task = task_by_name(REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml", "Validate SearXNG onramp required variables")
        self.assertIn("searxng_onramp_bind_address in ['127.0.0.1', '::1']", str(task))  # public-safety: allow-ip


if __name__ == "__main__":
    unittest.main()

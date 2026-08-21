from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra" / "ansible" / "roles" / "onramp_service_activation"
ROLE_TASKS = ROLE / "tasks" / "main.yml"
ROLE_SPECS = ROLE / "meta" / "argument_specs.yml"
SERVICE_ROLES = {
    "infisical_onramp": (
        "infisical-onramp.service",
        "infisical_onramp_deploy_user_uid",
        "Verify Infisical onramp loopback endpoint",
    ),
    "searxng_onramp": (
        "searxng-onramp.service",
        "searxng_onramp_deploy_user_uid",
        "Verify SearXNG loopback health endpoint",
    ),
    "freellmapi_onramp": (
        "freellmapi-onramp.service",
        "freellmapi_onramp_deploy_user_uid",
        "Verify FreeLLMAPI loopback health endpoint",
    ),
}


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_tasks(path: Path) -> list[dict[str, Any]]:
    data = load_yaml(path) or []
    return [task for task in data if isinstance(task, dict)]


def command_argv(task: dict[str, Any]) -> list[str]:
    command = task.get("ansible.builtin.command", {})
    return [str(value) for value in command.get("argv", [])]


class OnrampServiceActivationTests(unittest.TestCase):
    def test_role_arguments_and_checks_are_bounded_and_fail_fast(self) -> None:
        specs = load_yaml(ROLE_SPECS)["argument_specs"]["main"]["options"]
        self.assertEqual(
            set(specs),
            {
                "onramp_service_activation_unit_name",
                "onramp_service_activation_deploy_user",
                "onramp_service_activation_uid",
                "onramp_service_activation_runtime_dir",
            },
        )
        self.assertTrue(all(option["required"] for option in specs.values()))

        tasks = load_tasks(ROLE_TASKS)
        self.assertFalse(any("ansible.builtin.uri" in task for task in tasks))
        unit_check = next(
            task
            for task in tasks
            if task.get("name") == "Check Onramp rootless systemd user unit activation"
        )
        caddy_check = next(
            task
            for task in tasks
            if task.get("name") == "Check shared Caddy systemd unit activation"
        )
        for task in (unit_check, caddy_check):
            self.assertEqual(task["failed_when"], False)
            self.assertNotIn("retries", task)
            self.assertNotIn("delay", task)
            self.assertNotIn("until", task)

        self.assertEqual(
            command_argv(unit_check)[:3], ["systemctl", "--user", "is-active"]
        )
        self.assertEqual(command_argv(caddy_check), ["systemctl", "is-active", "caddy"])

        evidence_tasks = [
            task
            for task in tasks
            if str(task.get("name", "")).startswith("Collect bounded")
        ]
        self.assertEqual(len(evidence_tasks), 2)
        for task in evidence_tasks:
            argv = command_argv(task)
            self.assertIn("show", argv)
            self.assertIn("--no-pager", argv)
            self.assertTrue(any(value.startswith("--property=") for value in argv))
            self.assertNotIn("journalctl", argv)
            self.assertEqual(task["failed_when"], False)
            self.assertIn("when", task)

        final = next(
            task
            for task in tasks
            if task.get("name") == "Fail when an Onramp service is not active"
        )
        self.assertEqual(
            final["ansible.builtin.assert"]["that"],
            [
                "onramp_service_activation_unit_active.rc == 0",
                "onramp_service_activation_caddy_active.rc == 0",
            ],
        )
        self.assertIn("status=", final["ansible.builtin.assert"]["fail_msg"])

    def test_service_roles_call_shared_check_before_local_http_checks(self) -> None:
        for role_name, (unit_name, uid_register, http_task_name) in SERVICE_ROLES.items():
            tasks_path = (
                REPO / "infra" / "ansible" / "roles" / role_name / "tasks" / "main.yml"
            )
            tasks = load_tasks(tasks_path)
            activation_index, activation = next(
                (index, task)
                for index, task in enumerate(tasks)
                if task.get("name", "").endswith("service activation")
            )
            include = activation["ansible.builtin.include_role"]
            self.assertEqual(include["name"], "onramp_service_activation")
            variables = activation["vars"]
            self.assertEqual(variables["onramp_service_activation_unit_name"], unit_name)
            self.assertEqual(
                variables["onramp_service_activation_deploy_user"],
                "{{ onramp_host_deploy_user }}",
            )
            self.assertIn(uid_register, variables["onramp_service_activation_uid"])
            self.assertIn(uid_register, variables["onramp_service_activation_runtime_dir"])

            flush_index = next(
                index
                for index, task in enumerate(tasks)
                if task.get("ansible.builtin.meta") == "flush_handlers"
            )
            http_index = next(
                index for index, task in enumerate(tasks) if task.get("name") == http_task_name
            )
            self.assertGreater(activation_index, flush_index)
            self.assertLess(activation_index, http_index)
            self.assertFalse(
                any(
                    "is-active" in command_argv(task)
                    for task in tasks
                    if "ansible.builtin.command" in task
                )
            )

            if role_name == "freellmapi_onramp":
                health = next(task for task in tasks if task.get("name") == http_task_name)
                self.assertEqual(health.get("retries"), 24)


if __name__ == "__main__":
    unittest.main()

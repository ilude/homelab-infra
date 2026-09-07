"""Render the deployment boundary with synthetic inventory, without live secrets."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).parents[1]
ROLE = ROOT / "infra/ansible/roles/web_fetch_onramp"


class DeploymentTests(unittest.TestCase):
    def test_compose_keeps_the_browser_private_and_in_a_distinct_namespace(self) -> None:
        template = Environment(undefined=StrictUndefined).from_string(
            (ROLE / "templates/docker-compose.yml.j2").read_text(encoding="utf-8")
        )
        rendered = yaml.safe_load(
            template.render(
                web_fetch_host_port=8088,
                web_fetch_gateway_image=f"sha256:{'a' * 64}",
                web_fetch_browser_image=f"sha256:{'b' * 64}",
            )
        )
        gateway, browser = (rendered["services"][name] for name in ("gateway", "browser"))
        self.assertEqual(gateway["ports"], ["127.0.0.1:8088:8080"])
        self.assertNotIn("ports", browser)
        self.assertFalse(rendered["x-podman"]["in_pod"])
        self.assertEqual(browser["cap_add"], ["NET_ADMIN"])
        for service in (gateway, browser):
            self.assertNotEqual(service.get("network_mode"), "host")
            self.assertFalse(service.get("privileged", False))
            self.assertEqual(service["pull_policy"], "never")
            self.assertNotIn("/var/run", str(service.get("volumes", [])))

    def test_release_hold_is_checked_before_runtime_mutations(self) -> None:
        tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
        verify = next(
            index
            for index, task in enumerate(tasks)
            if task.get("ansible.builtin.include_tasks") == "image.yml"
        )
        mutation = next(
            index
            for index, task in enumerate(tasks)
            if any(
                key in task
                for key in (
                    "ansible.builtin.file",
                    "ansible.builtin.template",
                    "ansible.builtin.systemd_service",
                )
            )
        )
        self.assertLess(verify, mutation)
        image_tasks = yaml.safe_load((ROLE / "tasks/image.yml").read_text(encoding="utf-8"))
        import datetime
        import json
        from types import SimpleNamespace
        from unittest.mock import patch

        code = image_tasks[0]["ansible.builtin.command"]["argv"][2]
        base = "example/base@sha256:" + "b" * 64
        for days, label, accepted in ((8, base, True), (1, base, False), (8, "wrong", False)):
            upstream = {
                "Created": (
                    datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                ).isoformat()
            }
            built = {"Config": {"Labels": {"org.opencontainers.image.base.name": label}}}

            def inspect(args, **kwargs):
                return SimpleNamespace(stdout=json.dumps([upstream if args[-1] == base else built]))

            with (
                self.subTest(days=days, label=label),
                patch("subprocess.run", side_effect=inspect),
                patch("sys.argv", ["verify", "sha256:" + "a" * 64, base, "[]"]),
            ):
                if accepted:
                    exec(code, {})
                else:
                    with self.assertRaises(AssertionError):
                        exec(code, {})

    def test_backup_quiesces_only_the_new_service(self) -> None:
        state = yaml.safe_load(
            (ROOT / "infra/ansible/vars/service-state.yml").read_text(encoding="utf-8")
        )
        service = state["managed_service_state_catalog"]["web_fetch_onramp"]
        self.assertEqual(service["services"], [])
        self.assertEqual(service["user_services"], ["web-fetch-onramp.service"])
        self.assertTrue(service["backup_quiesce_user_services"])
        self.assertIn("web-fetch.caddy", str(service["paths"]))

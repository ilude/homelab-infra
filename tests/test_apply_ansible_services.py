from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply-ansible-services.py"
spec = importlib.util.spec_from_file_location("apply_ansible_services", SCRIPT)
assert spec and spec.loader
apply_ansible_services = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = apply_ansible_services
spec.loader.exec_module(apply_ansible_services)


class ApplyAnsibleServicesTests(unittest.TestCase):
    def test_dependency_waves_parallelize_independent_services(self) -> None:
        waves = apply_ansible_services.dependency_waves(
            ["technitium", "forgejo", "forgejo_runner", "onramp_host", "searxng_onramp", "hermes"]
        )

        self.assertEqual(waves[0], ["technitium", "forgejo", "onramp_host", "hermes"])
        self.assertEqual(waves[1], ["forgejo_runner", "searxng_onramp"])

    def test_run_service_keeps_service_playbooks_sequential(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            result = apply_ansible_services.run_service(
                "forgejo_runner",
                ("inventory.yml", "tfvars.py"),
                Path(temp),
                Path(temp) / ".env",
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [["ansible-playbook", "-i", "inventory.yml", "-i", "tfvars.py", "infra/ansible/playbooks/forgejo-runner.yml"]],
        )

    def test_technitium_dns_bootstraps_token_before_dns_sync(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            env_path = Path(temp) / ".env"
            env_path.write_text(
                'export TECHNITIUM_API_URL="http://192.0.2.53:5380/api"\n'
                'export TECHNITIUM_API_TOKEN="REPLACE_AFTER_TOKEN_CREATION"\n'
                'export DNS_RECORDS_FILE="values/dns-records.local.json"\n',
                encoding="utf-8",
            )
            result = apply_ansible_services.run_service(
                "technitium",
                ("inventory.yml",),
                Path(temp),
                env_path,
                dict(os.environ),
                runner,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            commands,
            [
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium.yml"],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/caddy-proxy.yml"],
                ["python", "scripts/bootstrap-technitium-api-token.py", "--env-file", str(env_path)],
                ["ansible-playbook", "-i", "inventory.yml", "infra/ansible/playbooks/technitium-dns.yml"],
            ],
        )

    def test_sequential_stops_after_first_failure(self) -> None:
        commands: list[list[str]] = []

        def runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
            commands.append(command)
            return 2 if command[-1] == "infra/ansible/playbooks/forgejo.yml" else 0

        with tempfile.TemporaryDirectory() as temp:
            results = apply_ansible_services.run_sequential(
                ["forgejo", "hermes"],
                ("inventory.yml",),
                Path(temp),
                Path(temp) / ".env",
                dict(os.environ),
                runner,
            )

        self.assertEqual([result.service for result in results], ["forgejo"])
        self.assertEqual(results[0].returncode, 2)
        self.assertEqual(len(commands), 1)


if __name__ == "__main__":
    unittest.main()

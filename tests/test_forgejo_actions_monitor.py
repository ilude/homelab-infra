from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "forgejo-actions-monitor.py"
spec = importlib.util.spec_from_file_location("forgejo_actions_monitor", SCRIPT)
assert spec and spec.loader
monitor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = monitor
spec.loader.exec_module(monitor)


class ForgejoActionsMonitorTests(unittest.TestCase):
    def test_ansible_uses_local_and_authoritative_tfvars_inventories(self) -> None:
        result = subprocess.CompletedProcess([], 0, "pve_target | SUCCESS | rc=0 >>\nok\n", "")
        with (
            mock.patch.object(monitor.shutil, "which", return_value="/usr/bin/ansible"),
            mock.patch.object(monitor.Path, "exists", return_value=True),
            mock.patch.object(monitor.subprocess, "run", return_value=result) as run,
        ):
            self.assertEqual(monitor.run_ansible_shell("echo ok"), "ok")

        argv = run.call_args.args[0]
        self.assertEqual(argv[0:2], ["ansible", "pve_target"])
        self.assertNotEqual(argv[1], "pve")
        self.assertEqual(
            argv[2:6],
            ["-i", monitor.INVENTORY, "-i", monitor.TFVARS_INVENTORY],
        )

    def test_every_pct_command_is_preceded_by_authority_guard(self) -> None:
        commands: list[str] = []

        def fake_run(command: str) -> str:
            commands.append(command)
            if "select id from action_run" in command:
                return '[{"id": 7}]'
            if "sqlite3" in command:
                return '[{"id": 7, "status": 1, "job_status": 1, "job_name": "job"}]'
            return "active"

        with (
            mock.patch.object(monitor, "run_ansible_shell", side_effect=fake_run),
            redirect_stdout(io.StringIO()),
        ):
            monitor.print_status(1, False)
            monitor.watch("latest", 1, 1)
            monitor.print_runners(False)
            monitor.print_logs("latest", 1, False)

        self.assertEqual(len(commands), 7)
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("pct exec", command)
                self.assertIn("proxmox_node_name", command)
                self.assertIn("refusing pct command", command)
                self.assertLess(command.index("hostname -s"), command.index("pct exec"))

    def test_authority_guard_is_rendered_before_payload(self) -> None:
        payload = 'printf "pct command reached\\n"'
        expected_guard = (
            'expected={{ proxmox_node_name | quote }}; '
            'actual="$(hostname -s 2>/dev/null || true)"; '
            'if [ "$actual" != "$expected" ]; then '
            'printf "%s\\n" "refusing pct command: connected host is not the configured Proxmox node" >&2; '
            "exit 1; "
            "fi; "
        )
        commands: list[str] = []
        with mock.patch.object(monitor, "run_ansible_shell", side_effect=commands.append):
            monitor.run_pve_pct(payload)

        self.assertEqual(commands, [expected_guard + payload])

    def test_authority_guard_failure_redacts_error_output(self) -> None:
        result = subprocess.CompletedProcess(
            [],
            1,
            "",
            "refusing pct command: connected host is not the configured Proxmox node TOKEN="
            + "secret https://example.internal 192.0.2.1",
        )
        with (
            mock.patch.object(monitor.shutil, "which", return_value="/usr/bin/ansible"),
            mock.patch.object(monitor.Path, "exists", return_value=True),
            mock.patch.object(monitor.subprocess, "run", return_value=result),
            self.assertRaisesRegex(monitor.MonitorError, "refusing pct command") as raised,
        ):
            monitor.run_pve_pct('printf "pct command reached\\n"')

        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("example.internal", str(raised.exception))
        self.assertNotIn("192.0.2.1", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

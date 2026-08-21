from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@unittest.skipIf(
    os.name == "nt", "run-infra.sh fake PATH test requires POSIX shell path semantics"
)
class RunInfraTests(unittest.TestCase):
    def run_with_fake_docker(
        self,
        exit_code: int,
        *,
        access_key: bool = True,
        command: tuple[str, ...] = ("true",),
        writeback: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        settings = root / "settings.local.json"
        settings.write_text(
            json.dumps(
                {
                    "bws": {
                        "project_id": "project-id",
                        "api_server": "https://bws.example.internal/api",
                    }
                }
            ),
            encoding="utf-8",
        )
        fakebin = root / "bin"
        fakebin.mkdir()
        record = root / "record"
        fake_docker = fakebin / "docker"
        fake_docker.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\n' "$@" > "{record}"
                exit {exit_code}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fakebin}{os.pathsep}{env['PATH']}",
                "INFRA_BWS_LOCATOR_FILE": str(settings),
            }
        )
        if access_key:
            env["BITWARDEN_ACCESS_KEY"] = "test-access-key"
        else:
            env.pop("BITWARDEN_ACCESS_KEY", None)
        if writeback:
            env["BWS_WRITEBACK"] = "1"
        else:
            env.pop("BWS_WRITEBACK", None)
        result = subprocess.run(
            ["bash", "scripts/run-infra.sh", *command],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, root, record

    def test_invokes_container_snapshot_runner_without_values_fallback(self) -> None:
        result, _, record = self.run_with_fake_docker(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = record.read_text(encoding="utf-8").splitlines()
        self.assertIn("scripts/run-infra-container.py", arguments)
        self.assertIn("--settings", arguments)
        self.assertNotIn("values/.env", arguments)
        self.assertNotIn("--env-from-file", arguments)

    def test_propagates_container_failure(self) -> None:
        result, _, _ = self.run_with_fake_docker(7)
        self.assertEqual(result.returncode, 7)

    def test_rejects_writeback_for_an_arbitrary_command(self) -> None:
        result, _, record = self.run_with_fake_docker(0, writeback=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("only allowed for: python scripts/update.py", result.stderr)
        self.assertFalse(record.exists())

    def test_passes_writeback_only_for_update(self) -> None:
        result, _, record = self.run_with_fake_docker(
            0,
            command=("python", "scripts/update.py"),
            writeback=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = record.read_text(encoding="utf-8").splitlines()
        self.assertIn("--writeback-update", arguments)
        self.assertNotIn("--writeback", arguments)

    def test_fails_closed_without_controller_access_key(self) -> None:
        result, _, record = self.run_with_fake_docker(0, access_key=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("BITWARDEN_ACCESS_KEY is missing", result.stderr)
        self.assertFalse(record.exists())


if __name__ == "__main__":
    unittest.main()

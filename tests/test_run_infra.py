from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "run-infra.sh fake PATH test requires POSIX shell path semantics")
class RunInfraTests(unittest.TestCase):
    def run_with_fake_docker(self, exit_code: int) -> tuple[subprocess.CompletedProcess[str], Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        values = root / "values"
        values.mkdir()
        (values / ".env").write_text("PVE_HOST=proxmox.example.internal\n", encoding="utf-8")
        fakebin = root / "bin"
        fakebin.mkdir()
        record = root / "record"
        fake_docker = fakebin / "docker"
        fake_docker.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                set -euo pipefail
                if printf '%s\n' "$@" | grep -qx -- "scripts/parse-env.py"; then
                  printf 'PVE_HOST=proxmox.example.internal\n'
                  exit 0
                fi
                env_file=""
                while [[ $# -gt 0 ]]; do
                  if [[ "$1" == "--env-from-file" ]]; then
                    env_file="$2"
                    break
                  fi
                  shift
                done
                test -f "$env_file"
                mode="$(stat -c '%a' "$env_file")"
                echo "$env_file $mode" > "{record}"
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
                "VALUES_DIR": str(values),
                "TMPDIR": str(root),
            }
        )
        result = subprocess.run(
            ["bash", "scripts/run-infra.sh", "true"],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, root

    def test_temp_env_file_removed_on_success(self) -> None:
        result, root = self.run_with_fake_docker(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(list(root.glob("run-infra.*")))

    def test_temp_env_file_removed_on_failure(self) -> None:
        result, root = self.run_with_fake_docker(7)
        self.assertEqual(result.returncode, 7)
        self.assertFalse(list(root.glob("run-infra.*")))


if __name__ == "__main__":
    unittest.main()

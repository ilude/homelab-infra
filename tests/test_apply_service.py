#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVICE_SCRIPT = REPO / "scripts" / "apply-service.sh"


def _windows_bash_context(
    script: Path, env: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    cygpath_name = shutil.which("cygpath")
    if cygpath_name is None:
        raise RuntimeError("cygpath is required to run Bash tests on Windows")
    cygpath = Path(cygpath_name).resolve()

    bash_candidates = [
        cygpath.with_name("bash.exe"),
        cygpath.parent.parent.parent / "bin" / "bash.exe",
    ]
    bash = next(
        (candidate for candidate in bash_candidates if candidate.is_file()), None
    )
    if bash is None:
        raise RuntimeError(
            f"Could not locate bash.exe for the MSYS installation containing {cygpath}"
        )

    def cygpath_to_posix(path: str) -> str:
        converted = subprocess.run(
            [str(cygpath), "-u", path],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        if not converted:
            raise RuntimeError(f"cygpath returned an empty path for {path}")
        return converted

    converted_env = dict(env)
    for name, value in converted_env.items():
        if value and name.endswith(("_FILE", "_DIR")):
            converted_env[name] = cygpath_to_posix(value)

    return [str(bash), cygpath_to_posix(str(script))], converted_env


def run_script(
    script: Path,
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    script_env = {**os.environ, **(env or {})}
    command = ["bash", str(script)]
    if os.name == "nt":
        command, script_env = _windows_bash_context(script, script_env)
    return subprocess.run(
        [*command, *args],
        cwd=cwd,
        env=script_env,
        text=True,
        capture_output=True,
        check=False,
    )


class ApplyServiceTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        scripts = root / "scripts"
        scripts.mkdir()
        script = scripts / "apply-service.sh"
        shutil.copy2(SERVICE_SCRIPT, script)
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        shutil.copy2(REPO / "scripts" / "settings.py", scripts / "settings.py")
        infra = root / "infra"
        infra.mkdir()
        shutil.copy2(REPO / "infra" / "services.json", infra / "services.json")

        run_infra = scripts / "run-infra.sh"
        run_infra.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env bash
                set -euo pipefail
                printf 'profile=%s\\n' "${BWS_RUNTIME_PROFILE:-}" >> "${RUN_CAPTURE_FILE}"
                printf 'copy=%s\\n' "${INFRA_COPY_SSH_KEYS:-}" >> "${RUN_CAPTURE_FILE}"
                exec "$@"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run_infra.chmod(run_infra.stat().st_mode | stat.S_IXUSR)

        (scripts / "apply-ansible-services.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                from pathlib import Path

                capture = Path(os.environ["APPLY_CAPTURE_FILE"])
                with capture.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(sys.argv[1:]) + "\\n")
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        run_capture = root / "run-infra.txt"
        apply_capture = root / "apply-ansible-services.jsonl"
        return script, run_capture, apply_capture

    def test_profiles_are_resolved_by_settings_and_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, run_capture, apply_capture = self.make_fixture(root)
            environment = {
                "RUN_CAPTURE_FILE": str(run_capture),
                "APPLY_CAPTURE_FILE": str(apply_capture),
                "VALUES_DIR": "values",
            }
            expected = {
                "technitium": "config",
                "seaweedfs_onramp": "seaweedfs",
                "onclave_onramp": "onclave",
                "freellmapi_onramp": "freellmapi",
            }

            for service in expected:
                result = run_script(script, service, cwd=root, env=environment)
                self.assertEqual(0, result.returncode, result.stderr)

            self.assertEqual(
                [
                    line
                    for line in run_capture.read_text(encoding="utf-8").splitlines()
                    if line.startswith("profile=")
                ],
                [f"profile={profile}" for profile in expected.values()],
            )
            self.assertEqual(
                ["copy=true"] * len(expected),
                [
                    line
                    for line in run_capture.read_text(encoding="utf-8").splitlines()
                    if line.startswith("copy=")
                ],
            )

            apply_arguments = [
                json.loads(line)
                for line in apply_capture.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(expected), len(apply_arguments))
            for service, arguments in zip(expected, apply_arguments):
                self.assertEqual(
                    [
                        "--mode",
                        "sequential",
                        "--service",
                        service,
                        "--inventory",
                        "values/ansible/inventory/local.yml",
                        "--inventory",
                        "infra/ansible/inventory/tfvars.py",
                    ],
                    arguments,
                )

            wrapper = SERVICE_SCRIPT.read_text(encoding="utf-8")
            self.assertNotRegex(wrapper, r"\bcase\s")
            for service in expected:
                self.assertNotIn(service, wrapper)

    def test_profile_resolution_failure_does_not_invoke_run_infra(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, run_capture, _ = self.make_fixture(root)
            result = run_script(
                script,
                "unknown-service",
                cwd=root,
                env={
                    "RUN_CAPTURE_FILE": str(run_capture),
                    "VALUES_DIR": "values",
                },
            )

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(run_capture.exists())

    def test_usage_requires_one_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, run_capture, _ = self.make_fixture(root)
            result = run_script(
                script,
                cwd=root,
                env={"RUN_CAPTURE_FILE": str(run_capture)},
            )

            self.assertEqual(2, result.returncode)
            self.assertIn("Usage:", result.stderr)
            self.assertFalse(run_capture.exists())


if __name__ == "__main__":
    unittest.main()

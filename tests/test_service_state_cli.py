from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVICE_SCRIPT = REPO / "scripts/service-state.sh"
HERMES_SCRIPT = REPO / "scripts/hermes-state.sh"


def run_script(script: Path, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=cwd or REPO,
        env={**os.environ, **(env or {})},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class ServiceStateCliTests(unittest.TestCase):
    def make_registry_fixture(self, root: Path) -> Path:
        scripts = root / "scripts"
        infra = root / "infra"
        scripts.mkdir()
        infra.mkdir()
        copied = scripts / "service-state.sh"
        shutil.copy2(SERVICE_SCRIPT, copied)
        (infra / "services.json").write_text(
            json.dumps(
                {
                    "services": {
                        "eligible": {
                            "state_capable": True,
                            "inventory": {"group": "eligible_group"},
                        },
                        "ineligible": {
                            "state_capable": False,
                            "inventory": {"group": "ineligible_group"},
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (scripts / "python.sh").write_text("#!/usr/bin/env bash\nexec python \"$@\"\n", encoding="utf-8")
        (scripts / "settings.py").write_text("print('eligible ineligible')\n", encoding="utf-8")
        (scripts / "run-infra.sh").write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"${CAPTURE_FILE}\"\n",
            encoding="utf-8",
        )
        for script in scripts.iterdir():
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return copied

    def test_registry_state_capability_drives_list_backup_all_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.make_registry_fixture(root)
            capture = root / "run-infra.txt"

            listed = run_script(script, "list", cwd=root)
            self.assertEqual(0, listed.returncode, listed.stderr)
            self.assertIn("  eligible", listed.stdout)
            self.assertNotIn("  ineligible", listed.stdout)

            backed_up = run_script(script, "backup", "all", cwd=root, env={"CAPTURE_FILE": str(capture)})
            self.assertEqual(0, backed_up.returncode, backed_up.stderr)
            self.assertIn("Backing up eligible service state", backed_up.stderr)
            self.assertNotIn("Backing up ineligible service state", backed_up.stderr)
            self.assertIn("service_state_service='eligible'", capture.read_text(encoding="utf-8"))

            rejected = run_script(script, "backup", "ineligible", cwd=root)
            self.assertEqual(2, rejected.returncode)
            self.assertIn("Unsupported service-state target: ineligible", rejected.stderr)

    def test_windows_backup_acl_hardening_is_fail_closed(self) -> None:
        script = SERVICE_SCRIPT.read_text(encoding="utf-8")
        compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
        playbook = (REPO / "infra/ansible/playbooks/service-state-backup.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("MSYS2_ARG_CONV_EXCL='*' icacls.exe", script)
        self.assertIn("/inheritance:r", script)
        self.assertIn("*S-1-5-18:(OI)(CI)F", script)
        self.assertIn("*S-1-5-32-544:(OI)(CI)F", script)
        self.assertIn('SERVICE_STATE_HOST_ACL_ENFORCED="${service_state_host_acl_enforced}"', script)
        self.assertIn("SERVICE_STATE_HOST_ACL_ENFORCED:", compose)
        self.assertIn("service_state_host_acl_enforced", playbook)
        self.assertIn("when: not service_state_host_acl_enforced", playbook)

    def test_list_behavior(self) -> None:
        result = run_script(SERVICE_SCRIPT, "list")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Supported service-state targets:", result.stdout)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            [
                "  hermes",
                "  forgejo",
                "  technitium",
                "  onramp_host",
                "  infisical_onramp",
                "  searxng_onramp",
            ],
        )

    def test_invalid_target_and_archive_are_rejected(self) -> None:
        target = run_script(SERVICE_SCRIPT, "restore", "unknown", "state.tar.gz")
        self.assertEqual(2, target.returncode)
        self.assertIn("Unsupported service-state target", target.stderr)

        archive = run_script(SERVICE_SCRIPT, "restore", "hermes", "elsewhere/state.tar.gz")
        self.assertEqual(2, archive.returncode)
        self.assertIn("Restore archive must be under", archive.stderr)

    def test_restore_if_present_missing_archive_is_a_noop(self) -> None:
        result = run_script(
            SERVICE_SCRIPT,
            "restore-if-present",
            "hermes",
            "values/service-backups/hermes/missing.tar.gz",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("skipping restore", result.stderr)

    def test_implicit_selection_excludes_pre_restore_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            infra = root / "infra"
            backup_dir = root / "values/service-backups/hermes"
            scripts.mkdir(parents=True)
            infra.mkdir()
            backup_dir.mkdir(parents=True)
            copied = scripts / "service-state.sh"
            shutil.copy2(SERVICE_SCRIPT, copied)
            shutil.copy2(REPO / "infra/services.json", infra / "services.json")
            (backup_dir / "hermes-state-pre-restore-20260101T000000Z.tar.gz").touch()

            result = run_script(copied, "restore-if-present", "hermes", cwd=root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("No hermes service-state archive found", result.stderr)

    def test_hermes_wrapper_delegation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            copied = scripts / "hermes-state.sh"
            shutil.copy2(HERMES_SCRIPT, copied)
            capture = root / "arguments.txt"
            delegate = scripts / "service-state.sh"
            delegate.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"${CAPTURE_FILE}\"\n",
                encoding="utf-8",
            )
            delegate.chmod(delegate.stat().st_mode | stat.S_IXUSR)

            result = run_script(
                copied,
                "restore",
                "values/service-backups/hermes/hermes-state-20260101T000000Z.tar.gz",
                cwd=root,
                env={"CAPTURE_FILE": str(capture)},
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                [
                    "restore",
                    "hermes",
                    "values/service-backups/hermes/hermes-state-20260101T000000Z.tar.gz",
                ],
                capture.read_text(encoding="utf-8").splitlines(),
            )


if __name__ == "__main__":
    unittest.main()

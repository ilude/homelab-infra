from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "infra/ansible/roles/technitium/files/validate-technitium-archive.py"
TASKS = ROOT / "infra/ansible/roles/technitium/tasks/main.yml"

spec = importlib.util.spec_from_file_location("technitium_archive_validator", VALIDATOR)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class TechnitiumArchiveValidatorTests(unittest.TestCase):
    def write_archive(self, path: Path, names: list[str]) -> None:
        runtime = json.dumps(
            {
                "runtimeOptions": {
                    "frameworks": [
                        {"name": "Microsoft.NETCore.App", "version": "10.0.0"},
                        {"name": "Microsoft.AspNetCore.App", "version": "10.0.0"},
                    ]
                }
            }
        ).encode()
        with tarfile.open(path, "w:gz") as archive:
            for name in names:
                content = runtime if name == "DnsServerApp.runtimeconfig.json" else b"fixture"
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))

    def test_accepts_verified_release_layout_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "release.tar.gz"
            self.write_archive(archive, sorted(validator.REQUIRED_FILES))
            validator.validate_archive(str(archive))

    def test_rejects_unsafe_archive_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "release.tar.gz"
            self.write_archive(archive, [*sorted(validator.REQUIRED_FILES), "../escape"])
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                validator.validate_archive(str(archive))

    def test_rejects_missing_required_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "release.tar.gz"
            self.write_archive(archive, ["DnsServerApp.dll"])
            with self.assertRaisesRegex(ValueError, "missing required files"):
                validator.validate_archive(str(archive))


class TechnitiumRoleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = TASKS.read_text(encoding="utf-8")

    def test_uses_versioned_verified_archive_without_upstream_installer(self) -> None:
        self.assertNotIn("install.sh", self.tasks)
        self.assertIn("/{{ technitium_discovery_version }}/DnsServerPortable.tar.gz", self.tasks)
        self.assertIn("checksum_algorithm: sha256", self.tasks)
        self.assertIn("technitium_staged_archive.stat.checksum != technitium_portable_sha256", self.tasks)

    def test_marker_match_gates_all_runtime_staging_and_activation(self) -> None:
        self.assertIn("technitium_installed_version.stdout | trim != technitium_discovery_version", self.tasks)
        self.assertIn("when: technitium_update_required | bool", self.tasks)
        self.assertIn("Record healthy managed Technitium version", self.tasks)

    def test_first_conversion_and_failed_health_rollback_are_explicit(self) -> None:
        self.assertIn("Retain upstream-installed application as initial rollback release", self.tasks)
        self.assertIn("releases/pre-managed", self.tasks)
        self.assertIn("rescue:", self.tasks)
        self.assertIn("Restore previous managed Technitium application link", self.tasks)
        self.assertIn("Restore Technitium state snapshot", self.tasks)
        self.assertIn("Verify rolled-back Technitium release", self.tasks)

    def test_activation_requires_inactive_service_before_link_change(self) -> None:
        activation = self.tasks.split("- name: Activate verified Technitium release with rollback", 1)[1]
        stop_and_verify = activation.split(
            "    - name: Replace previous Technitium state snapshot staging directory", 1
        )[0]
        self.assertIn("register: technitium_stop", stop_and_verify)
        self.assertIn("technitium_stop.status.ActiveState == 'inactive'", stop_and_verify)
        self.assertNotIn("failed_when: false", stop_and_verify)

    def test_state_is_outside_release_directories(self) -> None:
        self.assertIn("technitium_state_directory: /etc/dns", (TASKS.parent.parent / "defaults/main.yml").read_text(encoding="utf-8"))
        self.assertNotIn("{{ technitium_release_directory }}/etc/dns", self.tasks)


if __name__ == "__main__":
    unittest.main()

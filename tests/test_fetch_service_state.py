from __future__ import annotations

import importlib.util
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "ansible" / "scripts" / "fetch-service-state.py"
spec = importlib.util.spec_from_file_location("fetch_service_state", SCRIPT)
assert spec and spec.loader
fetch_service_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_service_state)


class FakeProcess:
    def __init__(self, payload: bytes, returncode: int = 0) -> None:
        self.stdout = io.BytesIO(payload)
        self.stderr = io.BytesIO(b"remote-private-detail")
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class FetchServiceStateTests(unittest.TestCase):
    def args(self, root: Path, output: str = "state.tar.gz") -> object:
        return fetch_service_state.parse_args([
            "--host", "192.0.2.71", "--user", "operator", "--remote-archive", "/tmp/hermes-state.tar.gz",
            "--output", str(root / output), "--backup-root", str(root),
        ])

    def test_stream_is_atomic_private_and_reports_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.args(root)
            with patch.object(fetch_service_state.subprocess, "Popen", return_value=FakeProcess(b"archive")):
                result = fetch_service_state.stream_archive(args)
            output = root / "state.tar.gz"
            self.assertEqual(output.read_bytes(), b"archive")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(result["bytes"], 7)
            self.assertEqual(result["sha256"], __import__("hashlib").sha256(b"archive").hexdigest())
            self.assertFalse(list(root.glob(".state.tar.gz.*")))

    def test_failed_stream_removes_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.args(root)
            with patch.object(fetch_service_state.subprocess, "Popen", return_value=FakeProcess(b"partial", 1)):
                with self.assertRaises(fetch_service_state.TransferError) as error:
                    fetch_service_state.stream_archive(args)
            self.assertNotIn("remote-private-detail", str(error.exception))
            self.assertFalse((root / "state.tar.gz").exists())
            self.assertFalse(list(root.glob(".state.tar.gz.*")))

    def test_ssh_command_uses_become_without_interpolating_archive_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = self.args(Path(temp))
            args.ssh_common_args = "-o BatchMode=yes -o StrictHostKeyChecking=no"
            args.become = True
            command = fetch_service_state.ssh_command(args)
        self.assertEqual(
            command,
            [
                "ssh",
                "-p",
                "22",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "operator@192.0.2.71",
                "sudo",
                "-n",
                "cat",
                "/tmp/hermes-state.tar.gz",
            ],
        )

    def test_rejects_unsafe_paths_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.args(root, "../escape.tar.gz")
            with patch.object(fetch_service_state.subprocess, "Popen") as popen:
                with self.assertRaises(fetch_service_state.TransferError):
                    fetch_service_state.stream_archive(args)
            popen.assert_not_called()

    def test_backup_playbook_uses_stream_digest_without_rereading_archive(self) -> None:
        backup = (SCRIPT.parents[1] / "playbooks" / "service-state-backup.yml").read_text(encoding="utf-8")
        self.assertIn("service_state_stream.stdout | from_json", backup)
        self.assertIn("service_state_checksum.sha256", backup)
        self.assertIn("- name: Create and stream service-state backup transaction\n      block:", backup)
        self.assertIn("      always:\n", backup)
        self.assertLess(backup.index("      always:"), backup.index("Record streamed service-state archive checksum"))
        self.assertNotIn("sha256sum", backup)


if __name__ == "__main__":
    unittest.main()

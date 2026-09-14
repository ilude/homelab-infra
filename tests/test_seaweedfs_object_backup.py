from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "seaweedfs-object-backup.py"
spec = importlib.util.spec_from_file_location("seaweedfs_object_backup", SCRIPT)
assert spec and spec.loader
backup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backup
try:
    spec.loader.exec_module(backup)
except ModuleNotFoundError:
    backup = None  # type: ignore[assignment]


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _Paginator:
    def paginate(self, **kwargs: object):
        del kwargs
        yield {"Contents": [{"Key": "objects/example"}]}


class _CleanupClient:
    def __init__(self) -> None:
        self.deleted_objects: list[str] = []
        self.deleted_buckets: list[str] = []

    def get_paginator(self, name: str) -> _Paginator:
        assert name == "list_objects_v2"
        return _Paginator()

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        assert Bucket == "menos-restore-test-abcdef"
        self.deleted_objects.append(Key)

    def delete_bucket(self, *, Bucket: str) -> None:
        self.deleted_buckets.append(Bucket)


class _Client:
    def get_paginator(self, name: str) -> _Paginator:
        assert name == "list_objects_v2"
        return _Paginator()

    def get_object(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["Bucket"] == "menos"
        assert kwargs["Key"] == "objects/example"
        return {
            "Body": _Body(b"payload"),
            "ContentType": "text/plain",
            "Metadata": {"source": "test"},
        }


@unittest.skipIf(backup is None, "boto3 is provided by the infra tooling container")
class SeaweedfsObjectBackupTests(unittest.TestCase):
    def test_backup_requires_orchestration_quiescence_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(backup.BackupError, "quiescence marker"):
                backup.backup(_Client(), "menos", Path(temp) / "backup.tar.gz")

    def test_backup_requires_a_fresh_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "quiesced"
            marker.touch()
            output = Path(temp) / "backup.tar.gz"
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(backup.BackupError, "overwrite existing"):
                backup.backup(_Client(), "menos", output, str(marker))

    def test_backup_manifest_is_an_exact_private_corpus_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "quiesced"
            marker.touch()
            output = Path(temp) / "backup.tar.gz"
            summary = backup.backup(_Client(), "menos", output, str(marker))
            self.assertEqual(summary["objects"], 1)
            with backup.tarfile.open(output, "r:gz") as archive:
                manifest = backup.json.loads(
                    archive.extractfile("MANIFEST.json").read()  # type: ignore[union-attr]
                )
            self.assertEqual(manifest["objects"][0]["key"], "objects/example")
            self.assertEqual(
                manifest["objects"][0]["sha256"], backup.hashlib.sha256(b"payload").hexdigest()
            )

    def test_restore_test_bucket_isolated_from_app_bucket(self) -> None:
        backup.validate_restore_bucket("menos-restore-test-abcdef")
        for bucket in ("menos", "other", "menos-restore"):
            with self.subTest(bucket=bucket), self.assertRaises(backup.BackupError):
                backup.validate_restore_bucket(bucket)

    def test_cleanup_deletes_only_a_bucket_created_by_the_restore_test(self) -> None:
        client = _CleanupClient()
        backup.cleanup_restore(client, "menos-restore-test-abcdef", False)
        self.assertEqual(client.deleted_objects, ["objects/example"])
        self.assertEqual(client.deleted_buckets, [])

        client = _CleanupClient()
        backup.cleanup_restore(client, "menos-restore-test-abcdef", True)
        self.assertEqual(client.deleted_objects, ["objects/example"])
        self.assertEqual(client.deleted_buckets, ["menos-restore-test-abcdef"])


if __name__ == "__main__":
    unittest.main()

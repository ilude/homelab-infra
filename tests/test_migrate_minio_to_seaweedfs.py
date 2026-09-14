from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate-minio-to-seaweedfs.py"
spec = importlib.util.spec_from_file_location("migrate_minio_to_seaweedfs", SCRIPT)
assert spec and spec.loader
migration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migration
try:
    spec.loader.exec_module(migration)
except ModuleNotFoundError:
    migration = None  # type: ignore[assignment]


@unittest.skipIf(migration is None, "boto3 is provided by the infra tooling container")
class MigrationSafetyTests(unittest.TestCase):
    def test_environment_flag_cannot_bypass_orchestration_quiescence(self) -> None:
        old = os.environ.get("ONCLAVE_MIGRATION_QUIESCED")
        os.environ["ONCLAVE_MIGRATION_QUIESCED"] = "1"
        try:
            with self.assertRaisesRegex(migration.MigrationError, "quiescence marker"):
                migration.require_quiescence(None)
        finally:
            if old is None:
                os.environ.pop("ONCLAVE_MIGRATION_QUIESCED", None)
            else:
                os.environ["ONCLAVE_MIGRATION_QUIESCED"] = old

    def test_finalize_artifact_must_be_new(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "parity.json"
            with self.assertRaisesRegex(migration.MigrationError, "new --artifact"):
                migration.require_fresh_artifact(None)
            path.touch()
            with self.assertRaisesRegex(migration.MigrationError, "overwrite existing"):
                migration.require_fresh_artifact(path)
            self.assertEqual(
                migration.require_fresh_artifact(Path(temp) / "new.json"), Path(temp) / "new.json"
            )

    def test_parity_uses_keys_bytes_and_digests_not_backend_inferred_mime_types(self) -> None:
        source = [
            {
                "key": "youtube/example/transcript.txt",
                "bytes": 12,
                "sha256": "a" * 64,
                "content_type": "application/octet-stream",
                "metadata": {},
            }
        ]
        destination = [
            {
                **source[0],
                "content_type": "text/plain; charset=utf-8",
            }
        ]

        self.assertTrue(migration.has_object_parity(source, destination))
        destination[0]["sha256"] = "b" * 64
        self.assertFalse(migration.has_object_parity(source, destination))


if __name__ == "__main__":
    unittest.main()

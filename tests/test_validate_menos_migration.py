from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "validate-menos-migration.py"
SPEC = importlib.util.spec_from_file_location("validate_menos_migration", SCRIPT)
assert SPEC and SPEC.loader
validate_menos_migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_menos_migration)

STAMP = "20260719T223202Z"


def migration_manifest(policy: str = "preserve_new_managed_single_principal") -> dict:
    return {
        "snapshot": STAMP,
        "legacy_deploy_path": "/apps/menos",
        "quiesce_started_at": "2026-07-19T22:32:06Z",
        "record_counts": {name: 0 for name in validate_menos_migration.TABLES},
        "minio": {
            "object_count": 1,
            "total_bytes": 4,
            "key_list_sha256": hashlib.sha256(b"object\n").hexdigest(),
        },
        "legacy_authorized_keys": {
            "migration_policy": policy,
            "unique_fingerprint_count": 5,
            "sorted_fingerprint_sha256": hashlib.sha256(b"fingerprints").hexdigest(),
        },
        "vector_index": "idx_chunk_embedding MTREE DIMENSION 1024 DIST COSINE",
    }


def make_archive(root: Path, *, policy: str = "preserve_new_managed_single_principal", extra_name: str | None = None) -> tuple[Path, Path]:
    archive = root / f"{STAMP}.tar.gz"
    files = {
        "authorized_keys": b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestMaterial test@example\n",
        "database.surql": b"CREATE content:test SET title = 'test';\n",
        "manifest.json": json.dumps({"backup_date": STAMP}).encode(),
        "migration-manifest.json": json.dumps(migration_manifest(policy)).encode(),
        "minio/menos/object/xl.meta": b"data",
    }
    checksums = "".join(f"{hashlib.sha256(data).hexdigest()}  ./{name}\n" for name, data in sorted(files.items()))
    files["SHA256SUMS"] = checksums.encode()
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{STAMP}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if extra_name:
            info = tarfile.TarInfo(extra_name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    sidecar = root / f"{archive.name}.sha256"
    sidecar.write_text(f"{validate_menos_migration.file_sha256(archive)}  /staging/{archive.name}\n", encoding="utf-8")
    return archive, sidecar


class ValidateMenosMigrationTests(unittest.TestCase):
    def test_accepts_valid_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive, sidecar = make_archive(Path(temp))
            manifest = validate_menos_migration.validate_archive(archive, sidecar, STAMP)
            self.assertEqual(manifest["minio"]["object_count"], 1)

    def test_rejects_unapproved_authorized_key_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive, sidecar = make_archive(Path(temp), policy="copy_all_legacy_keys")
            with self.assertRaisesRegex(ValueError, "authorized-key policy"):
                validate_menos_migration.validate_archive(archive, sidecar, STAMP)

    def test_rejects_archive_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive, sidecar = make_archive(Path(temp), extra_name=f"{STAMP}/../escape")
            with self.assertRaisesRegex(ValueError, "unsafe archive path"):
                validate_menos_migration.validate_archive(archive, sidecar, STAMP)

    def test_rejects_outer_archive_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive, sidecar = make_archive(Path(temp))
            sidecar.write_text(f"{'0' * 64}  /staging/{archive.name}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum does not match"):
                validate_menos_migration.validate_archive(archive, sidecar, STAMP)


if __name__ == "__main__":
    unittest.main()

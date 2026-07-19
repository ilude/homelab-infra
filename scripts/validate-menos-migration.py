#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

STAMP_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
TABLES = (
    "content",
    "chunk",
    "link",
    "content_entity",
    "entity",
    "pipeline_job",
    "llm_usage",
    "tag_alias",
)
REQUIRED_FILES = {
    "authorized_keys",
    "database.surql",
    "manifest.json",
    "migration-manifest.json",
    "SHA256SUMS",
}


class MigrationValidationError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sidecar(path: Path, archive: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) != 2 or Path(parts[1].lstrip("*")).name != archive.name:
        raise MigrationValidationError("archive checksum sidecar has an unexpected format")
    if not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
        raise MigrationValidationError("archive checksum sidecar does not contain SHA256")
    return parts[0]


def normalize_member(name: str, stamp: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise MigrationValidationError(f"unsafe archive path: {name}")
    parts = path.parts
    if not parts or parts[0] != stamp:
        raise MigrationValidationError(f"archive member is outside the timestamp root: {name}")
    return PurePosixPath(*parts[1:]).as_posix()


def parse_checksums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise MigrationValidationError("SHA256SUMS contains an invalid line")
        name = parts[1].lstrip("*")
        if name.startswith("./"):
            name = name[2:]
        if name in checksums:
            raise MigrationValidationError(f"SHA256SUMS contains a duplicate path: {name}")
        checksums[name] = parts[0]
    return checksums


def require_manifest_contract(manifest: Any, stamp: str) -> None:
    if not isinstance(manifest, dict):
        raise MigrationValidationError("migration manifest must be an object")
    if manifest.get("snapshot") != stamp:
        raise MigrationValidationError("migration manifest snapshot does not match archive stamp")
    counts = manifest.get("record_counts")
    if not isinstance(counts, dict) or set(counts) != set(TABLES):
        raise MigrationValidationError("migration manifest must contain exactly eight table counts")
    if any(not isinstance(counts[name], int) or counts[name] < 0 for name in TABLES):
        raise MigrationValidationError("migration manifest table counts must be non-negative integers")
    minio = manifest.get("minio")
    if not isinstance(minio, dict):
        raise MigrationValidationError("migration manifest MinIO summary is missing")
    if not isinstance(minio.get("object_count"), int) or minio["object_count"] < 0:
        raise MigrationValidationError("migration manifest MinIO object count is invalid")
    if not isinstance(minio.get("total_bytes"), int) or minio["total_bytes"] < 0:
        raise MigrationValidationError("migration manifest MinIO byte count is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(minio.get("key_list_sha256", ""))):
        raise MigrationValidationError("migration manifest MinIO key-list hash is invalid")
    keys = manifest.get("legacy_authorized_keys")
    if not isinstance(keys, dict) or keys.get("migration_policy") != "preserve_new_managed_single_principal":
        raise MigrationValidationError("migration manifest authorized-key policy is not approved")
    if "MTREE DIMENSION 1024 DIST COSINE" not in str(manifest.get("vector_index", "")):
        raise MigrationValidationError("migration manifest vector-index contract is invalid")


def validate_archive(archive: Path, sidecar: Path, stamp: str) -> dict[str, Any]:
    if not STAMP_RE.fullmatch(stamp):
        raise MigrationValidationError("migration stamp must be UTC YYYYMMDDTHHMMSSZ")
    if not archive.is_file() or not sidecar.is_file():
        raise MigrationValidationError("migration archive and checksum sidecar are required")
    if file_sha256(archive) != parse_sidecar(sidecar, archive):
        raise MigrationValidationError("migration archive checksum does not match")

    members: set[str] = set()
    file_hashes: dict[str, str] = {}
    payloads: dict[str, bytes] = {}
    minio_file_found = False
    database_nonempty = False
    captured_names = {"manifest.json", "migration-manifest.json", "SHA256SUMS"}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            relative = normalize_member(member.name, stamp)
            if relative in members:
                raise MigrationValidationError(f"archive contains a duplicate member: {relative}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise MigrationValidationError(f"archive contains an unsupported member: {member.name}")
            members.add(relative)
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                raise MigrationValidationError(f"archive member is not readable: {relative}")
            digest = hashlib.sha256()
            captured = bytearray()
            for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                digest.update(chunk)
                if relative in captured_names:
                    captured.extend(chunk)
            if relative != "SHA256SUMS":
                file_hashes[relative] = digest.hexdigest()
            if relative in captured_names:
                payloads[relative] = bytes(captured)
            minio_file_found = minio_file_found or relative.startswith("minio/")
            database_nonempty = database_nonempty or (relative == "database.surql" and member.size > 0)

    missing = REQUIRED_FILES - members
    if missing:
        raise MigrationValidationError(f"archive is missing required files: {', '.join(sorted(missing))}")
    if not minio_file_found:
        raise MigrationValidationError("archive does not contain MinIO snapshot files")
    if not database_nonempty:
        raise MigrationValidationError("SurrealDB export is empty")
    try:
        json.loads(payloads["manifest.json"])
        migration_manifest = json.loads(payloads["migration-manifest.json"])
        checksums = parse_checksums(payloads["SHA256SUMS"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationValidationError("archive manifest JSON is invalid") from error
    require_manifest_contract(migration_manifest, stamp)
    if set(checksums) != set(file_hashes):
        raise MigrationValidationError("SHA256SUMS does not cover exactly the snapshot files")
    for name, expected in checksums.items():
        if file_hashes[name] != expected:
            raise MigrationValidationError(f"snapshot member checksum mismatch: {name}")
    return migration_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a private Menos C1 migration archive.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--stamp", required=True)
    args = parser.parse_args()
    manifest = validate_archive(args.archive, args.checksum, args.stamp)
    print(
        "validated Menos migration archive: "
        f"{len(manifest['record_counts'])} tables, "
        f"{manifest['minio']['object_count']} objects"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

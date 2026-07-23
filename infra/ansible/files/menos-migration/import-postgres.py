#!/usr/bin/env python3
"""Validate and import a portable Menos snapshot into PostgreSQL and MinIO."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

TABLE_COLUMNS = {
    "content": (
        "id",
        "content_type",
        "title",
        "description",
        "mime_type",
        "file_size",
        "file_path",
        "author",
        "tags",
        "tier",
        "metadata",
        "classification_status",
        "classification_at",
        "classification_tier",
        "classification_score",
        "entity_extraction_status",
        "entity_extraction_at",
        "processing_status",
        "processed_at",
        "pipeline_version",
        "created_at",
        "updated_at",
    ),
    "chunk": ("id", "content_id", "text", "chunk_index", "embedding", "created_at"),
    "entity": (
        "id",
        "entity_type",
        "name",
        "normalized_name",
        "description",
        "hierarchy",
        "metadata",
        "created_at",
        "updated_at",
        "source",
    ),
    "content_entity": (
        "id",
        "content_id",
        "entity_id",
        "edge_type",
        "confidence",
        "mention_count",
        "source",
        "created_at",
    ),
    "link": ("id", "source", "target", "link_text", "link_type", "created_at"),
    "pipeline_job": (
        "id",
        "resource_key",
        "content_id",
        "status",
        "pipeline_version",
        "data_tier",
        "idempotency_key",
        "error_code",
        "error_message",
        "error_stage",
        "metadata",
        "created_at",
        "started_at",
        "finished_at",
    ),
    "llm_usage": (
        "id",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "input_price_per_million",
        "output_price_per_million",
        "estimated_cost",
        "context",
        "duration_ms",
        "pricing_snapshot_refreshed_at",
        "created_at",
    ),
    "tag_alias": ("id", "variant", "canonical", "usage_count", "updated_at"),
}
IMPORT_ORDER = (
    "content",
    "chunk",
    "entity",
    "content_entity",
    "link",
    "pipeline_job",
    "llm_usage",
    "tag_alias",
)
JSON_FIELDS = {"metadata"}
REFERENCE_FIELDS = {
    "chunk": {"content_id": "content"},
    "content_entity": {"content_id": "content", "entity_id": "entity"},
    "link": {"source": "content", "target": "content"},
    "pipeline_job": {"content_id": "content"},
}


def required_env(name: str, *fallbacks: str) -> str:
    for candidate in (name, *fallbacks):
        value = os.environ.get(candidate)
        if value:
            return value
    raise RuntimeError(f"missing required environment variable: {name}")


def _verify_archive_checksum(source: Path) -> None:
    checksum_path = source.with_name(source.name + ".sha256")
    if not checksum_path.is_file():
        raise ValueError("snapshot archive checksum is missing")
    parts = checksum_path.read_text(encoding="utf-8").strip().split(maxsplit=1)
    if len(parts) != 2 or parts[1].lstrip("*") != source.name:
        raise ValueError("invalid snapshot archive checksum")
    if sha256_file(source) != parts[0]:
        raise ValueError("snapshot archive checksum mismatch")


def _validate_archive_member(member: tarfile.TarInfo) -> PurePosixPath:
    path = PurePosixPath(member.name)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe archive path: {member.name}")
    unsupported = member.issym() or member.islnk() or member.isdev() or member.isfifo()
    if unsupported:
        raise ValueError(f"unsupported archive member: {member.name}")
    return path


def _validated_archive_members(
    archive: tarfile.TarFile,
) -> tuple[list[tarfile.TarInfo], str]:
    members = archive.getmembers()
    roots = {_validate_archive_member(member).parts[0] for member in members}
    if len(roots) != 1:
        raise ValueError("snapshot archive must contain one root directory")
    return members, next(iter(roots))


def _extract_archive_members(
    archive: tarfile.TarFile, members: list[tarfile.TarInfo], root: Path
) -> None:
    for member in members:
        relative = PurePosixPath(member.name)
        destination = root.joinpath(*relative.parts)
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        extracted = archive.extractfile(member)
        if extracted is None:
            raise ValueError(f"unreadable archive member: {member.name}")
        with destination.open("wb") as handle:
            shutil.copyfileobj(extracted, handle)


@contextmanager
def snapshot_directory(source: Path) -> Iterator[Path]:
    if source.is_dir():
        yield source
        return
    if not source.is_file():
        raise ValueError("snapshot path is missing")
    _verify_archive_checksum(source)
    with tempfile.TemporaryDirectory(prefix="menos-import-") as temporary:
        root = Path(temporary)
        with tarfile.open(source, "r:gz") as archive:
            members, snapshot_root = _validated_archive_members(archive)
            _extract_archive_members(archive, members, root)
        yield root / snapshot_root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe snapshot path: {name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"snapshot path escapes root: {name}")
    return path


def parse_checksums(snapshot: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in (snapshot / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError("invalid SHA256SUMS entry")
        name = parts[1].lstrip("*")
        if name in checksums:
            raise ValueError(f"duplicate checksum entry: {name}")
        checksums[name] = parts[0]
    return checksums


def _decode_row(table: str, line_number: int, line: str) -> dict[str, Any]:
    try:
        row = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {table} NDJSON at line {line_number}") from error
    if not isinstance(row, dict):
        raise ValueError(f"{table} line {line_number} is not an object")
    return row


def _validate_row_fields(table: str, row: dict[str, Any]) -> None:
    unknown = set(row) - set(TABLE_COLUMNS[table])
    if unknown:
        raise ValueError(
            f"{table} row contains unknown fields: {', '.join(sorted(unknown))}"
        )
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ValueError(f"{table} row has invalid id")


def _validate_chunk_embedding(table: str, row: dict[str, Any]) -> None:
    embedding = row.get("embedding")
    if table != "chunk" or embedding is None:
        return
    if not isinstance(embedding, list) or len(embedding) != 1024:
        raise ValueError("chunk embedding dimension is not 1024")
    valid = all(
        isinstance(value, (int, float)) and math.isfinite(value) for value in embedding
    )
    if not valid:
        raise ValueError("chunk embedding contains a non-finite value")


def read_rows(snapshot: Path, table: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with (snapshot / f"{table}.ndjson").open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            row = _decode_row(table, line_number, line)
            _validate_row_fields(table, row)
            _validate_chunk_embedding(table, row)
            rows.append(row)
    if len(rows) != len({row["id"] for row in rows}):
        raise ValueError(f"{table} contains duplicate ids")
    return rows


def local_object_inventory(snapshot: Path) -> list[tuple[str, int]]:
    root = snapshot / "minio"
    return sorted(
        (path.relative_to(root).as_posix(), path.stat().st_size)
        for path in root.rglob("*")
        if path.is_file()
    )


def key_hash(items: list[tuple[str, int]]) -> str:
    return hashlib.sha256(
        "".join(f"{key}\n" for key, _size in items).encode()
    ).hexdigest()


def _load_manifest(snapshot: Path) -> dict[str, Any]:
    if not snapshot.is_dir():
        raise ValueError("snapshot directory is missing")
    manifest_path = snapshot / "manifest.json"
    checksum_path = snapshot / "SHA256SUMS"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise ValueError("snapshot manifest and SHA256SUMS are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or manifest.get("vector_dimension") != 1024:
        raise ValueError("unsupported snapshot contract")
    return manifest


def _required_snapshot_files() -> set[str]:
    return {
        "manifest.json",
        "deduplication-report.json",
        "reference-repair-report.json",
    } | {f"{table}.ndjson" for table in IMPORT_ORDER}


def _snapshot_payload_files(snapshot: Path) -> set[str]:
    return {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }


def _validate_checksum_values(snapshot: Path, checksums: dict[str, str]) -> None:
    for name, expected in checksums.items():
        if sha256_file(safe_relative(snapshot, name)) != expected:
            raise ValueError(f"snapshot checksum mismatch: {name}")


def _validate_snapshot_checksums(snapshot: Path, manifest: dict[str, Any]) -> None:
    checksums = parse_checksums(snapshot)
    if not _required_snapshot_files().issubset(checksums):
        raise ValueError("snapshot checksums do not cover required files")
    if set(checksums) != _snapshot_payload_files(snapshot):
        raise ValueError("SHA256SUMS does not cover exactly the snapshot payload")
    _validate_checksum_values(snapshot, checksums)
    payload = {
        name: digest for name, digest in checksums.items() if name != "manifest.json"
    }
    if manifest.get("file_sha256") != payload:
        raise ValueError("manifest file checksums do not match SHA256SUMS")


def _validate_row_counts(
    manifest: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
) -> None:
    counts = {table: len(rows[table]) for table in IMPORT_ORDER}
    if manifest.get("record_counts") != counts:
        raise ValueError("snapshot record counts do not match NDJSON")


def _validate_references(rows: dict[str, list[dict[str, Any]]]) -> None:
    identifiers = {table: {row["id"] for row in items} for table, items in rows.items()}
    for table, fields in REFERENCE_FIELDS.items():
        for row in rows[table]:
            for field, target in fields.items():
                value = row.get(field)
                if value is not None and value not in identifiers[target]:
                    raise ValueError(f"unresolved reference {table}.{field}")


def _validate_deduplication(
    snapshot: Path,
    manifest: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> None:
    audit = json.loads(
        (snapshot / "deduplication-report.json").read_text(encoding="utf-8")
    )
    raw_count = audit.get("raw_count")
    unique_count = audit.get("unique_count")
    dropped = audit.get("dropped")
    if raw_count != manifest.get("content_entity_raw_count"):
        raise ValueError("deduplication raw count does not match manifest")
    if unique_count != len(rows["content_entity"]):
        raise ValueError("deduplication unique count does not match rows")
    if not isinstance(dropped, list) or raw_count - unique_count != len(dropped):
        raise ValueError("deduplication dropped count is inconsistent")
    edge_keys = {
        (row["content_id"], row["entity_id"], row["edge_type"])
        for row in rows["content_entity"]
    }
    if len(edge_keys) != unique_count:
        raise ValueError("content_entity uniqueness contract failed")


def _validate_chunk_repairs(
    chunk: dict[str, Any],
    source_counts: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> None:
    if chunk.get("raw_count") != source_counts.get("chunk"):
        raise ValueError("chunk repair raw count does not match source manifest")
    if chunk.get("import_count") != len(rows["chunk"]):
        raise ValueError("chunk repair import count does not match rows")
    dropped = chunk.get("dropped")
    if not isinstance(dropped, list) or chunk.get("dropped_count") != len(dropped):
        raise ValueError("chunk repair dropped count is inconsistent")


def _validate_job_repairs(
    jobs: dict[str, Any],
    source_counts: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> None:
    if jobs.get("raw_count") != source_counts.get("pipeline_job"):
        raise ValueError("pipeline job repair raw count does not match source manifest")
    if jobs.get("import_count") != len(rows["pipeline_job"]):
        raise ValueError("pipeline job repair import count does not match rows")
    dropped = jobs.get("dropped")
    if not isinstance(dropped, list) or jobs.get("dropped_count") != len(dropped):
        raise ValueError("pipeline job dropped count is inconsistent")
    if jobs.get("raw_count") - jobs.get("import_count") != len(dropped):
        raise ValueError("pipeline job dropped rows do not match import count")


def _validate_reference_repairs(
    snapshot: Path,
    manifest: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
) -> None:
    report = json.loads(
        (snapshot / "reference-repair-report.json").read_text(encoding="utf-8")
    )
    chunk = report.get("chunk", {})
    jobs = report.get("pipeline_job", {})
    source_counts = manifest.get("source_record_counts", {})
    _validate_chunk_repairs(chunk, source_counts, rows)
    _validate_job_repairs(jobs, source_counts, rows)
    summary = {
        "chunk_dropped_count": chunk.get("dropped_count"),
        "pipeline_job_dropped_count": jobs.get("dropped_count"),
    }
    if manifest.get("reference_repairs") != summary:
        raise ValueError("reference repair summary does not match manifest")


def _validate_minio(snapshot: Path, manifest: dict[str, Any]) -> None:
    objects = local_object_inventory(snapshot)
    expected = manifest.get("minio", {})
    actual = {
        "object_count": len(objects),
        "total_bytes": sum(size for _key, size in objects),
        "key_list_sha256": key_hash(objects),
    }
    if actual != expected:
        raise ValueError("snapshot MinIO inventory does not match manifest")


def validate_snapshot(
    snapshot: Path,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest = _load_manifest(snapshot)
    _validate_snapshot_checksums(snapshot, manifest)
    rows = {table: read_rows(snapshot, table) for table in IMPORT_ORDER}
    _validate_row_counts(manifest, rows)
    _validate_reference_repairs(snapshot, manifest, rows)
    _validate_references(rows)
    _validate_deduplication(snapshot, manifest, rows)
    _validate_minio(snapshot, manifest)
    return manifest, rows


def postgres_connection() -> Any:
    import psycopg

    return psycopg.connect(
        host=required_env("POSTGRES_HOST"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        dbname=required_env("POSTGRES_DATABASE"),
    )


def postgres_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in JSON_FIELDS:
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    if field == "embedding":
        return "[" + ",".join(format(float(item), ".17g") for item in value) + "]"
    return value


def _pricing_seed_count(cursor: Any) -> int:
    cursor.execute("SELECT count(*) FROM llm_pricing_snapshot")
    return int(cursor.fetchone()[0])


def _validate_import_target(cursor: Any) -> None:
    cursor.execute(
        "SELECT to_regclass('schema_migration') IS NOT NULL AS migrated, "
        "to_regclass('content') IS NOT NULL AS schema_ready"
    )
    migrated, schema_ready = cursor.fetchone()
    if not migrated or not schema_ready:
        raise RuntimeError("PostgreSQL schema migrations must run before import")
    cursor.execute(
        "SELECT "
        + "+".join(f"(SELECT count(*) FROM {table})" for table in IMPORT_ORDER)
    )
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("PostgreSQL import target is not empty")
    if _pricing_seed_count(cursor) != 1:
        raise RuntimeError(
            "PostgreSQL target must contain exactly one managed pricing seed"
        )


def _insert_rows(cursor: Any, rows: dict[str, list[dict[str, Any]]]) -> None:
    from psycopg import sql

    for table in IMPORT_ORDER:
        columns = TABLE_COLUMNS[table]
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _column in columns),
        )
        values = [
            tuple(postgres_value(field, row.get(field)) for field in columns)
            for row in rows[table]
        ]
        if values:
            cursor.executemany(statement, values)


def _analyze_imported_tables(connection: Any) -> None:
    from psycopg import sql

    with connection.cursor() as cursor:
        for table in IMPORT_ORDER:
            cursor.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(table)))


def import_database(rows: dict[str, list[dict[str, Any]]]) -> None:
    with postgres_connection() as connection:
        with connection.transaction(), connection.cursor() as cursor:
            _validate_import_target(cursor)
            _insert_rows(cursor, rows)
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            if _pricing_seed_count(cursor) != 1:
                raise RuntimeError("managed pricing seed changed during import")
        _analyze_imported_tables(connection)


def destination_client() -> Any:
    from minio import Minio

    return Minio(
        required_env("DEST_S3_ENDPOINT", "S3_ENDPOINT_URL"),
        access_key=required_env("DEST_S3_ACCESS_KEY", "S3_ACCESS_KEY"),
        secret_key=required_env("DEST_S3_SECRET_KEY", "S3_SECRET_KEY"),
        secure=os.environ.get("DEST_S3_SECURE", "false").lower() == "true",
        region=os.environ.get("DEST_S3_REGION", "us-east-1"),
    )


def remote_inventory(client: Any, bucket: str) -> list[tuple[str, int]]:
    return sorted(
        (str(item.object_name), int(item.size or 0))
        for item in client.list_objects(bucket, recursive=True)
    )


def import_objects(snapshot: Path) -> None:
    client = destination_client()
    bucket = required_env("S3_BUCKET")
    if client.bucket_exists(bucket):
        if remote_inventory(client, bucket):
            raise RuntimeError("MinIO import target bucket is not empty")
    else:
        client.make_bucket(bucket)
    expected = local_object_inventory(snapshot)
    for key, _size in expected:
        client.fput_object(bucket, key, str(safe_relative(snapshot / "minio", key)))
    if remote_inventory(client, bucket) != expected:
        raise RuntimeError("destination MinIO inventory does not match snapshot")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a portable Menos snapshot.")
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    with snapshot_directory(args.snapshot) as snapshot:
        manifest, rows = validate_snapshot(snapshot)
        import_database(rows)
        import_objects(snapshot)
        print(
            f"import_verified=true records={sum(manifest['record_counts'].values())} "
            f"objects={manifest['minio']['object_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

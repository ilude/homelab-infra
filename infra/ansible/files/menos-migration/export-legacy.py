#!/usr/bin/env python3
"""Export legacy Menos state to deterministic typed NDJSON and object files."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import shutil
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

TABLES = (
    "content",
    "chunk",
    "entity",
    "content_entity",
    "link",
    "pipeline_job",
    "llm_usage",
    "tag_alias",
)
REFERENCE_FIELDS = {
    "chunk": {"content_id": "content"},
    "content_entity": {"content_id": "content", "entity_id": "entity"},
    "link": {"source": "content", "target": "content"},
    "pipeline_job": {"content_id": "content"},
}
TIMESTAMP_FIELDS = {
    "classification_at",
    "entity_extraction_at",
    "processed_at",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "pricing_snapshot_refreshed_at",
}
REQUIRED_FIELDS = {
    "content": {
        "id",
        "content_type",
        "mime_type",
        "file_size",
        "file_path",
        "created_at",
        "updated_at",
    },
    "chunk": {"id", "content_id", "text", "chunk_index", "created_at"},
    "entity": {
        "id",
        "entity_type",
        "name",
        "normalized_name",
        "created_at",
        "updated_at",
        "source",
    },
    "content_entity": {
        "id",
        "content_id",
        "entity_id",
        "edge_type",
        "source",
        "created_at",
    },
    "link": {"id", "source", "link_text", "link_type", "created_at"},
    "pipeline_job": {
        "id",
        "resource_key",
        "content_id",
        "status",
        "pipeline_version",
        "created_at",
    },
    "llm_usage": {
        "id",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "context",
        "duration_ms",
        "created_at",
    },
    "tag_alias": {"id", "variant", "canonical", "usage_count", "updated_at"},
}
OPTIONAL_FIELDS = {
    "content": {
        "title",
        "description",
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
    },
    "chunk": {"embedding"},
    "entity": {"description", "hierarchy", "metadata"},
    "content_entity": {"confidence", "mention_count"},
    "link": {"target"},
    "pipeline_job": {
        "data_tier",
        "idempotency_key",
        "error_code",
        "error_message",
        "error_stage",
        "metadata",
        "started_at",
        "finished_at",
    },
    "llm_usage": {
        "input_price_per_million",
        "output_price_per_million",
        "estimated_cost",
        "pricing_snapshot_refreshed_at",
    },
    "tag_alias": set(),
}


def required_env(name: str, *fallbacks: str) -> str:
    for candidate in (name, *fallbacks):
        value = os.environ.get(candidate)
        if value:
            return value
    raise RuntimeError(f"missing required environment variable: {name}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_parts(value: Any) -> tuple[Any, Any]:
    if not isinstance(value, dict):
        return None, None
    table = value.get("tb", value.get("table"))
    identifier = value.get("id")
    if isinstance(identifier, dict):
        identifier = identifier.get("String", identifier.get("string"))
    return table, identifier


def _text_record_id(value: Any, expected_table: str) -> str:
    text = str(value)
    prefix = f"{expected_table}:"
    if text.startswith(prefix):
        text = text[len(prefix) :]
    text = text.strip("`\u27e8\u27e9")
    if not text or ":" in text:
        raise ValueError(f"invalid {expected_table} record reference")
    return text


def record_id(value: Any, expected_table: str) -> str:
    table, identifier = _record_parts(value)
    if table is not None and str(table) != expected_table:
        raise ValueError(f"expected {expected_table} record reference")
    if identifier is not None:
        return str(identifier)
    return _text_record_id(value, expected_table)


def utc_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("Datetime") or value.get("datetime") or value.get("value")
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _is_record_reference(value: dict[Any, Any]) -> bool:
    return "id" in value and bool({"tb", "table"} & value.keys())


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        if _is_record_reference(value):
            table = str(value.get("tb", value.get("table")))
            return record_id(value, table)
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    return value


def _normalize_references(
    table: str, source: dict[str, Any], row: dict[str, Any]
) -> None:
    for field, target in REFERENCE_FIELDS.get(table, {}).items():
        value = source.get(field)
        if value is not None:
            row[field] = record_id(value, target)
        elif field != "target":
            raise ValueError(f"{table}.{field} is required")


def _normalize_timestamps(row: dict[str, Any]) -> None:
    for field in TIMESTAMP_FIELDS & row.keys():
        row[field] = utc_timestamp(row[field])


def _validate_string_arrays(table: str, row: dict[str, Any]) -> None:
    for field in ("tags", "hierarchy"):
        value = row.get(field)
        if value is not None and (
            not isinstance(value, list)
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError(f"{table}.{field} must be a string array")


def _apply_defaults(table: str, row: dict[str, Any]) -> None:
    if table == "content":
        row.setdefault("tags", [])
    if table in {"content", "entity", "pipeline_job"}:
        row.setdefault("metadata", {})
    if table == "pipeline_job":
        row.setdefault("data_tier", "compact")
    if "metadata" in row and row["metadata"] is None:
        row["metadata"] = {}


def _normalize_embedding(table: str, row: dict[str, Any]) -> None:
    embedding = row.get("embedding")
    if table != "chunk" or embedding is None:
        return
    if not isinstance(embedding, list) or len(embedding) != 1024:
        raise ValueError("chunk.embedding must contain exactly 1024 values")
    normalized = [float(value) for value in embedding]
    if not all(math.isfinite(value) for value in normalized):
        raise ValueError("chunk.embedding contains a non-finite value")
    row["embedding"] = normalized


def _validate_required(table: str, row: dict[str, Any]) -> None:
    missing = sorted(
        field for field in REQUIRED_FIELDS[table] if row.get(field) is None
    )
    if missing:
        raise ValueError(
            f"{table} row is missing required fields: {', '.join(missing)}"
        )


def normalize_row(table: str, source: dict[str, Any]) -> dict[str, Any]:
    allowed = REQUIRED_FIELDS[table] | OPTIONAL_FIELDS[table]
    row = {
        str(key): normalize_json(value)
        for key, value in source.items()
        if str(key) in allowed
    }
    row["id"] = record_id(source.get("id"), table)
    _normalize_references(table, source, row)
    _normalize_timestamps(row)
    _validate_string_arrays(table, row)
    _apply_defaults(table, row)
    _normalize_embedding(table, row)
    _validate_required(table, row)
    return row


def deduplicate_relationships(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["content_id"], row["entity_id"], str(row["edge_type"]))
        groups.setdefault(key, []).append(row)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    for key in sorted(groups):
        candidates = sorted(
            groups[key],
            key=lambda row: (
                -(
                    float(row["confidence"])
                    if row.get("confidence") is not None
                    else -1.0
                ),
                str(row.get("created_at") or "9999-12-31T23:59:59Z"),
                row["id"],
            ),
        )
        winner = candidates[0]
        kept.append(winner)
        dropped.extend(
            {"id": row["id"], "kept_id": winner["id"]} for row in candidates[1:]
        )
    kept.sort(key=lambda row: row["id"])
    return kept, {"raw_count": len(rows), "unique_count": len(kept), "dropped": dropped}


def _chunk_signature(row: dict[str, Any]) -> tuple[int, str, str]:
    embedding = canonical_json(row.get("embedding"))
    embedding_hash = hashlib.sha256(embedding.encode()).hexdigest()
    return int(row["chunk_index"]), str(row["text"]), embedding_hash


def _repair_orphan_chunks(
    rows: dict[str, list[dict[str, Any]]], content_ids: set[str]
) -> dict[str, Any]:
    candidates: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for row in rows["chunk"]:
        if row["content_id"] in content_ids:
            candidates.setdefault(_chunk_signature(row), []).append(row)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    for row in rows["chunk"]:
        if row["content_id"] in content_ids:
            kept.append(row)
            continue
        matches = candidates.get(_chunk_signature(row), [])
        match_content_ids = {match["content_id"] for match in matches}
        if len(match_content_ids) != 1:
            raise ValueError(
                f"unresolved reference chunk.content_id={row['content_id']}"
            )
        winner = min(matches, key=lambda match: match["id"])
        dropped.append(
            {
                "id": row["id"],
                "missing_content_id": row["content_id"],
                "duplicate_content_id": winner["content_id"],
                "duplicate_chunk_id": winner["id"],
            }
        )
    rows["chunk"] = kept
    return {
        "raw_count": len(kept) + len(dropped),
        "import_count": len(kept),
        "dropped_count": len(dropped),
        "dropped": dropped,
    }


def _repair_orphan_jobs(
    rows: dict[str, list[dict[str, Any]]], content_ids: set[str]
) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    for row in rows["pipeline_job"]:
        if row["content_id"] in content_ids:
            kept.append(row)
            continue
        if row.get("status") != "failed" or dropped:
            raise ValueError(
                f"unresolved reference pipeline_job.content_id={row['content_id']}"
            )
        dropped.append(
            {
                "id": row["id"],
                "missing_content_id": row["content_id"],
                "status": row["status"],
            }
        )
    rows["pipeline_job"] = kept
    return {
        "raw_count": len(kept) + len(dropped),
        "import_count": len(kept),
        "dropped_count": len(dropped),
        "dropped": dropped,
    }


def repair_orphan_references(
    rows: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    content_ids = {row["id"] for row in rows["content"]}
    return {
        "policy": "drop_exact_duplicate_orphan_chunks_and_single_failed_orphan_job",
        "chunk": _repair_orphan_chunks(rows, content_ids),
        "pipeline_job": _repair_orphan_jobs(rows, content_ids),
    }


def validate_references(rows: dict[str, list[dict[str, Any]]]) -> None:
    identifiers = {table: {row["id"] for row in items} for table, items in rows.items()}
    for table, references in REFERENCE_FIELDS.items():
        for row in rows[table]:
            for field, target in references.items():
                value = row.get(field)
                if value is not None and value not in identifiers[target]:
                    raise ValueError(f"unresolved reference {table}.{field}={value}")


def legacy_sql_endpoint(url: str) -> str:
    endpoint = url.rstrip("/")
    if endpoint.startswith("ws://"):
        endpoint = "http://" + endpoint.removeprefix("ws://")
    elif endpoint.startswith("wss://"):
        endpoint = "https://" + endpoint.removeprefix("wss://")
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("SURREALDB_URL must use ws, wss, http, or https")
    return endpoint + "/sql"


def query_legacy(table: str) -> list[dict[str, Any]]:
    endpoint = legacy_sql_endpoint(required_env("SURREALDB_URL"))
    namespace = required_env("SURREALDB_NAMESPACE")
    database = required_env("SURREALDB_DATABASE")
    user = required_env("SURREALDB_USER")
    password = required_env("SURREALDB_PASSWORD")
    request = urllib.request.Request(
        endpoint,
        data=f"SELECT * FROM {table} ORDER BY id;".encode(),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "text/plain",
            "Surreal-NS": namespace,
            "Surreal-DB": database,
            "Authorization": "Basic "
            + base64.b64encode(f"{user}:{password}".encode()).decode(),
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        payload = json.load(response)
    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or payload[0].get("status") != "OK"
    ):
        raise RuntimeError(f"legacy read failed for table {table}")
    result = payload[0].get("result")
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise RuntimeError(f"legacy response for table {table} is not a row list")
    return result


def safe_object_path(root: Path, key: str) -> Path:
    relative = PurePosixPath(key)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("unsafe object key")
    destination = root.joinpath(*relative.parts)
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("object key escapes snapshot root")
    return destination


def export_objects(output: Path) -> dict[str, Any]:
    from minio import Minio

    endpoint = required_env("SOURCE_S3_ENDPOINT", "MINIO_URL")
    endpoint_secure = endpoint.startswith("https://")
    endpoint = endpoint.removeprefix("http://").removeprefix("https://")
    bucket = required_env("S3_BUCKET", "MINIO_BUCKET")
    client = Minio(
        endpoint,
        access_key=required_env("SOURCE_S3_ACCESS_KEY", "MINIO_ACCESS_KEY"),
        secret_key=required_env("SOURCE_S3_SECRET_KEY", "MINIO_SECRET_KEY"),
        secure=os.environ.get("SOURCE_S3_SECURE", str(endpoint_secure)).lower()
        == "true",
        region=os.environ.get("SOURCE_S3_REGION", "us-east-1"),
    )
    object_root = output / "minio"
    inventory: list[tuple[str, int]] = []
    for item in sorted(
        client.list_objects(bucket, recursive=True),
        key=lambda value: str(value.object_name),
    ):
        key = str(item.object_name)
        size = int(item.size or 0)
        destination = safe_object_path(object_root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = client.get_object(bucket, key)
        try:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        finally:
            response.close()
            response.release_conn()
        if destination.stat().st_size != size:
            raise RuntimeError(f"object size changed during export: {key}")
        inventory.append((key, size))
    key_list = "".join(f"{key}\n" for key, _size in inventory).encode()
    return {
        "object_count": len(inventory),
        "total_bytes": sum(size for _key, size in inventory),
        "key_list_sha256": hashlib.sha256(key_list).hexdigest(),
    }


def _load_rows() -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
    dict[str, Any],
    dict[str, int],
]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES:
        rows[table] = [normalize_row(table, row) for row in query_legacy(table)]
        rows[table].sort(key=lambda row: row["id"])
    source_counts = {table: len(rows[table]) for table in TABLES}
    rows["content_entity"], dedup_audit = deduplicate_relationships(
        rows["content_entity"]
    )
    repair_audit = repair_orphan_references(rows)
    validate_references(rows)
    return rows, dedup_audit, repair_audit, source_counts


def _write_rows(
    output: Path,
    rows: dict[str, list[dict[str, Any]]],
    dedup_audit: dict[str, Any],
    repair_audit: dict[str, Any],
) -> None:
    for table, items in rows.items():
        path = output / f"{table}.ndjson"
        path.write_text(
            "".join(canonical_json(row) + "\n" for row in items), encoding="utf-8"
        )
    (output / "deduplication-report.json").write_text(
        canonical_json(dedup_audit) + "\n", encoding="utf-8"
    )
    (output / "reference-repair-report.json").write_text(
        canonical_json(repair_audit) + "\n", encoding="utf-8"
    )


def _payload_paths(output: Path) -> list[Path]:
    return sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}
    )


def _write_snapshot_checksums(output: Path, payload_paths: list[Path]) -> None:
    manifest_path = output / "manifest.json"
    checksum_paths = [*payload_paths, manifest_path]
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n"
            for path in checksum_paths
        ),
        encoding="utf-8",
    )


def write_snapshot(output: Path, source_revision: str) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    rows, dedup_audit, repair_audit, source_counts = _load_rows()
    _write_rows(output, rows, dedup_audit, repair_audit)
    minio = export_objects(output)
    payload_paths = _payload_paths(output)
    checksums = {
        path.relative_to(output).as_posix(): sha256_file(path) for path in payload_paths
    }
    manifest = {
        "format_version": 1,
        "source_revision": source_revision,
        "source_record_counts": source_counts,
        "record_counts": {table: len(rows[table]) for table in TABLES},
        "content_entity_raw_count": dedup_audit["raw_count"],
        "reference_repairs": {
            "chunk_dropped_count": repair_audit["chunk"]["dropped_count"],
            "pipeline_job_dropped_count": repair_audit["pipeline_job"]["dropped_count"],
        },
        "vector_dimension": 1024,
        "minio": minio,
        "file_sha256": checksums,
    }
    (output / "manifest.json").write_text(
        canonical_json(manifest) + "\n", encoding="utf-8"
    )
    _write_snapshot_checksums(output, payload_paths)
    return manifest


def create_archive(snapshot: Path, archive: Path) -> None:
    if archive.exists():
        raise ValueError("snapshot archive already exists")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
    ):
        with tarfile.open(fileobj=compressed, mode="w") as package:
            for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
                relative = path.relative_to(snapshot).as_posix()
                info = tarfile.TarInfo(f"{snapshot.name}/{relative}")
                info.size = path.stat().st_size
                info.mode = 0o600
                info.mtime = 0
                with path.open("rb") as handle:
                    package.addfile(info, handle)
    archive.with_name(archive.name + ".sha256").write_text(
        f"{sha256_file(archive)}  {archive.name}\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export legacy Menos into a portable snapshot."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    manifest = write_snapshot(args.output, args.source_revision)
    if args.archive is not None:
        create_archive(args.output, args.archive)
    print(
        f"export_verified=true tables={len(TABLES)} objects={manifest['minio']['object_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

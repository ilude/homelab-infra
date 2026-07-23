from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MIGRATION_DIR = REPO / "infra" / "ansible" / "files" / "menos-migration"
EXPORTER = MIGRATION_DIR / "export-legacy.py"
IMPORTER = MIGRATION_DIR / "import-postgres.py"
PLAYBOOK = REPO / "infra" / "ansible" / "playbooks" / "migrate-menos-onramp.yml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = load_module("export_legacy", EXPORTER)
importer = load_module("import_postgres", IMPORTER)


def fixture_rows() -> dict[str, list[dict]]:
    timestamp = "2026-01-01T00:00:00Z"
    return {
        "content": [
            {
                "id": "content-1",
                "content_type": "video",
                "mime_type": "text/plain",
                "file_size": 1,
                "file_path": "content/content-1.txt",
                "tags": [],
                "metadata": {},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        ],
        "chunk": [
            {
                "id": "chunk-1",
                "content_id": "content-1",
                "text": "example",
                "chunk_index": 0,
                "embedding": [0.0] * 1024,
                "created_at": timestamp,
            }
        ],
        "entity": [
            {
                "id": "entity-1",
                "entity_type": "topic",
                "name": "Example",
                "normalized_name": "example",
                "metadata": {},
                "created_at": timestamp,
                "updated_at": timestamp,
                "source": "ai_extracted",
            }
        ],
        "content_entity": [
            {
                "id": "edge-1",
                "content_id": "content-1",
                "entity_id": "entity-1",
                "edge_type": "mentions",
                "confidence": 0.9,
                "source": "ai_extracted",
                "created_at": timestamp,
            }
        ],
        "link": [],
        "pipeline_job": [
            {
                "id": "job-1",
                "resource_key": "example",
                "content_id": "content-1",
                "status": "completed",
                "pipeline_version": "v1",
                "data_tier": "compact",
                "metadata": {},
                "created_at": timestamp,
            }
        ],
        "llm_usage": [],
        "tag_alias": [
            {
                "id": "alias-1",
                "variant": "example",
                "canonical": "examples",
                "usage_count": 1,
                "updated_at": timestamp,
            }
        ],
    }


def snapshot_row_counts(rows: dict[str, list[dict]]) -> dict[str, int]:
    return {table: len(rows[table]) for table in importer.IMPORT_ORDER}


def write_snapshot(root: Path) -> None:
    rows = fixture_rows()
    row_counts = snapshot_row_counts(rows)
    for table in importer.IMPORT_ORDER:
        (root / f"{table}.ndjson").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows[table]),
            encoding="utf-8",
        )
    (root / "deduplication-report.json").write_text(
        '{"dropped":[],"raw_count":1,"unique_count":1}\n', encoding="utf-8"
    )
    (root / "reference-repair-report.json").write_text(
        json.dumps(
            {
                "policy": "drop_exact_duplicate_orphan_chunks_and_single_failed_orphan_job",
                "chunk": {
                    "raw_count": 1,
                    "import_count": 1,
                    "dropped_count": 0,
                    "dropped": [],
                },
                "pipeline_job": {
                    "raw_count": 1,
                    "import_count": 1,
                    "dropped_count": 0,
                    "dropped": [],
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "minio").mkdir()
    payloads = sorted(path for path in root.rglob("*") if path.is_file())
    file_hashes = {
        path.relative_to(root).as_posix(): importer.sha256_file(path)
        for path in payloads
    }
    manifest = {
        "format_version": 1,
        "source_revision": "source-revision",
        "source_record_counts": row_counts,
        "record_counts": row_counts,
        "content_entity_raw_count": 1,
        "reference_repairs": {
            "chunk_dropped_count": 0,
            "pipeline_job_dropped_count": 0,
        },
        "vector_dimension": 1024,
        "minio": {
            "object_count": 0,
            "total_bytes": 0,
            "key_list_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "file_sha256": file_hashes,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    payloads.append(manifest_path)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{importer.sha256_file(path)}  {path.relative_to(root).as_posix()}\n"
            for path in payloads
        ),
        encoding="utf-8",
    )


class MenosMigrationTests(unittest.TestCase):
    def test_legacy_sql_endpoint_normalizes_websocket_urls(self) -> None:
        self.assertEqual(
            exporter.legacy_sql_endpoint("ws://legacy.example:8000"),
            "http://legacy.example:8000/sql",
        )
        self.assertEqual(
            exporter.legacy_sql_endpoint("wss://legacy.example/rpc"),
            "https://legacy.example/rpc/sql",
        )
        with self.assertRaisesRegex(ValueError, "ws, wss, http, or https"):
            exporter.legacy_sql_endpoint("legacy.example:8000")

    def test_normalizes_record_ids_timestamps_and_vectors(self) -> None:
        row = {
            "id": "chunk:chunk-1",
            "content_id": {"tb": "content", "id": "content-1"},
            "text": "example",
            "chunk_index": 0,
            "embedding": [0] * 1024,
            "created_at": "2026-01-01T01:00:00+01:00",
            "ignored_legacy_field": "discarded",
        }

        normalized = exporter.normalize_row("chunk", row)

        self.assertEqual(normalized["id"], "chunk-1")
        self.assertEqual(normalized["content_id"], "content-1")
        self.assertEqual(normalized["created_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(len(normalized["embedding"]), 1024)
        self.assertNotIn("ignored_legacy_field", normalized)

    def test_rejects_wrong_vector_dimension_and_unresolved_references(self) -> None:
        row = {
            "id": "chunk:chunk-1",
            "content_id": "content:missing",
            "text": "example",
            "chunk_index": 0,
            "embedding": [0.0],
            "created_at": "2026-01-01T00:00:00Z",
        }
        with self.assertRaisesRegex(ValueError, "1024"):
            exporter.normalize_row("chunk", row)

        rows = {table: [] for table in exporter.TABLES}
        row["embedding"] = [0.0] * 1024
        rows["chunk"] = [exporter.normalize_row("chunk", row)]
        with self.assertRaisesRegex(ValueError, "unresolved reference"):
            exporter.validate_references(rows)

    def test_deduplicates_relationships_by_approved_order(self) -> None:
        base = {
            "content_id": "content-1",
            "entity_id": "entity-1",
            "edge_type": "mentions",
            "source": "ai_extracted",
        }
        rows = [
            {
                **base,
                "id": "low",
                "confidence": 0.7,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                **base,
                "id": "late",
                "confidence": 0.9,
                "created_at": "2026-02-01T00:00:00Z",
            },
            {
                **base,
                "id": "winner",
                "confidence": 0.9,
                "created_at": "2026-01-01T00:00:00Z",
            },
        ]

        kept, audit = exporter.deduplicate_relationships(rows)

        self.assertEqual([row["id"] for row in kept], ["winner"])
        self.assertEqual(audit["raw_count"], 3)
        self.assertEqual(audit["unique_count"], 1)
        self.assertEqual({item["id"] for item in audit["dropped"]}, {"low", "late"})

    def test_repairs_only_approved_orphan_references(self) -> None:
        rows = {table: [] for table in exporter.TABLES}
        rows["content"] = [
            {
                "id": "content-live",
                "metadata": {"video_id": "video-1"},
            }
        ]
        duplicate = {
            "chunk_index": 0,
            "text": "same chunk",
            "embedding": [0.0] * 1024,
        }
        rows["chunk"] = [
            {**duplicate, "id": "kept", "content_id": "content-live"},
            {**duplicate, "id": "orphan", "content_id": "content-missing"},
        ]
        rows["pipeline_job"] = [
            {
                "id": "job-1",
                "content_id": "job-content-missing",
                "resource_key": "yt:video-1",
                "status": "failed",
            }
        ]

        audit = exporter.repair_orphan_references(rows)

        self.assertEqual([row["id"] for row in rows["chunk"]], ["kept"])
        self.assertEqual(rows["pipeline_job"], [])
        self.assertEqual(audit["chunk"]["dropped_count"], 1)
        self.assertEqual(audit["pipeline_job"]["dropped_count"], 1)
        self.assertEqual(audit["pipeline_job"]["dropped"][0]["id"], "job-1")
        exporter.validate_references(rows)

        rows["pipeline_job"] = [
            {
                "id": "job-2",
                "content_id": "other-missing-content",
                "status": "completed",
            }
        ]
        with self.assertRaisesRegex(ValueError, "unresolved reference"):
            exporter.repair_orphan_references(rows)

    def test_snapshot_validation_checks_hashes_counts_vectors_and_references(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp)
            write_snapshot(snapshot)
            manifest, rows = importer.validate_snapshot(snapshot)
            self.assertEqual(manifest["vector_dimension"], 1024)
            self.assertEqual(rows["chunk"][0]["content_id"], "content-1")

            (snapshot / "content.ndjson").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                importer.validate_snapshot(snapshot)

    def test_snapshot_archive_is_deterministic_and_safely_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            write_snapshot(snapshot)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            exporter.create_archive(snapshot, first)
            exporter.create_archive(snapshot, second)

            self.assertEqual(importer.sha256_file(first), importer.sha256_file(second))
            with importer.snapshot_directory(first) as extracted:
                manifest, _rows = importer.validate_snapshot(extracted)
            self.assertEqual(manifest["source_revision"], "source-revision")

            first.with_name(first.name + ".sha256").write_text(
                f"{'0' * 64}  {first.name}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "archive checksum mismatch"):
                with importer.snapshot_directory(first):
                    pass

    def test_deduplication_audit_must_match_manifest_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp)
            (snapshot / "deduplication-report.json").write_text(
                '{"dropped":[],"raw_count":2,"unique_count":1}\n',
                encoding="utf-8",
            )
            manifest = {"content_entity_raw_count": 1}
            rows = fixture_rows()

            with self.assertRaisesRegex(ValueError, "raw count"):
                importer._validate_deduplication(snapshot, manifest, rows)

    def test_importer_uses_environment_credentials_and_fail_closed_guards(self) -> None:
        text = IMPORTER.read_text(encoding="utf-8")
        self.assertIn('required_env("POSTGRES_PASSWORD")', text)
        self.assertIn('required_env("DEST_S3_SECRET_KEY", "S3_SECRET_KEY")', text)
        self.assertIn("with connection.transaction()", text)
        self.assertIn("PostgreSQL import target is not empty", text)
        self.assertIn("MinIO import target bucket is not empty", text)
        self.assertNotIn("--password", text)
        self.assertNotIn("--secret-key", text)

    def test_playbook_runs_portable_importer_and_checks_postgres_readiness(
        self,
    ) -> None:
        plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        self.assertEqual(
            plays[0]["ansible.builtin.import_playbook"],
            "vm-direct-access-ready.yml",
        )
        migration_play = next(
            play
            for play in plays
            if play.get("name")
            == "Import a verified portable Menos snapshot into PostgreSQL and MinIO"
        )
        tasks = migration_play["tasks"]
        names = [task["name"] for task in tasks]
        self.assertLess(
            names.index("Require controller migration artifacts"),
            names.index("Import and verify Menos state"),
        )
        text = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("import-postgres.py", text)
        self.assertIn("checks.postgres", text)
        self.assertIn("--env-file", text)
        self.assertIn("menos_migration_stamp }}.tar.gz.sha256:ro,Z", text)
        for environment in (
            "POSTGRES_HOST=postgres",
            "POSTGRES_PORT=5432",
            "DEST_S3_ENDPOINT=minio:9000",
            "DEST_S3_SECURE=false",
        ):
            self.assertIn(environment, text)
        self.assertIn("Transfer verified portable migration archive checksum", names)
        self.assertIn("--cgroup-manager=cgroupfs", text)
        self.assertNotIn("checks.surrealdb", text)
        for check_name in (
            "Verify Menos health after migration",
            "Verify Menos readiness after migration",
        ):
            check = next(task for task in tasks if task["name"] == check_name)
            self.assertEqual(check["retries"], 30)
            self.assertEqual(check["delay"], 5)
            self.assertIn("until", check)
        import_block = next(
            task for task in tasks if task["name"] == "Import and verify Menos state"
        )
        failure_message = import_block["rescue"][0]["ansible.builtin.fail"]["msg"]
        self.assertIn("only if the failure mutated target state", failure_message)
        backup = next(
            task
            for task in tasks
            if task["name"] == "Create custom-format post-import PostgreSQL backup"
        )
        backup_command = backup["ansible.builtin.shell"]["cmd"]
        self.assertIn("nsenter", backup_command)
        self.assertIn("/usr/bin/pg_dump", backup_command)
        self.assertNotIn("POSTGRES_PASSWORD", backup_command)
        self.assertTrue(backup.get("no_log"))
        manifest = next(
            task
            for task in tasks
            if task["name"] == "Write post-import PostgreSQL backup manifest"
        )
        self.assertIn("pg_dump-custom-v1", manifest["ansible.builtin.copy"]["content"])
        self.assertEqual(
            plays[-1]["ansible.builtin.import_playbook"], "service-state-backup.yml"
        )

    def test_only_exporter_retains_legacy_surrealdb_access(self) -> None:
        importer_text = IMPORTER.read_text(encoding="utf-8").lower()
        self.assertNotIn("surrealdb", importer_text)
        self.assertNotIn("surql", importer_text)
        exporter_text = EXPORTER.read_text(encoding="utf-8")
        self.assertIn("SELECT * FROM", exporter_text)
        self.assertNotIn("INSERT ", exporter_text)
        self.assertNotIn("UPDATE ", exporter_text)
        self.assertNotIn("DELETE ", exporter_text)


if __name__ == "__main__":
    unittest.main()

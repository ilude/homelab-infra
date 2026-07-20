from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[1]
MIGRATE_S3 = REPO / "infra" / "ansible" / "files" / "menos-migration" / "migrate-s3.py"
MIGRATE_STATE = (
    REPO / "infra" / "ansible" / "files" / "menos-migration" / "migrate-state.sh"
)
NORMALIZE_SURREAL = (
    REPO
    / "infra"
    / "ansible"
    / "files"
    / "menos-migration"
    / "normalize-surreal-export.py"
)
PLAYBOOK = REPO / "infra" / "ansible" / "playbooks" / "migrate-menos-onramp.yml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate_s3 = load_module("migrate_s3", MIGRATE_S3)
normalize_surreal = load_module("normalize_surreal", NORMALIZE_SURREAL)


class MenosMigrationTests(unittest.TestCase):
    def test_key_hash_matches_sorted_newline_delimited_contract(self) -> None:
        items = [("a", 1), ("b", 2)]
        expected = hashlib.sha256(b"a\nb\n").hexdigest()
        self.assertEqual(migrate_s3.key_hash(items), expected)

    def test_expected_inventory_requires_count_bytes_and_key_hash(self) -> None:
        items = [("a", 1), ("b", 2)]
        environment = {
            "EXPECTED_S3_OBJECT_COUNT": "2",
            "EXPECTED_S3_TOTAL_BYTES": "3",
            "EXPECTED_S3_KEY_LIST_SHA256": migrate_s3.key_hash(items),
        }
        with patch.dict(os.environ, environment, clear=True):
            migrate_s3.verify_expected(items)
        environment["EXPECTED_S3_TOTAL_BYTES"] = "4"
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "byte count mismatch"):
                migrate_s3.verify_expected(items)

    def test_normalizes_legacy_relationship_references_without_changing_source(self) -> None:
        source_text = (
            "INSERT [{ content_id: 'content:abc_1', entity_id: 'entity:def-2' }] "
            "INTO content_entity;\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.surql"
            destination = Path(temp_dir) / "normalized.surql"
            source.write_text(source_text, encoding="utf-8")
            counts = normalize_surreal.normalize(source, destination, 1)
            normalized = destination.read_text(encoding="utf-8")
            source_after = source.read_text(encoding="utf-8")

        self.assertEqual(counts, {"content_id": 1, "entity_id": 1})
        self.assertEqual(source_text, source_after)
        self.assertEqual(len(normalized), len(source_text))
        self.assertIn("content_id:  content:abc_1 ", normalized)
        self.assertIn("entity_id:  entity:def-2 ", normalized)

    def test_normalizer_rejects_unexpected_relationship_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.surql"
            destination = Path(temp_dir) / "normalized.surql"
            source.write_text("RETURN true;\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                normalize_surreal.normalize(source, destination, 1)

    def test_state_helper_keeps_credentials_out_of_command_arguments(self) -> None:
        text = MIGRATE_STATE.read_text(encoding="utf-8")
        self.assertIn('podman exec --env-file "${runtime_dir}/surreal.env"', text)
        self.assertIn('--env-file "${runtime_dir}/migration.env"', text)
        self.assertNotIn("--password", text)
        self.assertNotIn("--secret-key", text)
        self.assertIn("authorized_keys_unchanged=true", text)
        self.assertIn("surreal_mtree_verified=true", text)

    def test_playbook_verifies_archive_before_state_mutation(self) -> None:
        plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        tasks = plays[0]["tasks"]
        names = [task["name"] for task in tasks]
        validate_index = names.index(
            "Validate private C1 archive contents and checksums"
        )
        import_index = names.index("Import and verify Menos state")
        self.assertLess(validate_index, import_index)
        import_block = tasks[import_index]["block"]
        import_task = next(
            task
            for task in import_block
            if task["name"] == "Run managed Menos state import"
        )
        self.assertEqual(import_task["become_user"], "{{ onramp_host_deploy_user }}")
        self.assertEqual(import_task["async"], 10800)
        self.assertEqual(import_task["poll"], 15)
        self.assertIn(
            "scripts/service-state.sh restore menos_onramp",
            str(tasks[import_index]["rescue"]),
        )

    def test_playbook_verifies_source_revision_and_creates_backup(self) -> None:
        plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        text = PLAYBOOK.read_text(encoding="utf-8")
        self.assertIn("menos_migration_health.json.git_sha", text)
        self.assertEqual(
            plays[1]["ansible.builtin.import_playbook"], "service-state-backup.yml"
        )
        self.assertEqual(plays[1]["vars"]["service_state_service"], "menos_onramp")


if __name__ == "__main__":
    unittest.main()

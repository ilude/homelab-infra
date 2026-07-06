from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tfplan-metadata.py"
spec = importlib.util.spec_from_file_location("tfplan_metadata", SCRIPT)
assert spec and spec.loader
tfplan_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tfplan_metadata)


class TfplanMetadataTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        repo = Path(temp_dir.name)
        (repo / "infra" / "ansible" / "scripts").mkdir(parents=True)
        (repo / "infra" / "opentofu").mkdir(parents=True)
        (repo / "infra" / "opentofu" / "main.tf").write_text("terraform {}\n")
        (repo / "infra" / "ansible" / "scripts" / "apply-technitium-dns.py").write_text("# helper\n")
        (repo / "values" / "ansible" / "inventory").mkdir(parents=True)
        (repo / "values" / "terraform.tfvars").write_text("x = 1\n")
        (repo / "values" / "dns-records.local.json").write_text("{}\n")
        (repo / "values" / "ansible" / "inventory" / "local.yml").write_text("---\n")
        (repo / "values" / ".env").write_text("PVE_HOST=proxmox.example.internal\n")
        plan = repo / "tfplan"
        metadata = repo / "tfplan.meta.json"
        plan.write_text("plan-data\n")
        return temp_dir, repo, plan, metadata

    def test_create_and_verify_metadata(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            tfplan_metadata.create_metadata(plan, metadata, repo, 24, {"resource_changes": []})
            tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_missing_metadata_fails(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_changed_plan_hash_fails(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            tfplan_metadata.create_metadata(plan, metadata, repo, 24, {"resource_changes": []})
            plan.write_text("changed\n")
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_changed_input_hash_fails(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            tfplan_metadata.create_metadata(plan, metadata, repo, 24, {"resource_changes": []})
            (repo / "values" / "dns-records.local.json").write_text('{"changed": true}\n')
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_expired_plan_fails(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            tfplan_metadata.create_metadata(plan, metadata, repo, 24, {"resource_changes": []})
            data = metadata.read_text(encoding="utf-8")
            expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            metadata.write_text(data.replace(data.split('"expires_at": "')[1].split('"')[0], expired))
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_summarize_plan_counts_destructive_changes(self) -> None:
        summary = tfplan_metadata.summarize_plan(
            {
                "resource_changes": [
                    {"address": "resource.create", "change": {"actions": ["create"]}},
                    {"address": "resource.update", "change": {"actions": ["update"]}},
                    {"address": "resource.delete", "change": {"actions": ["delete"]}},
                    {"address": "resource.replace", "change": {"actions": ["delete", "create"]}},
                ]
            }
        )

        self.assertEqual(summary["resource_changes"]["create"], 1)
        self.assertEqual(summary["resource_changes"]["update"], 1)
        self.assertEqual(summary["resource_changes"]["delete"], 1)
        self.assertEqual(summary["resource_changes"]["replace"], 1)
        self.assertTrue(summary["destructive"])
        self.assertEqual(len(summary["destructive_changes"]), 2)

    def test_destructive_plan_requires_allow_destroy(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            tfplan_metadata.create_metadata(
                plan,
                metadata,
                repo,
                24,
                {"resource_changes": [{"address": "resource.delete", "change": {"actions": ["delete"]}}]},
            )
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)
            tfplan_metadata.verify_metadata(plan, metadata, repo, allow_destroy=True)

    def test_missing_summary_fails_closed(self) -> None:
        temp_dir, repo, plan, metadata = self.make_repo()
        with temp_dir:
            data = tfplan_metadata.create_metadata(plan, metadata, repo, 24, {"resource_changes": []})
            del data["summary"]
            metadata.write_text(tfplan_metadata.json.dumps(data), encoding="utf-8")
            with self.assertRaises(tfplan_metadata.MetadataError):
                tfplan_metadata.verify_metadata(plan, metadata, repo)

    def test_format_plan_summary_lists_destructive_addresses(self) -> None:
        text = tfplan_metadata.format_plan_summary(
            {
                "resource_changes": {"create": 0, "update": 0, "replace": 1, "delete": 0},
                "destructive": True,
                "destructive_changes": [{"address": "resource.replace", "actions": "delete/create"}],
            }
        )

        self.assertIn("resource.replace", text)
        self.assertIn("Apply is gated", text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bws-snapshot.py"
spec = importlib.util.spec_from_file_location("bws_snapshot", SCRIPT)
assert spec and spec.loader
bws_snapshot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bws_snapshot
spec.loader.exec_module(bws_snapshot)


class BwsSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.access_key = os.environ.get("BITWARDEN_ACCESS_KEY")
        self.hcl2 = bws_snapshot.hcl2
        bws_snapshot.hcl2 = types.SimpleNamespace(loads=lambda text: {})
        os.environ["BITWARDEN_ACCESS_KEY"] = "test-access-key"

    def tearDown(self) -> None:
        bws_snapshot.hcl2 = self.hcl2
        if self.access_key is None:
            os.environ.pop("BITWARDEN_ACCESS_KEY", None)
        else:
            os.environ["BITWARDEN_ACCESS_KEY"] = self.access_key

    def write_source(self, root: Path) -> Path:
        (root / "values" / "ansible" / "inventory").mkdir(parents=True)
        (root / "values" / ".env").write_text('PVE_HOST="pve.example.internal"\n', encoding="utf-8")
        (root / "values" / "terraform.tfvars").write_text(
            'proxmox_node_name = "pve"\n', encoding="utf-8"
        )
        (root / "values" / "ansible" / "inventory" / "local.yml").write_text(
            "all:\n"
            "  vars:\n"
            "    seaweedfs_s3_endpoint: https://s3.example.internal\n"
            "    seaweedfs_s3_bucket: homelab-state\n"
            "    seaweedfs_s3_key: infra/terraform.tfstate\n"
            "    seaweedfs_s3_region: homelab\n",
            encoding="utf-8",
        )
        (root / "values" / "dns-records.local.json").write_text(
            '{"records": []}\n', encoding="utf-8"
        )
        settings_path = root / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {
                    "bws": {
                        "project_id": "project-id",
                        "api_server": "https://bws.example.internal/api",
                    },
                    "services": ["technitium"],
                }
            ),
            encoding="utf-8",
        )
        return settings_path

    def family_values(self, root: Path) -> dict[str, str]:
        manifest = bws_snapshot.load_manifest()
        values = bws_snapshot.read_source_values(root, manifest)
        values.update(
            {
                "SEAWEEDFS_S3_ACCESS_KEY": "access-key",
                "SEAWEEDFS_S3_SECRET_KEY": "secret$key",
                "HOMELAB_TOFU_STATE_PASSPHRASE": 'pass"word',
                "RABBITMQ_DEFAULT_USER": "rabbit-user",
                "RABBITMQ_DEFAULT_PASS": "rabbit-pass",
                "ONCLAVE_VAULT_POSTGRES_PASSWORD": "postgres-password-with-24-characters",
                "ONCLAVE_VAULT_S3_ACCESS_KEY": "s3-access-key",
                "ONCLAVE_VAULT_S3_SECRET_KEY": "s3-secret-with-24-characters",
                "ONCLAVE_VAULT_SEARXNG_SECRET": "searxng-secret-with-24-characters",
                "ONCLAVE_VAULT_WEBSHARE_PROXY_USERNAME": "webshare-user",
                "ONCLAVE_VAULT_WEBSHARE_PROXY_PASSWORD": "webshare-password",
                "ONCLAVE_VAULT_YOUTUBE_API_KEY": "youtube-key",
                "ONCLAVE_VAULT_OPENROUTER_API_KEY": "openrouter-key",
                "ONCLAVE_VAULT_ANTHROPIC_API_KEY": "anthropic-key",
            }
        )
        return values

    @staticmethod
    def runner(records: list[dict[str, str]], calls: list[tuple[list[str], dict[str, str]]]):
        def run(command: object, environment: object):
            calls.append((list(command), dict(environment)))
            return __import__("subprocess").CompletedProcess(command, 0, json.dumps(records), "")

        return run

    def test_manifest_has_exact_routes_and_runtime_keys(self) -> None:
        manifest = bws_snapshot.load_manifest()
        self.assertEqual(
            [(family.key, str(family.path)) for family in manifest.families],
            [
                ("HOMELAB_ENV", "values/.env"),
                ("HOMELAB_TERRAFORM_TFVARS", "values/terraform.tfvars"),
                ("HOMELAB_ANSIBLE_INVENTORY", "values/ansible/inventory/local.yml"),
                ("HOMELAB_DNS_RECORDS", "values/dns-records.local.json"),
                ("HOMELAB_SETTINGS", "settings.local.json"),
            ],
        )
        self.assertEqual(manifest.runtime_keys, bws_snapshot.RUNTIME_KEYS)

    def test_list_uses_bws_environment_and_rejects_duplicate_keys(self) -> None:
        locator = bws_snapshot.Locator("project", "https://bws.example.internal/api")
        calls: list[tuple[list[str], dict[str, str]]] = []
        with self.assertRaisesRegex(bws_snapshot.BwsSnapshotError, "duplicate secret keys"):
            bws_snapshot.list_bws_secrets(
                locator,
                "access-token",
                self.runner(
                    [
                        {"key": "HOMELAB_ENV", "value": "one"},
                        {"key": "HOMELAB_ENV", "value": "two"},
                    ],
                    calls,
                ),
            )
        self.assertEqual(calls[0][0][:3], ["bws", "secret", "list"])
        self.assertEqual(calls[0][1]["BWS_ACCESS_TOKEN"], "access-token")
        self.assertEqual(calls[0][1]["BWS_SERVER_URL"], "https://bws.example.internal")

    def test_required_value_errors_name_keys_but_not_values(self) -> None:
        with self.assertRaises(bws_snapshot.BwsSnapshotError) as captured:
            bws_snapshot.resolve_required(
                {"HOMELAB_ENV": "private-value"},
                ("HOMELAB_ENV", "HOMELAB_DNS_RECORDS"),
            )
        self.assertIn("HOMELAB_DNS_RECORDS", str(captured.exception))
        self.assertNotIn("private-value", str(captured.exception))

    def test_render_writes_private_validated_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            values = self.family_values(root)
            records = [{"key": key, "value": value} for key, value in values.items()]
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = root / "snapshot"
            console = io.StringIO()
            with contextlib.redirect_stdout(console):
                rc = bws_snapshot.main(
                    [
                        "--settings",
                        str(settings_path),
                        "render",
                        "--output",
                        str(output),
                    ],
                    self.runner(records, calls),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1)
            self.assertNotIn(values["SEAWEEDFS_S3_SECRET_KEY"], console.getvalue())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            for path in (
                output / "values" / ".env",
                output / "values" / "terraform.tfvars",
                output / "values" / "ansible" / "inventory" / "local.yml",
                output / "values" / "dns-records.local.json",
                output / "settings.local.json",
                output / "runtime.env",
                output / "backend.hcl",
            ):
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            runtime = (output / "runtime.env").read_text(encoding="utf-8")
            self.assertIn("AWS_ACCESS_KEY_ID=access-key", runtime)
            self.assertIn("AWS_SECRET_KEY=secret$$key", runtime)
            encoded_encryption = next(
                line.split("=", 1)[1]
                for line in runtime.splitlines()
                if line.startswith("TF_ENCRYPTION_B64=")
            )
            encryption = base64.b64decode(encoded_encryption).decode("utf-8")
            self.assertIn('passphrase = "pass', encryption)
            self.assertNotIn('passphrase = "pass"word"', encryption)
            self.assertIn(f"VALUES_DIR={output.resolve() / 'values'}", runtime)
            backend = (output / "backend.hcl").read_text(encoding="utf-8")
            self.assertIn('s3 = "https://s3.example.internal"', backend)
            self.assertIn("use_path_style = true", backend)
            self.assertIn("use_lockfile = true", backend)

    def test_render_rejects_duplicate_yaml_and_cleans_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_source(root)
            values = self.family_values(root)
            inventory_family = next(
                family
                for family in bws_snapshot.load_manifest().families
                if family.key == "HOMELAB_ANSIBLE_INVENTORY"
            )
            values["HOMELAB_ANSIBLE_INVENTORY"] = bws_snapshot.encode_family(
                inventory_family, "all:\n  vars:\n    same: one\n    same: two\n"
            )
            output = root / "snapshot"
            with self.assertRaisesRegex(bws_snapshot.BwsSnapshotError, "valid YAML"):
                bws_snapshot.render_snapshot(output, bws_snapshot.load_manifest(), values)
            self.assertFalse(output.exists())

    def test_seed_creates_only_missing_after_conflict_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            manifest = bws_snapshot.load_manifest()
            source = bws_snapshot.read_source_values(root, manifest)
            existing = [{"key": key, "value": value} for key, value in source.items()]
            existing.pop()
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = bws_snapshot.main(
                    [
                        "--settings",
                        str(settings_path),
                        "seed",
                        "--source-root",
                        str(root),
                    ],
                    self.runner(existing, calls),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len([call for call in calls if call[0][2] == "list"]), 1)
            creates = [call for call in calls if call[0][2] == "create"]
            self.assertEqual(len(creates), 1)
            self.assertIn("HOMELAB_SETTINGS: created", output.getvalue())
            self.assertNotIn(source["HOMELAB_SETTINGS"], output.getvalue())

    def test_seed_refuses_conflicts_without_creating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            existing = [{"key": "HOMELAB_ENV", "value": "different-private-value"}]
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = bws_snapshot.main(
                    [
                        "--settings",
                        str(settings_path),
                        "seed",
                        "--source-root",
                        str(root),
                    ],
                    self.runner(existing, calls),
                )
            self.assertEqual(rc, 1)
            self.assertEqual(len(calls), 1)
            self.assertIn("HOMELAB_ENV: conflict", output.getvalue())
            self.assertNotIn("different-private-value", output.getvalue())

    def test_sync_updates_only_changed_family_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            manifest = bws_snapshot.load_manifest()
            source = bws_snapshot.read_source_values(root, manifest)
            records = [
                {"id": f"id-{index}", "key": key, "value": value}
                for index, (key, value) in enumerate(source.items())
            ]
            records[0]["value"] = "old-private-value"
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = bws_snapshot.main(
                    [
                        "--settings",
                        str(settings_path),
                        "sync",
                        "--source-root",
                        str(root),
                    ],
                    self.runner(records, calls),
                )
            self.assertEqual(rc, 0)
            edits = [call for call in calls if call[0][2] == "edit"]
            self.assertEqual(len(edits), 1)
            self.assertIn("HOMELAB_ENV: updated", output.getvalue())
            self.assertNotIn(source["HOMELAB_ENV"], output.getvalue())

    @staticmethod
    def onclave_legacy_env() -> str:
        return (
            "PVE_HOST=pve.example.internal\n"
            "MENOS_POSTGRES_PASSWORD=postgres-secret\n"  # public-safety: allow-secret
            "MENOS_S3_ACCESS_KEY=s3-access\n"
            "MENOS_S3_SECRET_KEY=s3-secret\n"  # public-safety: allow-secret
            "MENOS_SEARXNG_SECRET=searxng-secret\n"  # public-safety: allow-secret
            "MENOS_WEBSHARE_PROXY_USERNAME=webshare-user\n"
            "MENOS_WEBSHARE_PROXY_PASSWORD=webshare-secret\n"  # public-safety: allow-secret
            "MENOS_YOUTUBE_API_KEY=youtube-key\n"  # public-safety: allow-secret
            "MENOS_OPENROUTER_API_KEY=openrouter-key\n"  # public-safety: allow-secret
            "MENOS_ANTHROPIC_API_KEY=anthropic-key\n"  # public-safety: allow-secret
        )

    @staticmethod
    def onclave_legacy_inventory() -> str:
        return (
            "all:\n"
            "  vars:\n"
            "    menos_onramp_base_dir: /menos\n"
            "    menos_authorized_keys: []\n"
            "    menos_postgres_database: menos\n"
            "    menos_postgres_user: menos\n"
            "    menos_postgres_password: \"{{ lookup('env', 'MENOS_POSTGRES_PASSWORD') }}\"\n"
            "    menos_s3_access_key: \"{{ lookup('env', 'MENOS_S3_ACCESS_KEY') }}\"\n"
            "    menos_s3_secret_key: \"{{ lookup('env', 'MENOS_S3_SECRET_KEY') }}\"\n"
            "    menos_searxng_secret: \"{{ lookup('env', 'MENOS_SEARXNG_SECRET') }}\"\n"
            "    menos_webshare_proxy_username: "
            "\"{{ lookup('env', 'MENOS_WEBSHARE_PROXY_USERNAME') }}\"\n"
            "    menos_webshare_proxy_password: "
            "\"{{ lookup('env', 'MENOS_WEBSHARE_PROXY_PASSWORD') }}\"\n"
            "    menos_youtube_api_key: \"{{ lookup('env', 'MENOS_YOUTUBE_API_KEY') }}\"\n"
            "    menos_openrouter_api_key: \"{{ lookup('env', 'MENOS_OPENROUTER_API_KEY') }}\"\n"
            "    menos_anthropic_api_key: \"{{ lookup('env', 'MENOS_ANTHROPIC_API_KEY') }}\"\n"
            "    menos_onramp_openai_api_key: \"{{ lookup('env', 'MENOS_OPENAI_API_KEY') }}\"\n"
            "    menos_onramp_unified_pipeline_model: openai/gpt-4o-mini\n"
        )

    @staticmethod
    def onclave_records(inventory: str) -> dict[str, tuple[str, str]]:
        manifest = bws_snapshot.load_manifest()
        inventory_family = next(
            family for family in manifest.families if family.key == "HOMELAB_ANSIBLE_INVENTORY"
        )
        return {
            "HOMELAB_ENV": ("id-env", BwsSnapshotTests.onclave_legacy_env()),
            "HOMELAB_ANSIBLE_INVENTORY": (
                "id-inventory",
                bws_snapshot.encode_family(inventory_family, inventory),
            ),
        }

    def test_onclave_runtime_profile_requires_vault_and_rabbitmq(self) -> None:
        values = {key: "test-value" for key in bws_snapshot.RUNTIME_KEYS}
        for key in bws_snapshot.OPTIONAL_RUNTIME_KEYS:
            values.pop(key)
        runtime = bws_snapshot.resolve_runtime(values, bws_snapshot.RUNTIME_PROFILES["onclave"])
        self.assertEqual(
            tuple(runtime),
            (
                "RABBITMQ_DEFAULT_USER",
                "RABBITMQ_DEFAULT_PASS",
                *bws_snapshot.ONCLAVE_RUNTIME_KEYS,
            ),
        )
        for key in bws_snapshot.OPTIONAL_RUNTIME_KEYS:
            self.assertEqual(runtime[key], "")

    def test_migrate_onclave_renames_bws_inputs_without_changing_adopted_storage(
        self,
    ) -> None:
        manifest = bws_snapshot.load_manifest()
        records = self.onclave_records(self.onclave_legacy_inventory())
        migrated = bws_snapshot.migrate_onclave_config(manifest, records)
        inventory_family = next(
            family for family in manifest.families if family.key == "HOMELAB_ANSIBLE_INVENTORY"
        )
        migrated_inventory = bws_snapshot.decode_family(
            inventory_family, migrated.families["HOMELAB_ANSIBLE_INVENTORY"]
        )
        self.assertNotIn("MENOS_", migrated.families["HOMELAB_ENV"])
        self.assertIn("onclave_onramp_postgres_database: menos", migrated_inventory)
        self.assertIn("onclave_onramp_postgres_user: menos", migrated_inventory)
        self.assertIn("onclave_onramp_data_root: /menos/data", migrated_inventory)
        self.assertIn("onclave_onramp_unified_pipeline_model", migrated_inventory)
        self.assertIn("ONCLAVE_VAULT_POSTGRES_PASSWORD", migrated_inventory)
        self.assertNotIn("menos_postgres_database", migrated_inventory)

    def test_migrate_onclave_rejects_colliding_legacy_and_canonical_keys(self) -> None:
        manifest = bws_snapshot.load_manifest()
        records = self.onclave_records(self.onclave_legacy_inventory())
        records["HOMELAB_ENV"] = (
            "id-env",
            self.onclave_legacy_env()
            + "ONCLAVE_VAULT_POSTGRES_PASSWORD=other-secret\n",  # public-safety: allow-secret
        )
        with self.assertRaisesRegex(
            bws_snapshot.BwsSnapshotError,
            "both MENOS_POSTGRES_PASSWORD and ONCLAVE_VAULT_POSTGRES_PASSWORD",
        ):
            bws_snapshot.migrate_onclave_config(manifest, records)

        records = self.onclave_records(
            self.onclave_legacy_inventory() + "    onclave_onramp_postgres_database: other\n"
        )
        with self.assertRaisesRegex(
            bws_snapshot.BwsSnapshotError,
            "both menos_postgres_database and onclave_onramp_postgres_database",
        ):
            bws_snapshot.migrate_onclave_config(manifest, records)

    def test_migrate_onclave_fails_closed_for_quoted_and_flow_style_legacy_keys(
        self,
    ) -> None:
        quoted = self.onclave_legacy_inventory().replace(
            "    menos_postgres_database:", "    'menos_postgres_database':"
        )
        with self.assertRaisesRegex(
            bws_snapshot.BwsSnapshotError, "quoted all.vars key menos_postgres_database"
        ):
            bws_snapshot.migrate_onclave_config(
                bws_snapshot.load_manifest(), self.onclave_records(quoted)
            )

        flow = (
            "all:\n"
            "  vars: {menos_postgres_database: menos, "
            "menos_onramp_unified_pipeline_model: openai/gpt-4o-mini}\n"
        )
        with self.assertRaisesRegex(bws_snapshot.BwsSnapshotError, "flow-style all.vars"):
            bws_snapshot.migrate_onclave_config(
                bws_snapshot.load_manifest(), self.onclave_records(flow)
            )

    def test_migrate_onclave_dry_run_and_rerun_after_partial_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            records = [
                {"id": secret_id, "key": key, "value": value}
                for key, (secret_id, value) in self.onclave_records(
                    self.onclave_legacy_inventory()
                ).items()
            ]
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = bws_snapshot.main(
                    ["--settings", str(settings_path), "migrate-onclave"],
                    self.runner(records, calls),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1)
            self.assertIn(
                "ONCLAVE_VAULT_POSTGRES_PASSWORD: create pending",  # public-safety: allow-secret
                output.getvalue(),
            )
            self.assertNotIn("postgres-secret", output.getvalue())

            fail_key = "ONCLAVE_VAULT_S3_SECRET_KEY"
            failed = False

            def partial_runner(command: object, environment: object):
                nonlocal failed
                calls.append((list(command), dict(environment)))
                if command[2] == "list":
                    return __import__("subprocess").CompletedProcess(
                        command, 0, json.dumps(records), ""
                    )
                if command[2] == "create":
                    key, value = command[3], command[4]
                    if key == fail_key and not failed:
                        failed = True
                        return __import__("subprocess").CompletedProcess(
                            command, 1, "", "create failed"
                        )
                    records.append({"id": f"id-{key}", "key": key, "value": value})
                elif command[2] == "edit":
                    secret_id, value = command[3], command[5]
                    next(record for record in records if record["id"] == secret_id)["value"] = value
                return __import__("subprocess").CompletedProcess(command, 0, "", "")

            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        bws_snapshot.main(
                            [
                                "--settings",
                                str(settings_path),
                                "migrate-onclave",
                                "--write",
                            ],
                            partial_runner,
                        ),
                        1,
                    )
            self.assertTrue(failed)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    bws_snapshot.main(
                        ["--settings", str(settings_path), "migrate-onclave", "--write"],
                        partial_runner,
                    ),
                    0,
                )
            self.assertEqual(
                sum(
                    call[0][2] == "create" and call[0][3] == "ONCLAVE_VAULT_POSTGRES_PASSWORD"
                    for call in calls
                ),
                1,
            )

    def test_verify_reports_key_only_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings_path = self.write_source(root)
            manifest = bws_snapshot.load_manifest()
            source = bws_snapshot.read_source_values(root, manifest)
            records = [{"key": key, "value": value} for key, value in source.items()]
            calls: list[tuple[list[str], dict[str, str]]] = []
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = bws_snapshot.main(
                    [
                        "--settings",
                        str(settings_path),
                        "verify",
                        "--source-root",
                        str(root),
                    ],
                    self.runner(records, calls),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1)
            self.assertIn("HOMELAB_ENV: match", output.getvalue())
            self.assertNotIn(source["HOMELAB_ENV"], output.getvalue())


if __name__ == "__main__":
    unittest.main()

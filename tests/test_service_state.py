from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any
from unittest import mock

import yaml
from jinja2 import StrictUndefined, Template

REPO = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO / "infra/ansible/vars/service-state.yml"
RESTORE_PATH = REPO / "infra/ansible/playbooks/service-state-restore.yml"
BACKUP_PATH = REPO / "infra/ansible/playbooks/service-state-backup.yml"
VALIDATOR_PATH = REPO / "infra/ansible/scripts/validate-service-state-archive.py"
COMPRESSION_HELPER_PATH = REPO / "infra/ansible/scripts/compress-service-state-backup.py"
FETCH_HELPER_PATH = REPO / "infra/ansible/scripts/fetch-service-state.py"
PUSH_HELPER_PATH = REPO / "infra/ansible/scripts/push-service-state.py"
TECHNITIUM_ROLE_TASKS = REPO / "infra/ansible/roles/technitium/tasks/main.yml"
FORGEJO_ROLE_TASKS = REPO / "infra/ansible/roles/forgejo/tasks/main.yml"
TECHNITIUM_ROLE_DEFAULTS = REPO / "infra/ansible/roles/technitium/defaults/main.yml"
SERVICE_STATE_SCRIPT = REPO / "scripts/service-state.sh"

spec = importlib.util.spec_from_file_location("service_state_validator", VALIDATOR_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

compression_spec = importlib.util.spec_from_file_location(
    "service_state_compression", COMPRESSION_HELPER_PATH
)
assert compression_spec and compression_spec.loader
compression = importlib.util.module_from_spec(compression_spec)
compression_spec.loader.exec_module(compression)

fetch_spec = importlib.util.spec_from_file_location(
    "fetch_service_state", FETCH_HELPER_PATH
)
assert fetch_spec and fetch_spec.loader
fetch = importlib.util.module_from_spec(fetch_spec)
fetch_spec.loader.exec_module(fetch)

push_spec = importlib.util.spec_from_file_location(
    "push_service_state", PUSH_HELPER_PATH
)
assert push_spec and push_spec.loader
push = importlib.util.module_from_spec(push_spec)
push_spec.loader.exec_module(push)


def load_catalog() -> dict[str, Any]:
    rendered = Template(
        CATALOG_PATH.read_text(encoding="utf-8"),
        undefined=StrictUndefined,
    ).render(
        hermes_runtime_user="anvil",
        onramp_host_deploy_dir="/srv/onramp",
        onramp_host_deploy_user="deploy",
    )
    return yaml.safe_load(rendered)["managed_service_state_catalog"]


def task_names(playbook: Path) -> list[str]:
    plays = yaml.safe_load(playbook.read_text(encoding="utf-8"))
    names: list[str] = []

    def visit(tasks: list[dict[str, Any]]) -> None:
        for task in tasks:
            if "name" in task:
                names.append(task["name"])
            for section in ("block", "rescue", "always"):
                if section in task:
                    visit(task[section])

    for play in plays:
        visit(play.get("tasks", []))
    return names


def add_bytes(handle: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    handle.addfile(info, io.BytesIO(content))


def make_archive(
    path: Path,
    *,
    target: str = "hermes",
    manifest: bool = True,
    manifest_paths: list[str] | None = None,
    include_state: bool = True,
    state_paths: list[str] | None = None,
    link: tuple[str, str, bytes] | None = None,
    compression_mode: str = "gz",
) -> None:
    managed_paths = state_paths or ["/home/anvil/.hermes"]
    with tarfile.open(path, f"w:{compression_mode}" if compression_mode else "w") as handle:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        handle.addfile(root)
        if manifest:
            data = json.dumps(
                {
                    "schema_version": 1,
                    "target": target,
                    "archive_kind": "backup",
                    "paths": (
                        managed_paths if manifest_paths is None else manifest_paths
                    ),
                }
            ).encode()
            add_bytes(handle, "MANIFEST.json", data)
        if include_state:
            for managed_path in managed_paths:
                archive_path = managed_path.lstrip("/")
                directory = tarfile.TarInfo(archive_path)
                directory.type = tarfile.DIRTYPE
                handle.addfile(directory)
                add_bytes(handle, f"{archive_path}/state.txt", b"state")
        if link:
            name, target_name, kind = link
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = target_name
            handle.addfile(info)


class ServiceStateCatalogTests(unittest.TestCase):
    def test_state_wrapper_refreshes_lxc_and_vm_direct_access(self) -> None:
        source = SERVICE_STATE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("direct-access-ready.yml", source)
        self.assertIn("vm-direct-access-ready.yml", source)
        self.assertIn("direct_vm_access_target_group", source)

    def test_every_path_declares_valid_ownership_metadata(self) -> None:
        for target, definition in load_catalog().items():
            for item in definition["paths"]:
                self.assertEqual(
                    {"path", "owner", "group", "recurse"}, set(item), target
                )
                self.assertTrue(item["path"])
                self.assertTrue(item["owner"])
                self.assertTrue(item["group"])
                self.assertIs(type(item["recurse"]), bool)

    def test_hermes_uses_recursive_runtime_user_ownership(self) -> None:
        path = load_catalog()["hermes"]["paths"][0]
        self.assertEqual(path["path"], "/home/anvil/.hermes")
        self.assertEqual(path["owner"], path["group"])
        self.assertEqual(path["owner"], "anvil")
        self.assertTrue(path["recurse"])

    def test_hermes_backup_stops_dashboard_and_gateway(self) -> None:
        self.assertEqual(
            load_catalog()["hermes"]["services"],
            ["hermes-gateway", "hermes-dashboard"],
        )

    def test_onclave_backup_covers_adopted_postgres_and_minio_not_ollama(self) -> None:
        definition = load_catalog()["onclave_onramp"]
        paths = [item["path"] for item in definition["paths"]]
        expected_root = "/srv/onramp"

        self.assertEqual(
            paths,
            [
                f"{expected_root}/onclave",
                f"{expected_root}/menos/data/postgres",
                f"{expected_root}/menos/data/minio",
                "/etc/caddy/sites.d/onclave.caddy",
            ],
        )
        self.assertNotIn(f"{expected_root}/menos/data/ollama", paths)
        self.assertEqual(
            definition["backup_staging_root"],
            f"{expected_root}/.service-state-backup-staging",
        )
        self.assertEqual(
            definition["device_backup_root"],
            f"{expected_root}/.service-state-backups",
        )
        self.assertEqual(definition["backup_retention_count"], 5)
        self.assertTrue(definition["restore_require_all_paths"])
        for path in definition["paths"][:3]:
            self.assertEqual(path["owner"], "deploy")
            self.assertEqual(path["group"], "deploy")
            self.assertTrue(path["recurse"])

    def test_onramp_host_owns_only_caddy_base_files(self) -> None:
        paths = [item["path"] for item in load_catalog()["onramp_host"]["paths"]]
        self.assertEqual(
            paths,
            [
                "/etc/caddy/env",
                "/etc/caddy/Caddyfile",
                "/etc/caddy/sites.d/00-placeholder.caddy",
            ],
        )

    def test_backup_quiescing_is_boolean_and_enabled_only_for_onclave(self) -> None:
        catalog = load_catalog()
        enabled = [
            target
            for target, definition in catalog.items()
            if definition.get("backup_quiesce_user_services", False)
        ]

        self.assertEqual(enabled, ["onclave_onramp"])
        self.assertIs(
            type(catalog["onclave_onramp"]["backup_quiesce_user_services"]), bool
        )
        strict_restore_targets = [
            target
            for target, definition in catalog.items()
            if definition.get("restore_require_all_paths", False)
        ]
        self.assertEqual(strict_restore_targets, ["onclave_onramp"])

    def test_forgejo_installs_state_backup_transport(self) -> None:
        self.assertIn(
            "openssh-server rsync sqlite3",
            FORGEJO_ROLE_TASKS.read_text(encoding="utf-8"),
        )

    def test_technitium_restore_ownership_matches_managed_role(self) -> None:
        path = load_catalog()["technitium"]["paths"][0]
        role_tasks = yaml.safe_load(TECHNITIUM_ROLE_TASKS.read_text(encoding="utf-8"))
        ownership_task = next(
            task
            for task in role_tasks
            if task.get("name")
            == "Ensure Technitium persistent and release directories exist"
        )
        role_state = next(
            item
            for item in ownership_task["loop"]
            if item["path"] == "{{ technitium_state_directory }}"
        )
        role_defaults = yaml.safe_load(
            TECHNITIUM_ROLE_DEFAULTS.read_text(encoding="utf-8")
        )

        self.assertEqual(path["path"], role_defaults["technitium_state_directory"])
        self.assertEqual(path["path"], "/etc/dns")
        self.assertEqual(path["owner"], role_state["owner"])
        self.assertEqual(path["group"], role_state["group"])
        self.assertTrue(path["recurse"])

    def test_paths_are_absolute_unique_and_non_overlapping(self) -> None:
        catalog = load_catalog()
        managed_paths = [
            (target, PurePosixPath(item["path"]))
            for target, definition in catalog.items()
            for item in definition["paths"]
        ]
        for target, definition in catalog.items():
            paths = [PurePosixPath(item["path"]) for item in definition["paths"]]
            self.assertTrue(all(str(path).startswith("/") for path in paths), target)
            self.assertEqual(len(paths), len(set(paths)), target)
        for index, (left_target, left) in enumerate(managed_paths):
            for right_target, right in managed_paths[index + 1 :]:
                if left_target == right_target:
                    continue
                self.assertNotEqual(left, right, (left_target, right_target))
                self.assertNotIn(left, right.parents, (left_target, right_target))
                self.assertNotIn(right, left.parents, (left_target, right_target))

    def test_system_and_user_service_scopes_do_not_overlap(self) -> None:
        for target, definition in load_catalog().items():
            system = definition.get("services", [])
            user = definition.get("user_services", [])
            self.assertEqual(len(system), len(set(system)), target)
            self.assertEqual(len(user), len(set(user)), target)
            self.assertFalse(set(system) & set(user), target)


class FetchServiceStateTests(unittest.TestCase):
    def test_accepts_archive_within_explicit_allowed_root(self) -> None:
        fetch.validate_remote_archive(
            "/srv/onramp/.service-state-backup-staging/onclave-state.tar.gz",
            "/srv/onramp/.service-state-backup-staging",
        )
        fetch.validate_remote_archive("/tmp/hermes-state.tar.gz", "/tmp")

    def test_rejects_sibling_and_traversal_remote_archives(self) -> None:
        for remote in (
            "/srv/onramp/.service-state-backup-staging-sibling/onclave-state.tar.gz",
            "/srv/onramp/.service-state-backup-staging/../outside.tar.gz",
            "/srv/onramp/.service-state-backup-staging/onclave-state.tar",
        ):
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                fetch.validate_remote_archive(
                    remote,
                    "/srv/onramp/.service-state-backup-staging",
                )

    def test_stream_replaces_controller_archive_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "state.tar.gz"
            output.write_bytes(b"previous")

            def stream_archive(*args: Any, **kwargs: Any) -> None:
                self.assertEqual(output.read_bytes(), b"previous")
                kwargs["stdout"].write(b"replacement")

            with (
                mock.patch.object(
                    fetch,
                    "parse_args",
                    return_value=type(
                        "Args",
                        (),
                        {
                            "host": "example.internal",
                            "user": "anvil",
                            "ssh_common_args": "",
                            "remote": "/tmp/state.tar.gz",
                            "allowed_remote_root": "/tmp",
                            "output": output,
                            "become": False,
                        },
                    )(),
                ),
                mock.patch.object(fetch.subprocess, "run", side_effect=stream_archive),
            ):
                self.assertEqual(fetch.main(), 0)

            self.assertEqual(output.read_bytes(), b"replacement")
            self.assertEqual(list(Path(temp).glob(".state.tar.gz.*")), [])


class PushServiceStateTests(unittest.TestCase):
    def test_accepts_archive_within_explicit_allowed_root(self) -> None:
        push.validate_remote_archive(
            "/srv/onramp/.service-state-backup-staging/onclave-state.tar.gz",
            "/srv/onramp/.service-state-backup-staging",
        )
        push.validate_remote_archive("/tmp/hermes-state.tar.gz", "/tmp")

    def test_rejects_sibling_and_traversal_remote_archives(self) -> None:
        for remote in (
            "/srv/onramp/.service-state-backup-staging-sibling/onclave-state.tar.gz",
            "/srv/onramp/.service-state-backup-staging/../outside.tar.gz",
            "/srv/onramp/.service-state-backup-staging/onclave-state.tar",
        ):
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                push.validate_remote_archive(
                    remote,
                    "/srv/onramp/.service-state-backup-staging",
                )

    def test_streams_to_a_private_remote_tempfile_then_replaces_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            input_archive = Path(temp) / "state.tar.gz"
            input_archive.write_bytes(b"state")

            def upload(command: list[str], **kwargs: Any) -> None:
                self.assertEqual(command[0], "ssh")
                self.assertIn('mktemp "$1"', command[-1])
                self.assertIn('cat > "$temporary"', command[-1])
                self.assertIn('mv -f "$temporary" "$2"', command[-1])
                self.assertEqual(kwargs["stdin"].read(), b"state")
                self.assertTrue(kwargs["check"])

            with (
                mock.patch.object(
                    push,
                    "parse_args",
                    return_value=type(
                        "Args",
                        (),
                        {
                            "host": "example.internal",
                            "user": "anvil",
                            "ssh_common_args": "",
                            "remote": "/tmp/state.tar.gz",
                            "allowed_remote_root": "/tmp",
                            "input": input_archive,
                            "become": True,
                        },
                    )(),
                ),
                mock.patch.object(push.subprocess, "run", side_effect=upload),
            ):
                self.assertEqual(push.main(), 0)


class ServiceStateCompressionTests(unittest.TestCase):
    def test_compresses_pending_archive_and_retains_latest_five_histories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o700)
            latest = root / "latest.tar"
            latest.write_bytes(b"current-state")
            pending = root / "onclave_onramp-state-pending-1.tar"
            pending.hardlink_to(latest)

            for index in range(5):
                archive = root / f"onclave_onramp-state-old-{index}.tar.gz"
                archive.write_bytes(f"old-{index}".encode())
                archive.with_name(f"{archive.name}.sha256").write_text(
                    "old\n", encoding="ascii"
                )
                os.utime(archive, (index + 1, index + 1))

            history = compression.compress_pending_archive(
                root,
                pending,
                "onclave_onramp-state-new.tar.gz",
                5,
            )

            self.assertTrue(latest.exists())
            self.assertFalse(pending.exists())
            with gzip.open(history, "rb") as handle:
                self.assertEqual(handle.read(), b"current-state")
            sidecar = history.with_name(f"{history.name}.sha256")
            expected_digest = hashlib.sha256(history.read_bytes()).hexdigest()
            self.assertEqual(
                sidecar.read_text(encoding="ascii"),
                f"{expected_digest}  {history.name}\n",
            )
            self.assertEqual(len(list(root.glob("*.tar.gz"))), 5)
            self.assertFalse((root / "onclave_onramp-state-old-0.tar.gz").exists())

    def test_compression_failure_keeps_pending_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o700)
            pending = root / "onclave_onramp-state-pending-1.tar"
            pending.write_bytes(b"state")
            history = root / "onclave_onramp-state-existing.tar.gz"
            history.write_bytes(b"existing")

            with self.assertRaises(compression.CompressionError):
                compression.compress_pending_archive(
                    root,
                    pending,
                    history.name,
                    5,
                )

            self.assertTrue(pending.exists())
            self.assertEqual(history.read_bytes(), b"existing")


class ServiceStateBackupPlaybookTests(unittest.TestCase):
    def test_quiescing_requires_a_boolean_flag_owner_and_staging_root(self) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        validation = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Validate service-state backup quiescing configuration"
        )
        checks = validation["ansible.builtin.assert"]["that"]

        self.assertIn(
            "service_state_definition.backup_quiesce_user_services | default(false) is boolean",
            checks,
        )
        self.assertTrue(any("user_services" in check for check in checks))
        self.assertTrue(any("user_service_owner" in check for check in checks))
        self.assertTrue(any("backup_staging_root" in check for check in checks))

    def test_strict_backup_requires_all_paths_before_quiescing(self) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        names = task_names(BACKUP_PATH)
        strict_preflight = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Fail strict backup when managed service-state paths are missing"
        )

        self.assertEqual(
            strict_preflight["ansible.builtin.assert"]["that"],
            [
                "service_state_existing_paths | length == service_state_definition.paths | length"
            ],
        )
        self.assertEqual(
            strict_preflight["when"],
            "service_state_definition.restore_require_all_paths | default(false) | bool",
        )
        self.assertLess(
            names.index(
                "Fail strict backup when managed service-state paths are missing"
            ),
            names.index("Check configured user services are active before backup"),
        )

    def test_fetches_allow_only_the_expected_remote_archive_root(self) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        non_quiesced_fetch = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Stream non-quiesced service-state archive into private values"
        )
        quiesced_block = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Create and stream quiesced service-state archive"
        )
        quiesced_fetch = next(
            task
            for task in quiesced_block["block"]
            if task.get("name")
            == "Stream quiesced service-state archive into private values"
        )
        fetches = [non_quiesced_fetch, quiesced_fetch]

        self.assertEqual(len(fetches), 2)
        for task in fetches:
            args = task["ansible.builtin.command"]["argv"]
            self.assertIn("--allowed-remote-root", args)
            self.assertIn("service_state_remote_archive_root", args)
        self.assertIn("else '/tmp'", BACKUP_PATH.read_text(encoding="utf-8"))

    def test_quiesced_backup_stops_archives_and_restarts_in_order(self) -> None:
        names = task_names(BACKUP_PATH)
        active = names.index("Check configured user services are active before backup")
        stop = names.index("Stop active user services before backup archive")
        archive = names.index(
            "Create quiesced service-state archive directly from managed paths"
        )
        restart = names.index("Restart active user services after backup archive")

        self.assertLess(active, stop)
        self.assertLess(stop, archive)
        self.assertLess(archive, restart)

    def test_quiesced_backup_restarts_only_initially_active_users_on_tar_failure(
        self,
    ) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        outer = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Create and stream quiesced service-state archive"
        )
        quiesce = next(
            task
            for task in outer["block"]
            if task.get("name")
            == "Quiesce active user services while creating service-state archive"
        )
        active = next(
            task
            for task in quiesce["block"]
            if task.get("name")
            == "Check configured user services are active before backup"
        )
        stop = next(
            task
            for task in quiesce["block"]
            if task.get("name") == "Stop active user services before backup archive"
        )
        archive = next(
            task
            for task in quiesce["block"]
            if task.get("name")
            == "Create quiesced service-state archive directly from managed paths"
        )
        restart = next(
            task
            for task in quiesce["always"]
            if task.get("name") == "Restart active user services after backup archive"
        )

        self.assertEqual(
            active["ansible.builtin.command"]["argv"][:3],
            ["systemctl", "--user", "is-active"],
        )
        self.assertEqual(
            active["failed_when"],
            "service_state_user_service_activity.rc not in [0, 3]",
        )
        self.assertEqual(stop["loop"], "{{ service_state_active_user_services }}")
        self.assertEqual(restart["loop"], "{{ service_state_active_user_services }}")
        self.assertEqual(stop["ansible.builtin.systemd_service"]["state"], "stopped")
        self.assertEqual(restart["ansible.builtin.systemd_service"]["state"], "started")
        self.assertIn(
            "service_state_existing_archive_paths",
            archive["ansible.builtin.command"]["argv"],
        )
        self.assertNotIn("snapshot", archive["ansible.builtin.command"]["argv"])
        self.assertNotIn("caddy", str(quiesce))

    def test_quiesced_backup_uses_private_staging_capacity_and_cleanup(self) -> None:
        source = BACKUP_PATH.read_text(encoding="utf-8")
        playbook = yaml.safe_load(source)
        names = task_names(BACKUP_PATH)

        self.assertIn("backup_staging_root", source)
        self.assertIn("service_state_backup_required_kib", source)
        self.assertIn("df", source)
        self.assertIn("du", source)
        self.assertIn("Create private quiesced service-state staging directory", names)
        self.assertIn("Remove quiesced service-state archive from service host", names)
        self.assertIn("Remove private quiesced service-state staging directory", names)
        self.assertIn(
            "Remove temporary quiesced service-state manifest directory", names
        )
        outer = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Create and stream quiesced service-state archive"
        )
        self.assertIn("always", outer)
        self.assertIn("service_state_manifest_dir.path", str(outer["always"]))

    def test_non_onclave_backup_retains_tmp_snapshot_workflow(self) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        snapshot = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Snapshot non-quiesced managed service-state paths"
        )
        archive = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Create non-quiesced service-state archive on service host"
        )

        self.assertEqual(
            snapshot["when"],
            "not (service_state_definition.backup_quiesce_user_services | default(false) | bool)",
        )
        self.assertEqual(archive["when"], snapshot["when"])
        self.assertIn("else '/tmp'", BACKUP_PATH.read_text(encoding="utf-8"))
        self.assertIn(
            "service_state_snapshot_dir.path",
            archive["ansible.builtin.command"]["argv"],
        )

    def test_device_backup_installs_latest_before_background_compression(self) -> None:
        playbook = yaml.safe_load(BACKUP_PATH.read_text(encoding="utf-8"))
        names = task_names(BACKUP_PATH)
        device = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Create device-local Onclave service-state archive"
        )
        quiesce = next(
            task
            for task in device["block"]
            if task.get("name")
            == "Quiesce active user service while creating device-local archive"
        )
        archive = next(
            task
            for task in quiesce["block"]
            if task.get("name")
            == "Create uncompressed temporary device-local service-state archive"
        )
        launch = next(
            task
            for task in device["block"]
            if task.get("name") == "Launch device-local service-state compression"
        )

        self.assertIn("'-cf'", archive["ansible.builtin.command"]["argv"])
        self.assertIn("--no-block", launch["ansible.builtin.command"]["argv"])
        self.assertIn("--retention", launch["ansible.builtin.command"]["argv"])
        self.assertLess(
            names.index("Atomically replace latest device-local service-state archive"),
            names.index("Restart active user service after device-local archive"),
        )
        self.assertLess(
            names.index("Restart active user service after device-local archive"),
            names.index("Launch device-local service-state compression"),
        )

    def test_backup_snapshot_avoids_container_and_compose_control(self) -> None:
        source = BACKUP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("podman", source)
        self.assertNotIn("docker", source)
        self.assertNotIn("compose", source)


class ServiceStateRestorePlaybookTests(unittest.TestCase):
    def test_onclave_restore_requires_complete_catalog_archive_before_stops(
        self,
    ) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        names = task_names(RESTORE_PATH)
        coverage = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Validate service-state restore archive coverage configuration"
        )
        archive_validation = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Validate service-state restore archive contents"
        )

        self.assertIn("restore_require_all_paths", str(coverage))
        self.assertIn(
            "--require-all-paths", archive_validation["ansible.builtin.command"]["argv"]
        )
        self.assertLess(
            names.index("Validate service-state restore archive contents"),
            names.index("Stop managed system services before restore"),
        )

    def test_unarchive_ownership_repair_restart_ordering(self) -> None:
        names = task_names(RESTORE_PATH)
        unarchive = names.index("Restore managed service-state archive")
        root_owner = names.index("Apply catalog ownership to restored path roots")
        recursive_owner = names.index(
            "Apply recursive catalog ownership to restored directories"
        )
        user_restart = names.index("Restart managed user services after restore")
        system_restart = names.index("Restart managed system services after restore")
        self.assertLess(unarchive, root_owner)
        self.assertLess(root_owner, recursive_owner)
        self.assertLess(recursive_owner, user_restart)
        self.assertLess(user_restart, system_restart)

    def test_ownership_tasks_specify_no_mode(self) -> None:
        plays = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        text = RESTORE_PATH.read_text(encoding="utf-8")
        for marker in (
            "Apply catalog ownership to restored path roots",
            "Apply recursive catalog ownership to restored directories",
        ):
            section = text.split(f"- name: {marker}", 1)[1].split(
                "\n        - name:", 1
            )[0]
            self.assertNotIn("mode:", section)
        self.assertTrue(plays)

    def test_multi_path_targets_process_every_path(self) -> None:
        text = RESTORE_PATH.read_text(encoding="utf-8")
        self.assertIn('loop: "{{ service_state_definition.paths }}"', text)
        self.assertIn("service_state_restored_path_stats.results", text)
        backup = BACKUP_PATH.read_text(encoding="utf-8")
        self.assertIn("item.path", backup)

    def test_large_archives_stream_without_ansible_fetch_buffering(self) -> None:
        backup = BACKUP_PATH.read_text(encoding="utf-8")
        restore = RESTORE_PATH.read_text(encoding="utf-8")
        helper = FETCH_HELPER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("ansible.builtin.fetch", backup)
        self.assertNotIn("ansible.builtin.fetch", restore)
        self.assertIn("fetch-service-state.py", backup)
        self.assertIn("fetch-service-state.py", restore)
        self.assertIn("subprocess.run(command, stdout=output, check=True)", helper)
        self.assertIn("temporary.replace(args.output)", helper)

    def test_pre_restore_uses_direct_staged_archive_and_path_contained_stream(
        self,
    ) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        restore_block = next(
            task["block"]
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        archive = next(
            task
            for task in restore_block
            if task.get("name")
            == "Create pre-restore service-state archive directly from managed paths"
        )
        stream = next(
            task
            for task in restore_block
            if task.get("name")
            == "Stream pre-restore service-state archive into private values"
        )
        archive_args = archive["ansible.builtin.command"]["argv"]
        stream_args = stream["ansible.builtin.command"]["argv"]
        source = RESTORE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("rsync", source)
        self.assertNotIn("service_state_pre_restore_snapshot_dir", source)
        self.assertNotIn("ansible.builtin.fetch", source)
        self.assertIn("service_state_existing_archive_paths", archive_args)
        self.assertIn("'-C', '/'", archive_args)
        self.assertIn("fetch-service-state.py", stream_args)
        self.assertIn("--allowed-remote-root", stream_args)
        self.assertIn("service_state_remote_archive_root", stream_args)
        self.assertIn("service_state_pre_restore_manifest_dir.path", archive_args)

    def test_pre_restore_archive_is_validated_before_recovery_is_ready(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        restore_block = next(
            task["block"]
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        names = [task["name"] for task in restore_block]
        validation = next(
            task
            for task in restore_block
            if task.get("name")
            == "Validate local pre-restore service-state archive contents"
        )

        args = validation["ansible.builtin.command"]["argv"]
        self.assertIn("validate-service-state-archive.py", args)
        self.assertIn("--target", args)
        self.assertIn("service_state_service", args)
        self.assertIn("--paths-json", args)
        self.assertIn("service_state_managed_paths", args)
        self.assertIn("--require-all-paths", args)
        self.assertLess(
            names.index("Validate local pre-restore service-state archive contents"),
            names.index("Mark pre-restore recovery archive as secured"),
        )

    def test_restore_upload_streams_directly_into_the_staging_filesystem(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        restore_block = next(
            task["block"]
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        upload = next(
            task
            for task in restore_block
            if task.get("name")
            == "Stream service-state restore archive into service staging"
        )

        args = upload["ansible.builtin.command"]["argv"]
        self.assertIn("push-service-state.py", args)
        self.assertIn("--allowed-remote-root", args)
        self.assertIn("service_state_remote_archive_root", args)
        self.assertIn("--input", args)
        self.assertIn("service_state_restore_file", args)

    def test_pre_restore_staging_is_contained_capacity_checked_before_stops(
        self,
    ) -> None:
        source = RESTORE_PATH.read_text(encoding="utf-8")
        names = task_names(RESTORE_PATH)

        self.assertIn("backup_staging_root | default('/tmp')", source)
        self.assertIn("service_state_pre_restore_required_kib", source)
        self.assertNotIn("service_state_remote_archive_root | dirname", source)
        self.assertIn(' - "{{ service_state_remote_archive_root }}"', source)
        self.assertIn("--apparent-size", source)
        self.assertIn("-Pk", source)
        self.assertLess(
            names.index("Require conservative free space for generic pre-restore staging"),
            names.index("Stop managed system services before restore"),
        )
        self.assertLess(
            names.index("Create private pre-restore service-state staging directory"),
            names.index("Stop managed system services before restore"),
        )

    def test_empty_state_cleanup_requires_manifest_path(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        outer = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        cleanup_names = [task["name"] for task in outer["always"]]

        self.assertEqual(
            cleanup_names,
            [
                "Remove temporary pre-restore service-state manifest directory",
                "Remove partial pre-restore service-state archive from service host",
                "Remove partial temporary device-local pre-restore archive",
                "Remove partial service-state restore archive from service host",
                "Remove private pre-restore service-state staging directory",
            ],
        )
        manifest_cleanup = outer["always"][0]
        self.assertEqual(
            manifest_cleanup["when"],
            "service_state_pre_restore_manifest_dir.path is defined",
        )
        staging_cleanup = outer["always"][-1]
        self.assertEqual(
            staging_cleanup["when"],
            [
                "service_state_definition.backup_staging_root is defined",
                "not (service_state_restore_uses_device_latest | bool)",
            ],
        )

    def test_restore_failure_restarts_before_mutation_and_stops_afterwards(
        self,
    ) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        outer = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        rescue = {task["name"]: task for task in outer["rescue"]}
        names = task_names(RESTORE_PATH)

        self.assertLess(
            names.index("Stream service-state restore archive into service staging"),
            names.index("Mark destructive service-state restore mutation started"),
        )
        self.assertLess(
            names.index("Mark destructive service-state restore mutation started"),
            names.index("Remove existing managed service-state paths before restore"),
        )
        self.assertIn(
            "not (service_state_restore_mutation_started | bool)",
            rescue["Restart managed user services after pre-mutation restore failure"][
                "when"
            ],
        )
        self.assertEqual(
            rescue[
                "Restart managed system services after pre-mutation restore failure"
            ]["when"],
            "not (service_state_restore_mutation_started | bool)",
        )
        self.assertEqual(
            rescue[
                "Keep managed system services stopped after destructive restore failure"
            ]["when"],
            "service_state_restore_mutation_started | bool",
        )
        self.assertLess(
            names.index(
                "Restart managed user services after pre-mutation restore failure"
            ),
            names.index(
                "Restart managed system services after pre-mutation restore failure"
            ),
        )

    def test_pre_restore_archive_has_manifest_checksum_and_private_permissions(
        self,
    ) -> None:
        text = RESTORE_PATH.read_text(encoding="utf-8")
        self.assertIn('"archive_kind": "pre_restore"', text)
        self.assertIn("Write local pre-restore service-state checksum", text)
        self.assertIn(
            "Restrict local pre-restore service-state archive permissions", text
        )
        self.assertGreaterEqual(text.count('mode: "0600"'), 3)

    def test_device_latest_is_validated_and_not_removed_by_restore_cleanup(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        names = task_names(RESTORE_PATH)
        validation = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Validate device-local latest service-state archive contents"
        )
        outer = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        cleanup = next(
            task
            for task in outer["always"]
            if task.get("name")
            == "Remove partial service-state restore archive from service host"
        )
        launch = next(
            task
            for task in playbook[0]["tasks"]
            if task.get("name") == "Launch device-local pre-restore compression"
        )

        self.assertIn(
            "service_state_device_latest_archive",
            validation["ansible.builtin.command"]["argv"],
        )
        self.assertLess(
            names.index("Validate device-local latest service-state archive contents"),
            names.index("Stop managed system services before restore"),
        )
        self.assertEqual(
            cleanup["when"], "not (service_state_restore_uses_device_latest | bool)"
        )
        self.assertNotIn(launch, outer["block"])
        self.assertIn("--no-block", launch["ansible.builtin.command"]["argv"])

    def test_hermes_wrapper_contract_remains_compatible(self) -> None:
        backup = yaml.safe_load(
            (REPO / "infra/ansible/playbooks/hermes-state-backup.yml").read_text(
                encoding="utf-8"
            )
        )
        restore = yaml.safe_load(
            (REPO / "infra/ansible/playbooks/hermes-state-restore.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            backup[0]["ansible.builtin.import_playbook"], "service-state-backup.yml"
        )
        self.assertEqual(
            restore[0]["ansible.builtin.import_playbook"], "service-state-restore.yml"
        )
        self.assertEqual(backup[0]["vars"]["service_state_service"], "hermes")
        self.assertEqual(restore[0]["vars"]["service_state_service"], "hermes")


class ServiceStateArchiveValidationTests(unittest.TestCase):
    def test_restore_repairs_symlink_ownership_without_following_links(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        tasks = playbook[0]["tasks"]
        restore_block = next(
            task["block"]
            for task in tasks
            if task.get("name")
            == "Restore service state after successful preflight and stops"
        )
        find_task = next(
            task
            for task in restore_block
            if task.get("name")
            == "Discover descendant symlinks in restored managed paths"
        )
        symlink_owner_task = next(
            task
            for task in restore_block
            if task.get("name") == "Apply catalog ownership to restored symlinks"
        )
        find_args = find_task["ansible.builtin.find"]
        owner_args = symlink_owner_task["ansible.builtin.file"]
        self.assertTrue(find_args["recurse"])
        self.assertEqual(find_args["file_type"], "link")
        self.assertFalse(find_args["follow"])
        self.assertEqual(owner_args["owner"], "{{ item.0.item.item.owner }}")
        self.assertEqual(owner_args["group"], "{{ item.0.item.item.group }}")
        self.assertFalse(owner_args["follow"])

    def test_escaping_symlink_and_hardlink_are_rejected(self) -> None:
        cases = [
            ("home/anvil/.hermes/link", "../../../../etc/passwd", tarfile.SYMTYPE),
            ("home/anvil/.hermes/link", "etc/passwd", tarfile.LNKTYPE),
        ]
        for link in cases:
            with self.subTest(kind=link[2]), tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / "state.tar.gz"
                make_archive(archive, link=link)
                with self.assertRaises(validator.ArchiveValidationError):
                    validator.validate_archive(
                        str(archive), "hermes", ["/home/anvil/.hermes"]
                    )

    def test_uncompressed_archive_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "state.tar"
            make_archive(archive, compression_mode="")
            validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_legacy_manifestless_hermes_archive_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "legacy.tar.gz"
            make_archive(archive, manifest=False)
            validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_legacy_onclave_archive_missing_adopted_paths_fails_strict_preflight(
        self,
    ) -> None:
        old_paths = [
            "/srv/onramp/onclave",
            "/etc/caddy/sites.d/onclave.caddy",
        ]
        managed_paths = [
            "/srv/onramp/onclave",
            "/srv/onramp/menos/data/postgres",
            "/srv/onramp/menos/data/minio",
            "/etc/caddy/sites.d/onclave.caddy",
        ]
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "legacy-onclave.tar.gz"
            make_archive(
                archive,
                target="onclave_onramp",
                manifest_paths=old_paths,
                state_paths=old_paths,
            )
            validator.validate_archive(str(archive), "onclave_onramp", managed_paths)
            with self.assertRaises(validator.ArchiveValidationError):
                validator.validate_archive(
                    str(archive),
                    "onclave_onramp",
                    managed_paths,
                    require_all_paths=True,
                )

    def test_empty_and_root_only_archives_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "empty.tar.gz"
            with tarfile.open(empty, "w:gz"):
                pass
            root_only = Path(temp) / "root-only.tar.gz"
            make_archive(root_only, manifest=False, include_state=False)
            for archive in (empty, root_only):
                with (
                    self.subTest(archive=archive.name),
                    self.assertRaises(validator.ArchiveValidationError),
                ):
                    validator.validate_archive(
                        str(archive), "hermes", ["/home/anvil/.hermes"]
                    )

    def test_manifestless_archive_without_managed_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "manifestless-root-only.tar.gz"
            make_archive(archive, manifest=False, include_state=False)
            with self.assertRaises(validator.ArchiveValidationError):
                validator.validate_archive(
                    str(archive), "hermes", ["/home/anvil/.hermes"]
                )

    def test_empty_and_nonmatching_manifest_paths_are_rejected(self) -> None:
        for manifest_paths in ([], ["/home/anvil/.other"]):
            with (
                self.subTest(manifest_paths=manifest_paths),
                tempfile.TemporaryDirectory() as temp,
            ):
                archive = Path(temp) / "state.tar.gz"
                make_archive(archive, manifest_paths=manifest_paths)
                with self.assertRaises(validator.ArchiveValidationError):
                    validator.validate_archive(
                        str(archive), "hermes", ["/home/anvil/.hermes"]
                    )

    def test_wrong_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "state.tar.gz"
            make_archive(archive, target="forgejo")
            with self.assertRaises(validator.ArchiveValidationError):
                validator.validate_archive(
                    str(archive), "hermes", ["/home/anvil/.hermes"]
                )


if __name__ == "__main__":
    unittest.main()

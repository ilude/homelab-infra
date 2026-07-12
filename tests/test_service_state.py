from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jinja2 import StrictUndefined, Template

REPO = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO / "infra/ansible/vars/service-state.yml"
RESTORE_PATH = REPO / "infra/ansible/playbooks/service-state-restore.yml"
BACKUP_PATH = REPO / "infra/ansible/playbooks/service-state-backup.yml"
VALIDATOR_PATH = REPO / "infra/ansible/scripts/validate-service-state-archive.py"
FETCH_HELPER_PATH = REPO / "infra/ansible/scripts/fetch-service-state.py"
TECHNITIUM_ROLE_TASKS = REPO / "infra/ansible/roles/technitium/tasks/main.yml"
FORGEJO_ROLE_TASKS = REPO / "infra/ansible/roles/forgejo/tasks/main.yml"
TECHNITIUM_ROLE_DEFAULTS = REPO / "infra/ansible/roles/technitium/defaults/main.yml"

spec = importlib.util.spec_from_file_location("service_state_validator", VALIDATOR_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


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
    link: tuple[str, str, bytes] | None = None,
) -> None:
    managed = "/home/anvil/.hermes"
    with tarfile.open(path, "w:gz") as handle:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        handle.addfile(root)
        if manifest:
            data = json.dumps(
                {
                    "schema_version": 1,
                    "target": target,
                    "archive_kind": "backup",
                    "paths": [managed] if manifest_paths is None else manifest_paths,
                }
            ).encode()
            add_bytes(handle, "MANIFEST.json", data)
        if include_state:
            directory = tarfile.TarInfo("home/anvil/.hermes")
            directory.type = tarfile.DIRTYPE
            handle.addfile(directory)
            add_bytes(handle, "home/anvil/.hermes/state.txt", b"state")
        if link:
            name, target_name, kind = link
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = target_name
            handle.addfile(info)


class ServiceStateCatalogTests(unittest.TestCase):
    def test_every_path_declares_valid_ownership_metadata(self) -> None:
        for target, definition in load_catalog().items():
            for item in definition["paths"]:
                self.assertEqual({"path", "owner", "group", "recurse"}, set(item), target)
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

    def test_forgejo_installs_state_backup_transport(self) -> None:
        self.assertIn("openssh-server rsync sqlite3", FORGEJO_ROLE_TASKS.read_text(encoding="utf-8"))

    def test_technitium_restore_ownership_matches_managed_role(self) -> None:
        path = load_catalog()["technitium"]["paths"][0]
        role_tasks = yaml.safe_load(TECHNITIUM_ROLE_TASKS.read_text(encoding="utf-8"))
        ownership_task = next(
            task
            for task in role_tasks
            if task.get("name") == "Ensure Technitium persistent and release directories exist"
        )
        role_state = next(
            item
            for item in ownership_task["loop"]
            if item["path"] == "{{ technitium_state_directory }}"
        )
        role_defaults = yaml.safe_load(TECHNITIUM_ROLE_DEFAULTS.read_text(encoding="utf-8"))

        self.assertEqual(path["path"], role_defaults["technitium_state_directory"])
        self.assertEqual(path["path"], "/etc/dns")
        self.assertEqual(path["owner"], role_state["owner"])
        self.assertEqual(path["group"], role_state["group"])
        self.assertTrue(path["recurse"])

    def test_paths_are_absolute_unique_and_non_overlapping(self) -> None:
        for target, definition in load_catalog().items():
            paths = [PurePosixPath(item["path"]) for item in definition["paths"]]
            self.assertTrue(all(str(path).startswith("/") for path in paths), target)
            self.assertEqual(len(paths), len(set(paths)), target)
            for index, left in enumerate(paths):
                for right in paths[index + 1 :]:
                    self.assertNotIn(left, right.parents, target)
                    self.assertNotIn(right, left.parents, target)

    def test_system_and_user_service_scopes_do_not_overlap(self) -> None:
        for target, definition in load_catalog().items():
            system = definition.get("services", [])
            user = definition.get("user_services", [])
            self.assertEqual(len(system), len(set(system)), target)
            self.assertEqual(len(user), len(set(user)), target)
            self.assertFalse(set(system) & set(user), target)


class ServiceStateRestorePlaybookTests(unittest.TestCase):
    def test_unarchive_ownership_repair_restart_ordering(self) -> None:
        names = task_names(RESTORE_PATH)
        unarchive = names.index("Restore managed service-state archive")
        root_owner = names.index("Apply catalog ownership to restored path roots")
        recursive_owner = names.index("Apply recursive catalog ownership to restored directories")
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
            section = text.split(f"- name: {marker}", 1)[1].split("\n        - name:", 1)[0]
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
        helper = FETCH_HELPER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("ansible.builtin.fetch", backup)
        self.assertIn("fetch-service-state.py", backup)
        self.assertIn("subprocess.run(command, stdout=output, check=True)", helper)
        self.assertIn("temporary.replace(args.output)", helper)

    def test_pre_restore_archive_has_manifest_checksum_and_private_permissions(self) -> None:
        text = RESTORE_PATH.read_text(encoding="utf-8")
        self.assertIn('"archive_kind": "pre_restore"', text)
        self.assertIn("Write local pre-restore service-state checksum", text)
        self.assertIn("Restrict local pre-restore service-state archive permissions", text)
        self.assertGreaterEqual(text.count('mode: "0600"'), 4)

    def test_hermes_wrapper_contract_remains_compatible(self) -> None:
        backup = yaml.safe_load((REPO / "infra/ansible/playbooks/hermes-state-backup.yml").read_text(encoding="utf-8"))
        restore = yaml.safe_load((REPO / "infra/ansible/playbooks/hermes-state-restore.yml").read_text(encoding="utf-8"))
        self.assertEqual(backup[0]["ansible.builtin.import_playbook"], "service-state-backup.yml")
        self.assertEqual(restore[0]["ansible.builtin.import_playbook"], "service-state-restore.yml")
        self.assertEqual(backup[0]["vars"]["service_state_service"], "hermes")
        self.assertEqual(restore[0]["vars"]["service_state_service"], "hermes")


class ServiceStateArchiveValidationTests(unittest.TestCase):
    def test_restore_repairs_symlink_ownership_without_following_links(self) -> None:
        playbook = yaml.safe_load(RESTORE_PATH.read_text(encoding="utf-8"))
        tasks = playbook[0]["tasks"]
        restore_block = next(
            task["block"]
            for task in tasks
            if task.get("name") == "Restore service state after successful preflight and stops"
        )
        find_task = next(
            task
            for task in restore_block
            if task.get("name") == "Discover descendant symlinks in restored managed paths"
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
                    validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_legacy_manifestless_hermes_archive_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "legacy.tar.gz"
            make_archive(archive, manifest=False)
            validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_empty_and_root_only_archives_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "empty.tar.gz"
            with tarfile.open(empty, "w:gz"):
                pass
            root_only = Path(temp) / "root-only.tar.gz"
            make_archive(root_only, manifest=False, include_state=False)
            for archive in (empty, root_only):
                with self.subTest(archive=archive.name), self.assertRaises(validator.ArchiveValidationError):
                    validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_manifestless_archive_without_managed_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "manifestless-root-only.tar.gz"
            make_archive(archive, manifest=False, include_state=False)
            with self.assertRaises(validator.ArchiveValidationError):
                validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_empty_and_nonmatching_manifest_paths_are_rejected(self) -> None:
        for manifest_paths in ([], ["/home/anvil/.other"]):
            with self.subTest(manifest_paths=manifest_paths), tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / "state.tar.gz"
                make_archive(archive, manifest_paths=manifest_paths)
                with self.assertRaises(validator.ArchiveValidationError):
                    validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])

    def test_wrong_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "state.tar.gz"
            make_archive(archive, target="forgejo")
            with self.assertRaises(validator.ArchiveValidationError):
                validator.validate_archive(str(archive), "hermes", ["/home/anvil/.hermes"])


if __name__ == "__main__":
    unittest.main()

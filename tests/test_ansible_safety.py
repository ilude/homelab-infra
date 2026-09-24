from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment

REPO = Path(__file__).resolve().parents[1]
RUNNER_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "forgejo_runner" / "tasks" / "main.yml"
)
LXC_READY_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "lxc_ready" / "tasks" / "main.yml"
)
DIRECT_ACCESS_PLAYBOOK = (
    REPO / "infra" / "ansible" / "playbooks" / "direct-access-ready.yml"
)
VM_DIRECT_ACCESS_PLAYBOOK = (
    REPO / "infra" / "ansible" / "playbooks" / "vm-direct-access-ready.yml"
)
MINIO_MIGRATION_PLAYBOOK = (
    REPO / "infra" / "ansible" / "playbooks" / "migrate-minio-to-seaweedfs.yml"
)
ONCLAVE_ONRAMP_PLAYBOOK = (
    REPO / "infra" / "ansible" / "playbooks" / "onclave-onramp.yml"
)
ONCLAVE_ONRAMP_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "onclave_onramp" / "tasks" / "main.yml"
)
SEAWEEDFS_ONRAMP_PLAYBOOK = REPO / "infra" / "ansible" / "playbooks" / "seaweedfs-onramp.yml"
SEAWEEDFS_S3_TEMPLATE = (
    REPO / "infra" / "ansible" / "roles" / "seaweedfs_onramp" / "templates" / "s3.json.j2"
)
SEAWEEDFS_ONRAMP_DEFAULTS = (
    REPO / "infra" / "ansible" / "roles" / "seaweedfs_onramp" / "defaults" / "main.yml"
)
SEARXNG_ONRAMP_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml"
)
SEARXNG_SETTINGS_TEMPLATE = (
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "searxng_onramp"
    / "templates"
    / "settings.yml.j2"
)
ZFS_DATASET_TASKS = REPO / "infra" / "ansible" / "tasks" / "zfs-dataset.yml"
ONRAMP_HOST_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "onramp_host" / "tasks" / "main.yml"
)
ONRAMP_HOST_STORAGE_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "onramp_host" / "tasks" / "storage.yml"
)
ROOTLESS_ONRAMP_UNITS = tuple(
    REPO / "infra" / "ansible" / "roles" / role / "templates" / unit
    for role, unit in (
        ("infisical_onramp", "infisical-onramp.service.j2"),
        ("freellmapi_onramp", "freellmapi-onramp.container.j2"),
        ("searxng_onramp", "searxng-onramp.service.j2"),
        ("onclave_onramp", "onclave-onramp.target.j2"),
    )
)
CADDY_TASK_FILES = (
    REPO / "infra" / "ansible" / "roles" / "caddy_proxy" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "caddy.yml",
    REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml",
)
ANSIBLE_TASK_FILES = tuple((REPO / "infra" / "ansible" / "roles").glob("*/tasks/*.yml"))
SERVICE_SMOKE_TASK_FILES = (
    REPO / "infra" / "ansible" / "roles" / "technitium" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "caddy_proxy" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "freellmapi_onramp"
    / "tasks"
    / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml",
)
ALLOWLIST_PCT = {
    REPO / "infra" / "ansible" / "roles" / "lxc_ready" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo_bind_mount" / "tasks" / "main.yml",
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "forgejo_bind_mount"
    / "handlers"
    / "main.yml",
}


def load_tasks(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        return []
    return [task for task in data if isinstance(task, dict)]


def task_by_name(path: Path, name: str) -> dict[str, Any]:
    for task in load_tasks(path):
        if task.get("name") == name:
            return task
    raise AssertionError(f"missing task: {name}")


def task_names(path: Path) -> list[str]:
    return [str(task.get("name")) for task in load_tasks(path)]


def command_text(task: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
        value = task.get(key)
        if isinstance(value, dict):
            argv = value.get("argv")
            if isinstance(argv, list):
                values.extend(str(item) for item in argv)
            elif isinstance(value.get("cmd"), str):
                values.append(str(value["cmd"]))
        elif isinstance(value, str):
            values.append(value)
    return "\n".join(values)


class AnsibleSafetyTests(unittest.TestCase):
    def test_storage_prep_does_not_reset_existing_service_ownership(self) -> None:
        task = task_by_name(
            ZFS_DATASET_TASKS,
            "Set initial host storage ownership {{ storage_dataset.mountpoint }}",
        )
        self.assertEqual(task.get("when"), "storage_zfs_list.rc != 0")

    def test_onramp_storage_precedes_app_installation_and_units_require_mounts(
        self,
    ) -> None:
        names = task_names(ONRAMP_HOST_TASKS)
        self.assertLess(
            names.index(
                "Prepare onramp-host guest storage before application packages"
            ),
            names.index("Install Podman onramp-host packages"),
        )
        self.assertLess(
            names.index("Install Podman onramp-host packages"),
            names.index("Build pinned Caddy for onramp host"),
        )
        inspect_device = task_by_name(
            ONRAMP_HOST_STORAGE_TASKS, "Inspect onramp-host data device"
        )
        self.assertTrue(inspect_device["ansible.builtin.stat"].get("follow"))
        inspect_var = task_by_name(
            ONRAMP_HOST_STORAGE_TASKS, "Inspect current onramp-host var mount"
        )
        self.assertIn("--target", command_text(inspect_var))
        storage = ONRAMP_HOST_STORAGE_TASKS.read_text(encoding="utf-8")
        for contract in (
            "Fail closed for an unsafe onramp-host data device",
            "Copy fresh onramp-host var data once",
            "Persist onramp-host var mount by UUID",
            "Reboot once for onramp-host var handoff",
            "Verify onramp-host VG reserve",
        ):
            self.assertIn(contract, storage)
        main = ONRAMP_HOST_TASKS.read_text(encoding="utf-8")
        self.assertIn('graphroot = "/srv/podman/{{ onramp_host_deploy_user }}"', main)
        for unit in ROOTLESS_ONRAMP_UNITS:
            source = unit.read_text(encoding="utf-8")
            self.assertIn(
                "RequiresMountsFor=/srv/podman/{{ onramp_host_deploy_user }} "
                "{{ onramp_host_deploy_dir }}",
                source,
                str(unit),
            )

    def test_service_roles_do_not_use_pct_for_steady_state(self) -> None:
        for path in sorted((REPO / "infra" / "ansible" / "roles").glob("*/**/*.yml")):
            if path in ALLOWLIST_PCT:
                continue
            for task in load_tasks(path):
                self.assertNotRegex(
                    command_text(task),
                    r"(^|\s)pct(\s|$)",
                    f"{path}: {task.get('name')}",
                )

    def test_forgejo_runner_secret_tasks_are_no_log(self) -> None:
        for name in (
            "Validate Forgejo Actions runner variables",
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Install Forgejo runner config",
        ):
            self.assertTrue(task_by_name(RUNNER_TASKS, name).get("no_log"), name)

    def test_minio_migration_uses_minio_network_namespace_without_host_binding(self) -> None:
        playbook = yaml.safe_load(MINIO_MIGRATION_PLAYBOOK.read_text(encoding="utf-8"))
        deployment = playbook[-1]
        migration = deployment["tasks"][0]
        block = migration["block"]
        by_name = {task["name"]: task for task in block}
        always = {task["name"]: task for task in migration["always"]}
        source = MINIO_MIGRATION_PLAYBOOK.read_text(encoding="utf-8")

        self.assertEqual(
            deployment["vars"]["onclave_migration_source_endpoint"],
            "http://127.0.0.1:9000",
        )
        self.assertEqual(
            deployment["vars"]["onclave_migration_destination_endpoint"],
            "http://seaweedfs-state:8333",
        )
        self.assertNotIn("onclave_migration_compose_override", deployment["vars"])

        network_discovery = by_name["Discover and validate the attached legacy Onclave network"]
        self.assertTrue(network_discovery["no_log"])
        network_script = network_discovery["ansible.builtin.shell"]
        self.assertIn("podman network inspect", network_script)
        self.assertIn('labels.get("com.docker.compose.project")', network_script)
        self.assertIn('io.podman.compose.project', network_script)

        for name in (
            "Verify SeaweedFS is not already attached to the legacy network",
            "Connect SeaweedFS temporarily to the verified legacy Onclave network",
            "Verify SeaweedFS attachment to the verified legacy network",
            "Resolve SeaweedFS address on the temporary legacy network",
            "Select the direct SeaweedFS migration endpoint",
            "Validate direct SeaweedFS S3 reachability from the MinIO network namespace",
        ):
            self.assertTrue(by_name[name].get("no_log"), name)

        direct_check = by_name[
            "Validate direct SeaweedFS S3 reachability from the MinIO network namespace"
        ]
        self.assertEqual(
            direct_check["ansible.builtin.command"]["argv"][:3],
            ["podman", "unshare", "nsenter"],
        )
        self.assertIn(
            "{{ onclave_migration_destination_effective_endpoint }}",
            direct_check["ansible.builtin.command"]["argv"],
        )

        pid_check = by_name["Verify the running MinIO network namespace and capture its PID"]
        self.assertTrue(pid_check["no_log"])
        pid_check_script = pid_check["ansible.builtin.shell"]
        self.assertIn('State", {}).get("Pid")', pid_check_script)
        self.assertIn("/proc/{pid}/ns/net", pid_check_script)

        for name in (
            "Run the resumable copy while Onclave core remains live",
            "Finalize the copy and write a private parity artifact",
        ):
            command = by_name[name]["ansible.builtin.command"]["argv"]
            self.assertEqual(command[:3], ["podman", "unshare", "nsenter"])
            self.assertIn("{{ onclave_migration_minio_pid.stdout | trim }}", command)
            self.assertIn("-n", command)
            self.assertIn("--", command)
            self.assertTrue(by_name[name]["no_log"])

        finalize = by_name["Finalize the copy and write a private parity artifact"]
        self.assertEqual(finalize["register"], "onclave_migration_finalize")
        self.assertFalse(finalize["failed_when"])
        parity_gate = by_name["Require exact final object parity"]
        self.assertIn("onclave_migration_finalize.rc == 0", parity_gate["ansible.builtin.assert"]["that"])
        self.assertTrue(parity_gate["no_log"])

        self.assertIn("http://127.0.0.1:9000", source)
        self.assertIn("http://seaweedfs-state:8333", source)
        self.assertNotIn("ONCLAVE_VAULT_S3_WORKSTATION_ENDPOINT", source)
        self.assertNotIn("onclave_migration_minio_port", source)
        self.assertNotIn("onclave_migration_compose_override", source)
        self.assertNotIn("binding=", source)
        self.assertNotIn("health=", source)
        self.assertNotIn("podman port", source)
        self.assertNotIn("podman rm", source)
        self.assertEqual(
            list(always),
            [
                "Disconnect SeaweedFS from the temporary legacy Onclave network",
                "Verify SeaweedFS was disconnected from the temporary legacy network",
                "Remove the temporary migration workspace",
            ],
        )
        self.assertIn(
            "onclave_migration_legacy_network is defined",
            always["Disconnect SeaweedFS from the temporary legacy Onclave network"]["when"],
        )
        self.assertTrue(
            by_name["Stop only Onclave core for the final migration window"]["when"]
            == "onclave_migration_mode == 'final'"
        )

    def test_caddy_override_directories_exist_before_templating(self) -> None:
        override_task_names = {
            "infra/ansible/roles/caddy_proxy/tasks/main.yml": (
                "Ensure DNS LXC Caddy systemd override directory exists",
                "Install DNS LXC Caddy systemd override",
            ),
            "infra/ansible/roles/forgejo/tasks/caddy.yml": (
                "Ensure Forgejo Caddy systemd override directory exists",
                "Install Forgejo Caddy systemd override",
            ),
            "infra/ansible/roles/infisical/tasks/main.yml": (
                "Ensure Infisical Caddy systemd override directory exists",
                "Install Infisical Caddy systemd override",
            ),
            "infra/ansible/roles/hermes/tasks/main.yml": (
                "Ensure Hermes Caddy systemd override directory exists",
                "Install Hermes Caddy systemd override",
            ),
        }
        for rel_path, (directory, override) in override_task_names.items():
            path = REPO / rel_path
            names = task_names(path)
            self.assertLess(names.index(directory), names.index(override), rel_path)
            self.assertEqual(
                task_by_name(path, directory)
                .get("ansible.builtin.file", {})
                .get("state"),
                "directory",
            )
            self.assertIn(
                "Restart caddy", task_by_name(path, override).get("notify", [])
            )

    def test_caddy_restart_handlers_reload_systemd_units(self) -> None:
        for role in ("caddy_proxy", "forgejo", "infisical", "hermes"):
            handler = (
                REPO / "infra" / "ansible" / "roles" / role / "handlers" / "main.yml"
            )
            self.assertIn(
                "daemon_reload: true", handler.read_text(encoding="utf-8"), str(handler)
            )

    def test_forgejo_runner_pve_access_targets_pve_inventory_host(self) -> None:
        directory = task_by_name(
            RUNNER_TASKS, "Ensure root SSH directory exists on Proxmox host"
        )
        authorization = task_by_name(
            RUNNER_TASKS, "Authorize Forgejo runner SSH key on Proxmox host"
        )
        trust = task_by_name(
            RUNNER_TASKS, "Trust Proxmox host key in Forgejo runner LXC"
        )
        key_generation = task_by_name(
            RUNNER_TASKS, "Ensure Forgejo runner SSH key exists"
        )
        for task in (directory, authorization):
            self.assertEqual(task.get("delegate_to"), "{{ groups['pve'][0] }}")
        self.assertNotIn("delegate_to", key_generation)
        self.assertIn("hostvars[groups['pve'][0]].ansible_host", command_text(trust))

    def test_direct_lxc_host_key_refresh_uses_proxmox_authority_not_network_scanning(
        self,
    ) -> None:
        play = load_tasks(DIRECT_ACCESS_PLAYBOOK)[0]
        tasks = [task for task in play.get("pre_tasks", []) if isinstance(task, dict)]
        names = [str(task.get("name")) for task in tasks]
        source = DIRECT_ACCESS_PLAYBOOK.read_text(encoding="utf-8")
        by_name = {str(task.get("name")): task for task in tasks}
        read_keys = by_name[
            "Read LXC SSH host public keys through authenticated Proxmox access"
        ]
        validate_keys = by_name[
            "Fail closed when Proxmox did not provide valid LXC host public keys"
        ]
        remove_stale = by_name[
            "Remove stale controller SSH trust for the direct inventory aliases"
        ]
        install_keys = by_name[
            "Install exact Proxmox-authoritative SSH keys for direct inventory aliases"
        ]

        self.assertIn("pct", command_text(read_keys))
        self.assertIn("exec", command_text(read_keys))
        self.assertIn("ssh_host_*_key.pub", command_text(read_keys))
        self.assertEqual(read_keys.get("delegate_to"), "{{ direct_access_pve_host }}")
        self.assertIn(
            "direct_access_pve_host",
            str(by_name["Validate direct LXC host-key refresh inputs"]),
        )
        self.assertTrue(read_keys.get("no_log"))
        self.assertTrue(validate_keys.get("no_log"))
        self.assertNotIn("ssh-keyscan", source)
        self.assertIn("direct_access_allowed_key_types", str(validate_keys))
        self.assertIn("A-Za-z0-9+/", str(validate_keys))
        self.assertIn("/tmp/homelab-infra/ansible/known_hosts", source)
        self.assertNotIn("/workspace/values/ansible/known_hosts", source)
        reset_trust = by_name["Reset the ephemeral controller known_hosts file"]
        trust_file = by_name[
            "Ensure the managed controller known_hosts file has restrictive permissions"
        ]
        trust_directory = by_name[
            "Ensure the managed controller known_hosts directory exists"
        ]
        self.assertEqual(trust_directory.get("delegate_to"), "localhost")
        self.assertEqual(trust_directory["ansible.builtin.file"].get("mode"), "0700")
        self.assertEqual(reset_trust.get("delegate_to"), "localhost")
        self.assertEqual(reset_trust["ansible.builtin.file"].get("state"), "absent")
        self.assertEqual(trust_file.get("delegate_to"), "localhost")
        self.assertEqual(trust_file["ansible.builtin.file"].get("state"), "touch")
        self.assertEqual(trust_file["ansible.builtin.file"].get("mode"), "0600")
        self.assertLess(
            names.index(str(reset_trust["name"])), names.index(str(trust_file["name"]))
        )
        self.assertLess(
            names.index(str(trust_file["name"])), names.index(str(remove_stale["name"]))
        )
        self.assertLess(
            names.index(str(remove_stale["name"])),
            names.index(str(install_keys["name"])),
        )
        self.assertIn("inventory_hostname", str(remove_stale))
        self.assertIn("ansible_host", str(remove_stale))
        self.assertIn("inventory_hostname", str(install_keys))
        self.assertIn("ansible_host", str(install_keys))
        self.assertFalse(play.get("gather_facts"))

    def test_vm_direct_access_verifies_proxmox_mac_before_keyscan(self) -> None:
        plays = load_tasks(VM_DIRECT_ACCESS_PLAYBOOK)
        self.assertEqual(len(plays), 1)
        tasks = plays[0]["pre_tasks"]
        by_name = {str(task["name"]): task for task in tasks}
        read_keys = by_name["Read VM SSH keys after Proxmox MAC ownership verification"]
        command = command_text(read_keys)
        self.assertIn("qm config", command)
        self.assertIn("ip neigh", command)
        self.assertLess(command.index("ip neigh"), command.index("ssh-keyscan"))
        self.assertEqual(read_keys.get("delegate_to"), "{{ direct_access_pve_host }}")
        self.assertTrue(read_keys.get("no_log"))
        self.assertTrue(
            by_name["Fail closed without valid Proxmox-verified VM SSH keys"].get(
                "no_log"
            )
        )
        self.assertIn("/tmp/homelab-infra/ansible/known_hosts", str(plays[0]))

    def test_vm_direct_access_callers_cover_registered_onramp_group(self) -> None:
        registry = json.loads(
            (REPO / "infra" / "services.json").read_text(encoding="utf-8")
        )["services"]
        direct_groups = {
            config["inventory"]["group"]
            for config in registry.values()
            if config.get("execution_resource") == "onramp_host"
        }
        caller_groups: set[str] = set()
        for path in sorted((REPO / "infra" / "ansible" / "playbooks").glob("*.yml")):
            for play in load_tasks(path):
                if (
                    play.get("ansible.builtin.import_playbook")
                    != "vm-direct-access-ready.yml"
                ):
                    continue
                group = play.get("vars", {}).get("direct_vm_access_target_group")
                self.assertIsInstance(group, str, str(path))
                self.assertIn(group, direct_groups, str(path))
                caller_groups.add(group)
        self.assertEqual(caller_groups, direct_groups)

    def test_all_direct_access_callers_select_only_registered_direct_lxc_groups(
        self,
    ) -> None:
        registry = json.loads(
            (REPO / "infra" / "services.json").read_text(encoding="utf-8")
        )["services"]
        direct_groups = {
            config["inventory"]["group"]
            for config in registry.values()
            if config.get("execution_resource") == "direct_lxc_known_hosts"
        }
        caller_groups: set[str] = set()
        for path in sorted((REPO / "infra" / "ansible" / "playbooks").glob("*.yml")):
            for play in load_tasks(path):
                if (
                    play.get("ansible.builtin.import_playbook")
                    != "direct-access-ready.yml"
                ):
                    continue
                group = play.get("vars", {}).get("direct_access_target_group")
                self.assertIsInstance(group, str, str(path))
                self.assertIn(group, direct_groups, str(path))
                caller_groups.add(group)
        self.assertEqual(caller_groups, direct_groups)

    def test_lxc_ready_checks_configured_node_before_pct(self) -> None:
        names = task_names(LXC_READY_TASKS)
        guard = "Fail when PVE inventory target does not match configured node"
        first_pct = (
            "Wait for LXC to report running "
            "{{ lxc_ready_name | default(lxc_ready_vmid) }}"
        )
        self.assertLess(names.index(guard), names.index(first_pct))
        guard_task = task_by_name(LXC_READY_TASKS, guard)
        self.assertNotIn("when", guard_task)
        self.assertIn("proxmox_node_name", str(guard_task))

    def test_verified_artifact_installs_check_hashes_before_atomic_moves(self) -> None:
        task_files = (
            REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "main.yml",
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "forgejo_runner"
            / "tasks"
            / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml",
        )
        for path in task_files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("sha256sum -c -", text, str(path))
            self.assertIn("mv -f", text, str(path))

    def test_caddy_build_is_shared_and_pinned(self) -> None:
        build_tasks = (
            REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml"
        )
        text = build_tasks.read_text(encoding="utf-8")
        self.assertIn("GOPROXY=proxy.golang.org,direct", text)
        self.assertIn("GOSUMDB=sum.golang.org", text)
        self.assertIn("caddy_build_cloudflare_version", text)
        for marker_name in (
            "Check installed Caddy build marker",
            "Verify installed Caddy build marker",
        ):
            self.assertIn(
                'GOTOOLCHAIN=local go version -m "$(command -v caddy)"',
                command_text(task_by_name(build_tasks, marker_name)),
                marker_name,
            )
        self.assertIn(
            'GOBIN="${tmp}/bin" GOTOOLCHAIN=local '
            "GOPROXY=proxy.golang.org,direct GOSUMDB=sum.golang.org\n"
            '        "${tmp}/go/bin/go" install',
            text,
        )
        self.assertIn(
            'PATH="${tmp}/go/bin:${PATH}" GOTOOLCHAIN=local '
            "GOPROXY=proxy.golang.org,direct GOSUMDB=sum.golang.org\n"
            '        "${tmp}/bin/xcaddy" build',
            text,
        )
        for path in CADDY_TASK_FILES[:4]:
            self.assertIn(
                "name: caddy_build", path.read_text(encoding="utf-8"), str(path)
            )

    def test_caddy_build_markers_verify_pinned_cloudflare_module_version(self) -> None:
        build_tasks = (
            REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml"
        )
        expected = (
            'awk \'$1 == "dep" && $2 == "github.com/caddy-dns/cloudflare" && '
            '$3 == "v{{ caddy_build_cloudflare_version }}" '
            "{ found=1 } END { exit !found }"
        )
        for name in (
            "Check installed Caddy build marker",
            "Verify installed Caddy build marker",
        ):
            marker = command_text(task_by_name(build_tasks, name))
            self.assertIn('go version -m "$(command -v caddy)"', marker, name)
            self.assertIn(expected, marker, name)

    def test_debian_security_updates_are_automatic_without_reboots(self) -> None:
        role = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "debian_security_updates"
            / "tasks"
            / "main.yml"
        )
        text = role.read_text(encoding="utf-8")
        self.assertIn(
            'APT::Periodic::Unattended-Upgrade "1"', text
        )  # public-safety: allow-ip
        self.assertIn(
            "codename=${distro_codename}-security", text
        )  # public-safety: allow-ip
        self.assertIn(
            'Unattended-Upgrade::Automatic-Reboot "false"', text
        )  # public-safety: allow-ip
        for name in (
            "technitium.yml",
            "forgejo.yml",
            "forgejo-runner.yml",
            "infisical.yml",
            "hermes.yml",
            "tailscale-client.yml",
            "onramp-host.yml",
        ):
            playbook = (REPO / "infra" / "ansible" / "playbooks" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn("debian_security_updates", playbook, name)

    def test_tailscale_uses_signed_debian_13_repository(self) -> None:
        path = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "tailscale_client"
            / "tasks"
            / "main.yml"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("trixie.noarmor.gpg", text)
        self.assertIn(
            "checksum: sha256:"
            "3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39",
            text,
        )
        self.assertIn("trixie.tailscale-keyring.list", text)
        self.assertIn(
            "checksum: sha256:"
            "5a1b21b30892bf22fb5d7c4f52fefe9b65efda2100e82abba2e0849da2a2264b",
            text,
        )
        self.assertIn("tailscale-archive-keyring.gpg", text)
        self.assertIn('name: "tailscale={{ tailscale_client_version }}"', text)
        self.assertIn("Verify installed Tailscale version", text)
        self.assertNotIn("tailscale.com/install.sh", text)

    def test_caddy_validation_does_not_fmt_overwrite_managed_files(self) -> None:
        for path in CADDY_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("caddy fmt --overwrite", text, str(path))
            self.assertIn(
                "caddy validate --config /etc/caddy/Caddyfile", text, str(path)
            )

    def test_curl_output_is_not_accidentally_streamed_to_ansible(self) -> None:
        for path in ANSIBLE_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"curl[^\n]*\n\s+-o\b",
                f"{path} has curl URL and -o split across YAML lines; folded "
                "blocks preserve the newline here, causing curl to stream binary "
                "to Ansible stdout",
            )

    def test_browser_facing_service_roles_have_http_smoke_checks(self) -> None:
        for path in SERVICE_SMOKE_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            health_tasks = path.with_name("health.yml")
            if "include_tasks: health.yml" in text and health_tasks.exists():
                text += health_tasks.read_text(encoding="utf-8")
            has_http_check = "ansible.builtin.uri:" in text or "      - curl\n" in text
            self.assertTrue(has_http_check, str(path))
            self.assertIn("retries:", text, str(path))
            self.assertIn("until:", text, str(path))

    def test_lightweight_service_roles_fail_on_active_checks(self) -> None:
        checks = {
            "infra/ansible/roles/forgejo_runner/tasks/main.yml": (
                "Verify Forgejo runner service is active"
            ),
            "infra/ansible/roles/onramp_host/tasks/main.yml": (
                "Verify rootless Podman user namespace as deploy user"
            ),
            "infra/ansible/roles/tailscale_client/tasks/main.yml": (
                "Verify tailscaled service is active"
            ),
        }
        for rel_path, task_name in checks.items():
            task = task_by_name(REPO / rel_path, task_name)
            self.assertNotEqual(task.get("failed_when"), False, rel_path)

    def test_forgejo_runner_registration_is_guarded_by_existing_lookup(self) -> None:
        existing = task_by_name(
            RUNNER_TASKS, "Check existing Forgejo Actions runner registration"
        )
        registration = task_by_name(
            RUNNER_TASKS, "Register Forgejo Actions runner with Forgejo"
        )
        config = task_by_name(RUNNER_TASKS, "Install Forgejo runner config")

        existing_text = command_text(existing)
        self.assertIn("action_runner", existing_text)
        self.assertIn("repository", existing_text)
        self.assertIn("repo_id", existing_text)
        self.assertIn("forgejo_runner_scope", existing_text)
        self.assertIn("forgejo_runner_name", existing_text)
        self.assertEqual(existing.get("changed_when"), False)
        self.assertIn(
            'forgejo_runner_existing_registration.stdout | trim == ""',
            str(registration.get("when")),
        )
        self.assertEqual(existing.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(registration.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(
            task_by_name(
                RUNNER_TASKS, "Normalize Forgejo repository-scoped runner ownership"
            ).get("delegate_to"),
            "{{ groups['forgejo'][0] }}",
        )
        self.assertNotIn("forgejo_runner_registration.stdout", str(config))
        self.assertIn(
            "forgejo_runner_uuid",
            str(task_by_name(RUNNER_TASKS, "Set Forgejo runner UUID")),
        )

    def test_forgejo_runner_registration_task_order(self) -> None:
        names = task_names(RUNNER_TASKS)
        ordered = [
            "Check existing Forgejo Actions runner registration",
            "Register Forgejo Actions runner with Forgejo",
            "Set Forgejo runner UUID",
            "Validate Forgejo runner UUID was resolved",
            "Normalize Forgejo repository-scoped runner ownership",
            "Install Forgejo runner config",
        ]
        indexes = [names.index(name) for name in ordered]
        self.assertEqual(indexes, sorted(indexes))

    def test_secret_files_are_direct_final_destinations_with_modes(self) -> None:
        checks = {
            "infra/ansible/roles/infisical/tasks/main.yml": (
                "/etc/infisical/infisical.env"
            ),
            "infra/ansible/roles/hermes/tasks/main.yml": "/etc/hermes-dashboard.env",
            "infra/ansible/roles/caddy_proxy/tasks/main.yml": "/etc/caddy/env",
            "infra/ansible/roles/forgejo_runner/tasks/main.yml": (
                "/etc/forgejo-runner/config.yml"
            ),
            "infra/ansible/roles/searxng_onramp/tasks/main.yml": (
                "{{ searxng_onramp_base_dir }}/settings.yml"
            ),
        }
        for rel_path, dest in checks.items():
            tasks = load_tasks(REPO / rel_path)
            matches = [task for task in tasks if dest in str(task)]
            self.assertTrue(matches, rel_path)
            self.assertTrue(any(task.get("no_log") for task in matches), rel_path)
            self.assertTrue(any("mode" in str(task) for task in matches), rel_path)

    def test_hermes_exports_native_searxng_url_key(self) -> None:
        template = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "hermes"
            / "templates"
            / "hermes-dashboard.env.j2"
        )
        text = template.read_text(encoding="utf-8")
        self.assertIn("HERMES_WEB_SEARXNG_URL={{ hermes_web_searxng_url }}", text)
        self.assertIn("SEARXNG_URL={{ hermes_web_searxng_url }}", text)

    def test_hermes_dashboard_uses_packaged_tui_bundle(self) -> None:
        env_template = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "hermes"
            / "templates"
            / "hermes-dashboard.env.j2"
        )
        tasks = REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml"
        self.assertIn(
            "HERMES_TUI_DIR=/usr/local/lib/hermes-agent/tui",
            env_template.read_text(encoding="utf-8"),
        )
        text = tasks.read_text(encoding="utf-8")
        self.assertIn("Link Hermes dashboard TUI bundle to the active release", text)
        self.assertIn("/usr/local/lib/hermes-agent/tui/dist/entry.js", text)
        self.assertIn(
            "/usr/local/lib/hermes-agent/venv/lib/python3.13/site-packages/hermes_cli/tui_dist/entry.js",
            text,
        )

    def test_hermes_passwordless_sudo_policy_is_validated(self) -> None:
        task = task_by_name(
            REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
            "Install passwordless sudo policy for Hermes runtime user",
        )
        copy = task["ansible.builtin.copy"]
        self.assertEqual(copy["dest"], "/etc/sudoers.d/hermes-runtime")
        self.assertEqual(copy["mode"], "0440")
        self.assertEqual(copy["validate"], "/usr/sbin/visudo -cf %s")
        self.assertIn("NOPASSWD: ALL", copy["content"])  # public-safety: allow-secret
        self.assertIn("hermes_runtime_user", copy["content"])

    def test_hermes_enables_linger_for_gateway_user_service(self) -> None:
        task = task_by_name(
            REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
            "Enable linger for Hermes runtime user services",
        )
        text = command_text(task)
        self.assertIn("loginctl\nenable-linger", text)
        self.assertIn("{{ hermes_runtime_user | default('anvil') }}", text)
        self.assertEqual(task.get("changed_when"), False)

    def test_targeted_apply_limits_ansible_to_target_service(self) -> None:
        text = (REPO / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        self.assertIn('target_service="${INFRA_TARGET_SERVICE:-}"', text)
        self.assertIn('storage_vars_args+=(--service "${target_service}")', text)
        self.assertIn('json.loads(sys.argv[1]).get(\\"storage_datasets\\")', text)
        self.assertIn('ansible_service_args+=(--service "${target_service}")', text)
        self.assertIn('"${ansible_service_args[@]}"', text)

    def test_public_workflow_entrypoints_are_executable(self) -> None:
        executable_paths = (
            "infra/ansible/inventory/tfvars.py",
            "scripts/apply-infra.sh",
            "scripts/apply-service.sh",
            "scripts/discover-values-remote.sh",
            "scripts/plan-infra.sh",
        )
        for rel_path in executable_paths:
            mode = (REPO / rel_path).stat().st_mode
            self.assertTrue(mode & 0o111, rel_path)

    def test_freellmapi_onramp_is_private_persistent_and_bws_backed(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "freellmapi_onramp"
        tasks = role / "tasks" / "main.yml"
        quadlet = (role / "templates" / "freellmapi-onramp.container.j2").read_text(
            encoding="utf-8"
        )
        environment = (role / "templates" / "freellmapi.env.j2").read_text(
            encoding="utf-8"
        )
        caddy = (role / "templates" / "freellmapi.caddy.j2").read_text(
            encoding="utf-8"
        )
        inventory_fixture = (
            REPO / "tests" / "fixtures" / "site-config" / "ansible" / "inventory" / "local.yml"
        ).read_text(encoding="utf-8")
        playbook = load_tasks(
            REPO / "infra" / "ansible" / "playbooks" / "freellmapi-onramp.yml"
        )
        registry = json.loads(
            (REPO / "infra" / "services.json").read_text(encoding="utf-8")
        )["services"]["freellmapi_onramp"]

        self.assertEqual(registry["dependencies"], ["onramp_host"])
        self.assertEqual(registry["execution_resource"], "onramp_host")
        self.assertTrue(registry["state_capable"])
        validate = task_by_name(tasks, "Validate FreeLLMAPI onramp required variables")
        self.assertIn(
            "freellmapi_onramp_bind_address == '127.0.0.1'",
            validate["ansible.builtin.assert"]["that"],
        )
        self.assertIn(
            "freellmapi_image: ghcr.io/tashfeenahmed/freellmapi:v0.8.4@sha256:",
            inventory_fixture,
        )
        self.assertIn("PublishPort={{ freellmapi_onramp_bind_address }}:", quadlet)
        self.assertIn("{{ freellmapi_onramp_base_dir }}/data:/app/server/data:Z,U", quadlet)
        self.assertIn("HealthCmd=node -e", quadlet)
        self.assertIn("Notify=healthy", quadlet)
        self.assertIn("[Install]\nWantedBy=default.target", quadlet)
        names = [
            task["name"]
            for task in yaml.safe_load(tasks.read_text(encoding="utf-8"))
        ]
        install_quadlet = names.index("Install FreeLLMAPI rootless Quadlet")
        self.assertLess(
            names.index("Stop and disable legacy FreeLLMAPI rootless unit"),
            install_quadlet,
        )
        self.assertLess(
            names.index("Stop and remove legacy FreeLLMAPI Compose container"),
            install_quadlet,
        )
        health_assertion = task_by_name(
            tasks, "Assert FreeLLMAPI container reached healthy state"
        )
        self.assertIn("podman', 'inspect", str(health_assertion))
        catalog = yaml.safe_load(
            (REPO / "infra" / "ansible" / "vars" / "service-state.yml").read_text(
                encoding="utf-8"
            )
        )["managed_service_state_catalog"]
        self.assertIn(
            "{{ onramp_host_deploy_dir }}/freellmapi",
            [item["path"] for item in catalog["freellmapi_onramp"]["paths"]],
        )
        self.assertEqual(
            catalog["freellmapi_onramp"]["user_services_skip_enable"],
            ["freellmapi-onramp.service"],
        )
        self.assertIn("ENCRYPTION_KEY={{ freellmapi_encryption_key }}", environment)
        self.assertIn("reverse_proxy 127.0.0.1:", caddy)
        self.assertTrue(
            task_by_name(tasks, "Install FreeLLMAPI private environment")["no_log"]
        )
        secret_task = next(
            task
            for task in playbook
            if task.get("name") == "Configure FreeLLMAPI on shared onramp host"
        )["pre_tasks"][0]
        self.assertTrue(secret_task["no_log"])
        self.assertIn("FREELLMAPI_ENCRYPTION_KEY", str(secret_task))

    def test_seaweedfs_route_uses_bws_endpoint_and_existing_dns_catalog(self) -> None:
        playbook = yaml.safe_load(SEAWEEDFS_ONRAMP_PLAYBOOK.read_text(encoding="utf-8"))
        deployment = playbook[-1]
        self.assertIn("seaweedfs_onramp_server_name", deployment["vars"])
        self.assertIn("seaweedfs_s3_endpoint", deployment["vars"]["seaweedfs_onramp_server_name"])
        self.assertIn("seaweedfs_onramp_onclave_server_name", deployment["vars"])
        self.assertIn(
            "ONCLAVE_VAULT_S3_WORKSTATION_ENDPOINT",
            deployment["vars"]["seaweedfs_onramp_onclave_server_name"],
        )
        names = [task["name"] for task in deployment["pre_tasks"]]
        self.assertIn("Validate SeaweedFS Caddy hostname from BWS workstation HTTPS endpoint", names)
        self.assertIn("Validate existing BWS DNS workflow contains SeaweedFS Caddy hostname", names)
        self.assertIn("ONCLAVE_VAULT_S3_WORKSTATION_ENDPOINT", SEAWEEDFS_ONRAMP_PLAYBOOK.read_text(encoding="utf-8"))

    def test_seaweedfs_onclave_identity_is_bucket_and_object_scoped(self) -> None:
        source = SEAWEEDFS_S3_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('"Read:menos"', source)
        self.assertIn('"Read:menos/*"', source)
        self.assertIn('"Write:menos/*"', source)
        self.assertIn('"List:menos"', source)
        self.assertIn('"Tagging:menos/*"', source)
        onclave = source.split('"name": {{ seaweedfs_onramp_onclave_identity', 1)[1]
        self.assertNotIn('"Admin', onclave)
        self.assertNotIn('"Read"', onclave)
        self.assertNotIn('"Write"', onclave)
        self.assertNotIn('"List"', onclave)

    def test_onclave_onramp_consumes_host_rendered_bws_secrets(self) -> None:
        plays = yaml.safe_load(ONCLAVE_ONRAMP_PLAYBOOK.read_text(encoding="utf-8"))
        deployment = plays[-1]
        self.assertIn(
            "ONCLAVE_VAULT_S3_WORKSTATION_ENDPOINT",
            deployment["vars"]["onclave_onramp_s3_hostname"],
        )
        self.assertIn(
            "onclave_onramp_s3_hostname",
            deployment["vars"]["onclave_onramp_s3_endpoint"],
        )
        self.assertIn(":443", deployment["vars"]["onclave_onramp_s3_endpoint"])
        self.assertTrue(deployment["vars"]["onclave_onramp_s3_secure"])
        tasks = {task["name"]: task for task in deployment["pre_tasks"]}
        resolve_task = tasks["Resolve host-rendered Onclave BWS secrets"]
        facts = resolve_task["ansible.builtin.set_fact"]
        self.assertIn(
            "lookup('env', 'RABBITMQ_DEFAULT_USER')",
            facts["onclave_rabbitmq_default_user"],
        )
        self.assertIn(
            "lookup('env', 'RABBITMQ_DEFAULT_PASS')",
            facts["onclave_rabbitmq_default_pass"],
        )
        self.assertTrue(resolve_task["no_log"])

        snapshot = (REPO / "scripts" / "bws-snapshot.py").read_text(encoding="utf-8")
        # Exact runtime-key isolation is exercised in test_bws_snapshot, not by
        # requiring a fragile tuple slice that leaks newly appended service keys.
        self.assertIn('"RABBITMQ_DEFAULT_USER"', snapshot)
        self.assertIn('"RABBITMQ_DEFAULT_PASS"', snapshot)

    def test_onclave_cutover_is_explicit_and_quiesces_before_backup_or_removal(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        defaults = yaml.safe_load(
            (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertFalse(defaults["onclave_onramp_enable_cutover"])
        source = (role / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("Verify legacy Onclave target is stopped before cutover", source)
        self.assertIn("Create final Onclave corpus backup while writes are quiesced", source)
        stop_legacy = task_by_name(
            role / "tasks" / "main.yml",
            "Stop legacy Onclave containers before final corpus backup",
        )
        self.assertIn(
            "com.docker.compose.project=onclave",
            stop_legacy["ansible.builtin.shell"],
        )
        self.assertIn(
            "com.docker.compose.service=${service}",
            stop_legacy["ansible.builtin.shell"],
        )
        self.assertTrue(stop_legacy["no_log"])
        backup_block = task_by_name(
            role / "tasks" / "main.yml",
            "Create final Onclave corpus backup while writes are quiesced",
        )
        local_tasks = {task["name"]: task for task in backup_block["block"]}
        for local_task_name in (
            "Create orchestration-owned Onclave quiescence marker",
            "Write exact fresh final Onclave corpus artifact",
        ):
            local_task = local_tasks[local_task_name]
            self.assertEqual(local_task["delegate_to"], "localhost")
            self.assertFalse(local_task["become"])
        remove_legacy = task_by_name(
            role / "tasks" / "main.yml",
            "Remove legacy Onclave containers",
        )
        self.assertIn(
            "for service in rabbitmq postgres ollama searxng docling-serve onclave-core",
            remove_legacy["ansible.builtin.shell"],
        )
        self.assertIn(
            "com.docker.compose.project=onclave",
            remove_legacy["ansible.builtin.shell"],
        )
        self.assertIn(
            "com.docker.compose.service=${service}",
            remove_legacy["ansible.builtin.shell"],
        )
        self.assertTrue(remove_legacy["no_log"])
        role_task_names = task_names(role / "tasks" / "main.yml")
        self.assertLess(
            role_task_names.index(
                "Start native RabbitMQ before credential reconciliation"
            ),
            role_task_names.index("Reconcile persisted RabbitMQ password from BWS"),
        )
        self.assertLess(
            role_task_names.index("Reconcile persisted RabbitMQ password from BWS"),
            role_task_names.index("Enable native Onclave rootless target"),
        )
        enable_unified = task_by_name(
            role / "tasks" / "main.yml",
            "Enable native Onclave rootless target",
        )
        self.assertEqual(
            enable_unified["ansible.builtin.systemd_service"]["state"],
            "started",
        )
        handlers = {
            handler["name"]: handler
            for handler in yaml.safe_load(
                (role / "handlers" / "main.yml").read_text(encoding="utf-8")
            )
        }
        changed_service_handler = handlers["Restart changed Onclave service"]
        self.assertEqual(
            changed_service_handler["ansible.builtin.systemd_service"]["name"],
            "{{ item }}",
        )
        self.assertIn(
            "not (onclave_onramp_topology_changed | default(false) | bool)",
            changed_service_handler["when"],
        )
        self.assertNotIn("onclave_onramp_enable_cutover", str(changed_service_handler))
        target_handler = handlers[
            "Restart Onclave target after topology change"
        ]
        self.assertEqual(
            target_handler["ansible.builtin.systemd_service"]["name"],
            "onclave-onramp.target",
        )
        self.assertIn(
            "onclave_onramp_topology_changed | default(false) | bool",
            target_handler["when"],
        )
        environment_contracts = task_by_name(
            role / "tasks" / "main.yml",
            "Install native Onclave service environment contracts",
        )
        self.assertEqual(
            environment_contracts["loop"],
            [
                {"name": "rabbitmq", "unit": "onclave-rabbitmq.service"},
                {"name": "postgres", "unit": "onclave-postgres.service"},
                {"name": "ollama", "unit": "onclave-ollama.service"},
                {"name": "searxng", "unit": "onclave-searxng.service"},
                {"name": "docling", "unit": "onclave-docling.service"},
                {"name": "core", "unit": "onclave-core.service"},
            ],
        )
        authorized_keys = task_by_name(
            role / "tasks" / "main.yml",
            "Install unified Onclave authorized public keys",
        )
        self.assertNotIn("notify", authorized_keys)
        key_tracking = task_by_name(
            role / "tasks" / "main.yml",
            "Track Onclave core for an authorized-key contract change",
        )
        self.assertIn("onclave-core.service", str(key_tracking))
        self.assertEqual(key_tracking["notify"], "Restart changed Onclave services")
        container_contracts = task_by_name(
            role / "tasks" / "main.yml",
            "Install native Onclave rootless container units",
        )
        self.assertEqual(
            container_contracts["loop"],
            [
                {
                    "template": "onclave-rabbitmq.container",
                    "unit": "onclave-rabbitmq.service",
                },
                {
                    "template": "onclave-postgres.container",
                    "unit": "onclave-postgres.service",
                },
                {
                    "template": "onclave-ollama.container",
                    "unit": "onclave-ollama.service",
                },
                {
                    "template": "onclave-searxng.container",
                    "unit": "onclave-searxng.service",
                },
                {
                    "template": "onclave-docling.container",
                    "unit": "onclave-docling.service",
                },
                {
                    "template": "onclave-core.container",
                    "unit": "onclave-core.service",
                },
            ],
        )
        network_topology = task_by_name(
            role / "tasks" / "main.yml",
            "Track changed Onclave network topology",
        )
        self.assertIn(
            "onclave_onramp_network_contract.changed",
            network_topology["ansible.builtin.set_fact"][
                "onclave_onramp_topology_changed"
            ],
        )
        self.assertEqual(network_topology["notify"], "Restart Onclave target")
        target_contract = task_by_name(
            role / "tasks" / "main.yml",
            "Install native Onclave rootless target",
        )
        self.assertNotIn("notify", target_contract)
        target_topology = task_by_name(
            role / "tasks" / "main.yml",
            "Track changed Onclave target membership topology",
        )
        self.assertEqual(target_topology["notify"], "Restart Onclave target")
        self.assertIn(
            "onclave_onramp_target_contract.changed",
            target_topology["ansible.builtin.set_fact"][
                "onclave_onramp_topology_changed"
            ],
        )
        state_catalog = yaml.safe_load(
            (REPO / "infra" / "ansible" / "vars" / "service-state.yml").read_text(
                encoding="utf-8"
            )
        )["managed_service_state_catalog"]["onclave_onramp"]
        self.assertEqual(state_catalog["user_services"], ["onclave-onramp.target"])
        rabbitmq_reconcile = task_by_name(
            role / "tasks" / "main.yml",
            "Reconcile persisted RabbitMQ password from BWS",
        )
        self.assertEqual(rabbitmq_reconcile["retries"], 24)
        self.assertEqual(rabbitmq_reconcile["delay"], 5)
        self.assertIn(
            "onclave_onramp_rabbitmq_reconcile.rc == 0",
            rabbitmq_reconcile["until"],
        )
        verify_stopped = task_by_name(
            role / "tasks" / "main.yml",
            "Verify no legacy Onclave containers are running before backup",
        )
        self.assertIn(
            "label=com.docker.compose.project=onclave",
            verify_stopped["ansible.builtin.shell"],
        )
        minio_find = task_by_name(
            role / "tasks" / "main.yml",
            "Find retired MinIO containers from the previous Onclave stack",
        )
        minio_matcher = minio_find["ansible.builtin.shell"]
        self.assertIn("label=com.docker.compose.project=onclave", minio_matcher)
        self.assertIn("label=io.podman.compose.project=onclave", minio_matcher)
        self.assertIn("label=com.docker.compose.service=minio", minio_matcher)
        self.assertIn("label=io.podman.compose.service=minio", minio_matcher)
        self.assertIn("name=^onclave[-_]minio[-_][0-9]+$", minio_matcher)
        self.assertNotIn(
            "ansible.builtin.command",
            minio_find,
            "A service-only filter could select unrelated rootless MinIO containers",
        )
        for task_name in (
            "Remove legacy Onclave containers",
            "Remove retired MinIO containers without touching their data directory",
        ):
            task = task_by_name(role / "tasks" / "main.yml", task_name)
            self.assertIn("onclave_onramp_enable_cutover", str(task.get("when")))
        for task_name in (
            "Discover existing Onclave SearXNG volume identities",
            "Install native Onclave rootless network",
            "Install native Onclave rootless container units",
            "Install native Onclave rootless target",
            "Enable native Onclave rootless target",
            "Install Onclave Caddy site snippets",
            "Verify native Onclave rootless target is active",
        ):
            task = task_by_name(role / "tasks" / "main.yml", task_name)
            self.assertNotIn("onclave_onramp_enable_cutover", str(task.get("when")))

    def test_onclave_steady_state_restart_scope_and_observations_are_explicit(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        tasks = load_tasks(role / "tasks" / "main.yml")
        handlers = load_tasks(role / "handlers" / "main.yml")
        topology_notifiers = [
            task["name"]
            for task in tasks
            if task.get("notify") == "Restart Onclave target"
        ]
        self.assertEqual(
            topology_notifiers,
            [
                "Track changed Onclave network topology",
                "Track changed Onclave target membership topology",
            ],
        )
        unit_notifiers = [
            task["name"]
            for task in tasks
            if task.get("notify") == "Restart changed Onclave services"
        ]
        self.assertEqual(
            unit_notifiers,
            [
                "Track services with changed Onclave environment contracts",
                "Track Onclave core for an authorized-key contract change",
                "Track services with changed Onclave container contracts",
            ],
        )
        self.assertIn("item.unit", str(task_by_name(
            role / "tasks" / "main.yml",
            "Track services with changed Onclave environment contracts",
        )))
        self.assertIn("item.unit", str(task_by_name(
            role / "tasks" / "main.yml",
            "Track services with changed Onclave container contracts",
        )))
        for handler in handlers:
            self.assertNotIn("onclave_onramp_enable_cutover", str(handler))
        lifecycle = task_by_name(
            role / "tasks" / "main.yml",
            "Observe post-apply Onclave unit lifecycle state",
        )
        self.assertIn("--property=NRestarts", lifecycle["ansible.builtin.command"]["argv"])
        report = task_by_name(
            role / "tasks" / "main.yml",
            "Report safe Onclave steady-state rollout observations",
        )
        report_text = str(report["ansible.builtin.debug"]["msg"])
        for field in (
            "revision",
            "affected_units",
            "requested_restart_actions",
            "automatic_restart_counter_note",
            "readiness",
            "diagnostic_health",
            "metrics",
        ):
            self.assertIn(field, report_text)
        self.assertIn("not requested restart actions", report_text)

    def test_onclave_adopts_existing_storage_and_renders_unified_contract(
        self,
    ) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        role_tasks = role / "tasks" / "main.yml"
        defaults = yaml.safe_load(
            (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            defaults["onclave_onramp_data_root"],
            "{{ onramp_host_deploy_dir }}/menos/data",
        )
        inspect = task_by_name(role_tasks, "Inspect adopted state directories")
        self.assertEqual(
            inspect["loop"],
            [
                "{{ onclave_onramp_data_root }}/postgres",
                "{{ onclave_onramp_data_root }}/ollama",
            ],
        )
        self.assertNotIn(
            "Create missing adopted state directories", task_names(role_tasks)
        )
        consumer_seams = task_by_name(
            role_tasks, "Validate unified Onclave app definition consumer seams"
        )
        conditions = consumer_seams["ansible.builtin.assert"]["that"]
        self.assertIn(
            "onclave_onramp_definition.services.rabbitmq.ports | default([]) | length == 0",
            conditions,
        )
        for mapping in (
            "'POSTGRES_PASSWORD' in onclave_onramp_upstream_text",
            "'SEARXNG_SECRET' in onclave_onramp_upstream_text",
        ):
            self.assertIn(mapping, conditions)
        native_contract = task_by_name(
            role_tasks, "Validate native Onclave Quadlet source contract"
        )
        conditions = native_contract["ansible.builtin.assert"]["that"]
        self.assertIn(
            "onclave_onramp_definition.services['onclave-core'].depends_on.keys() | sort == "
            "['docling-serve', 'minio', 'ollama', 'postgres', 'rabbitmq', 'searxng']",
            conditions,
        )
        self.assertIn(
            "onclave_onramp_definition.services['onclave-core'].healthcheck.test == "
            "['CMD', 'wget', '-qO-', 'http://127.0.0.1:8000/live']",
            conditions,
        )
        for variable in (
            "ONCLAVE_VAULT_JOB_RECOVERY_BATCH_SIZE",
            "ONCLAVE_VAULT_JOB_LEASE_MS",
            "ONCLAVE_VAULT_DELIVERY_POLL_INTERVAL_MS",
            "ONCLAVE_VAULT_DELIVERY_LEASE_MS",
            "ONCLAVE_VAULT_DELIVERY_RETRY_BASE_MS",
            "ONCLAVE_VAULT_DELIVERY_RETRY_MAX_MS",
            "ONCLAVE_VAULT_DELIVERY_BATCH_SIZE",
        ):
            self.assertIn(variable, str(conditions))

        templates = role / "templates"
        container_templates = tuple(templates.glob("*.container.j2"))
        rabbitmq = (templates / "onclave-rabbitmq.container.j2").read_text(
            encoding="utf-8"
        )
        postgres = (templates / "onclave-postgres.container.j2").read_text(
            encoding="utf-8"
        )
        ollama = (templates / "onclave-ollama.container.j2").read_text(
            encoding="utf-8"
        )
        searxng = (templates / "onclave-searxng.container.j2").read_text(
            encoding="utf-8"
        )
        core = (templates / "onclave-core.container.j2").read_text(
            encoding="utf-8"
        )
        target = (templates / "onclave-onramp.target.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "{{ onclave_onramp_base_dir }}/data/rabbitmq:/var/lib/rabbitmq:Z,U",
            rabbitmq,
        )
        self.assertIn(
            "{{ onclave_onramp_data_root }}/postgres:/var/lib/postgresql/data:Z,U",
            postgres,
        )
        self.assertIn(
            "{{ onclave_onramp_data_root }}/ollama:/root/.ollama:Z,U", ollama
        )
        self.assertIn(
            "{{ onclave_onramp_base_dir }}/data/onclave:/data:Z,U", core
        )
        self.assertIn(
            "{{ onclave_onramp_base_dir }}/authorized_keys:/keys/authorized_keys:ro,Z",
            core,
        )
        self.assertIn("PublishPort=127.0.0.1:{{ onclave_onramp_core_port }}:8000", core)
        health_cmd = (
            "HealthCmd=node -e 'fetch(\"http://127.0.0.1:8000/live\")"
            ".then(response => { if (!response.ok) process.exit(1); })"
            ".catch(() => process.exit(1))'"
        )
        self.assertIn(health_cmd, core)
        self.assertIn("HealthOnFailure=kill", core)
        self.assertIn("Restart=always", core)
        self.assertIn("Notify=healthy", postgres)
        self.assertIn("Requires=onclave-rabbitmq.service onclave-postgres.service", core)
        self.assertIn("After=onclave-rabbitmq.service onclave-postgres.service", core)
        self.assertIn(
            "Volume={{ onclave_onramp_searxng_config_volume }}:/etc/searxng",
            searxng,
        )
        self.assertIn(
            "Volume={{ onclave_onramp_searxng_cache_volume }}:/var/cache/searxng",
            searxng,
        )
        required_services = (
            "onclave-rabbitmq.service onclave-postgres.service "
            "onclave-ollama.service onclave-searxng.service "
            "onclave-docling.service onclave-core.service"
        )
        self.assertIn(f"Requires={required_services}", target)
        image_contracts = {
            "onclave-rabbitmq.container.j2": "Image={{ onclave_rabbitmq_image }}",
            "onclave-postgres.container.j2": "Image={{ onclave_postgres_image }}",
            "onclave-ollama.container.j2": "Image={{ onclave_ollama_image }}",
            "onclave-searxng.container.j2": "Image={{ onclave_searxng_image }}",
            "onclave-docling.container.j2": "Image={{ onclave_docling_image }}",
            "onclave-core.container.j2": (
                "Image={{ onclave_core_image_repository }}:"
                "{{ onclave_core_image_tag }}@{{ onclave_core_image_digest }}"
            ),
        }
        all_containers = "\n".join(
            path.read_text(encoding="utf-8") for path in container_templates
        )
        self.assertNotIn("minio", all_containers)
        self.assertEqual(len(container_templates), 6)
        for path in container_templates:
            source = path.read_text(encoding="utf-8")
            self.assertIn(image_contracts[path.name], source, path.name)
            self.assertIn("Network=onclave.network", source, path.name)
            self.assertIn("Restart=always", source, path.name)
            if path.name != "onclave-core.container.j2":
                self.assertNotIn("PublishPort=", source, path.name)
        discovery = task_by_name(
            role_tasks, "Discover existing Onclave SearXNG volume identities"
        )
        discovery_source = discovery["ansible.builtin.shell"]
        self.assertIn('("/etc/searxng", "/var/cache/searxng")', discovery_source)
        self.assertIn('{"nodev", "exec", "nosuid", "rbind"}', discovery_source)
        self.assertIn('mount.get("Propagation") == "rprivate"', discovery_source)
        self.assertTrue(discovery["no_log"])
        volume_guard = task_by_name(
            role_tasks,
            "Verify preserved Onclave SearXNG volumes survived container removal",
        )
        self.assertEqual(
            volume_guard["ansible.builtin.command"]["argv"][:3],
            ["podman", "volume", "exists"],
        )
        self.assertTrue(volume_guard["no_log"])

    def test_onclave_env_uses_canonical_vault_inputs(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        defaults = yaml.safe_load(
            (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        argument_specs = yaml.safe_load(
            (role / "meta" / "argument_specs.yml").read_text(encoding="utf-8")
        )
        options = argument_specs["argument_specs"]["main"]["options"]
        core_template = (role / "templates" / "core.env.j2").read_text(encoding="utf-8")
        template = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (role / "templates").glob("*.env.j2")
        )
        self.assertEqual(defaults["onclave_onramp_s3_bucket"], "menos")
        self.assertEqual(defaults["onclave_onramp_embedding_provider"], "openrouter")
        self.assertEqual(defaults["onclave_onramp_embedding_model"], "intfloat/e5-large-v2")
        self.assertEqual(
            {
                key: defaults[key]
                for key in (
                    "onclave_onramp_job_recovery_batch_size",
                    "onclave_onramp_job_lease_ms",
                    "onclave_onramp_delivery_poll_interval_ms",
                    "onclave_onramp_delivery_lease_ms",
                    "onclave_onramp_delivery_retry_base_ms",
                    "onclave_onramp_delivery_retry_max_ms",
                    "onclave_onramp_delivery_batch_size",
                )
            },
            {
                "onclave_onramp_job_recovery_batch_size": 50,
                "onclave_onramp_job_lease_ms": 300000,
                "onclave_onramp_delivery_poll_interval_ms": 1000,
                "onclave_onramp_delivery_lease_ms": 300000,
                "onclave_onramp_delivery_retry_base_ms": 1000,
                "onclave_onramp_delivery_retry_max_ms": 900000,
                "onclave_onramp_delivery_batch_size": 50,
            },
        )
        for name in (
            "onclave_onramp_authorized_keys",
            "onclave_onramp_postgres_password",
            "onclave_onramp_postgres_database",
            "onclave_onramp_postgres_user",
            "onclave_onramp_s3_access_key",
            "onclave_onramp_s3_secret_key",
            "onclave_onramp_searxng_secret",
            "onclave_onramp_webshare_proxy_username",
            "onclave_onramp_webshare_proxy_password",
            "onclave_onramp_youtube_api_key",
            "onclave_onramp_openrouter_api_key",
            "onclave_onramp_anthropic_api_key",
        ):
            self.assertTrue(options[name]["required"])
            self.assertNotIn(name, defaults)
        for key in (
            "ONCLAVE_VAULT_SSH_PUBLIC_KEYS_PATH=/keys/authorized_keys",
            "ONCLAVE_VAULT_POSTGRES_PASSWORD={{ onclave_onramp_postgres_password }}",
            "ONCLAVE_VAULT_POSTGRES_DATABASE={{ onclave_onramp_postgres_database }}",
            "ONCLAVE_VAULT_POSTGRES_USER={{ onclave_onramp_postgres_user }}",
            "ONCLAVE_VAULT_S3_ENDPOINT_URL={{ onclave_onramp_s3_endpoint }}",
            "ONCLAVE_VAULT_S3_ACCESS_KEY={{ onclave_onramp_s3_access_key }}",
            "ONCLAVE_VAULT_S3_SECRET_KEY={{ onclave_onramp_s3_secret_key }}",
            "SEARXNG_SECRET={{ onclave_onramp_searxng_secret }}",
            "ONCLAVE_VAULT_WEBSHARE_PROXY_USERNAME={{ onclave_onramp_webshare_proxy_username }}",
            "ONCLAVE_VAULT_WEBSHARE_PROXY_PASSWORD={{ onclave_onramp_webshare_proxy_password }}",
            "ONCLAVE_VAULT_YOUTUBE_API_KEY={{ onclave_onramp_youtube_api_key }}",
            "ONCLAVE_VAULT_OPENROUTER_API_KEY={{ onclave_onramp_openrouter_api_key }}",
            "ONCLAVE_VAULT_ANTHROPIC_API_KEY={{ onclave_onramp_anthropic_api_key }}",
            "ONCLAVE_VAULT_OPENAI_API_KEY={{ onclave_onramp_openai_api_key }}",
            "ONCLAVE_VAULT_CALLBACK_URL={{ onclave_onramp_callback_url }}",
            "ONCLAVE_VAULT_CALLBACK_SECRET={{ onclave_onramp_callback_secret }}",
            "ONCLAVE_VAULT_S3_BUCKET={{ onclave_onramp_s3_bucket }}",
            "ONCLAVE_VAULT_EMBEDDING_PROVIDER={{ onclave_onramp_embedding_provider }}",
            "ONCLAVE_VAULT_EMBEDDING_MODEL={{ onclave_onramp_embedding_model }}",
            "ONCLAVE_VAULT_JOB_RECOVERY_BATCH_SIZE={{ onclave_onramp_job_recovery_batch_size }}",
            "ONCLAVE_VAULT_JOB_LEASE_MS={{ onclave_onramp_job_lease_ms }}",
            (
                "ONCLAVE_VAULT_DELIVERY_POLL_INTERVAL_MS="
                "{{ onclave_onramp_delivery_poll_interval_ms }}"
            ),
            "ONCLAVE_VAULT_DELIVERY_LEASE_MS={{ onclave_onramp_delivery_lease_ms }}",
            "ONCLAVE_VAULT_DELIVERY_RETRY_BASE_MS={{ onclave_onramp_delivery_retry_base_ms }}",
            "ONCLAVE_VAULT_DELIVERY_RETRY_MAX_MS={{ onclave_onramp_delivery_retry_max_ms }}",
            "ONCLAVE_VAULT_DELIVERY_BATCH_SIZE={{ onclave_onramp_delivery_batch_size }}",
        ):
            self.assertIn(key, template)
        for retired_key in (
            "\nPOSTGRES_PASSWORD=",
            "\nS3_ACCESS_KEY=",
            "\nS3_SECRET_KEY=",
            "\nSEARXNG_SECRET=",
            "\nWEBSHARE_PROXY_USERNAME=",
            "\nWEBSHARE_PROXY_PASSWORD=",
            "\nYOUTUBE_API_KEY=",
            "\nOPENROUTER_API_KEY=",
            "\nANTHROPIC_API_KEY=",
            "\nOPENAI_API_KEY=",
            "\nCALLBACK_URL=",
            "\nCALLBACK_SECRET=",
        ):
            self.assertNotIn(retired_key, core_template)

    def test_onclave_operational_gates_separate_liveness_diagnostics_and_readiness(self) -> None:
        role_tasks = ONCLAVE_ONRAMP_TASKS
        live = task_by_name(role_tasks, "Verify unified Onclave process liveness")
        health = task_by_name(
            role_tasks, "Read unified Onclave diagnostic health and source revision"
        )
        health_contract = task_by_name(
            role_tasks, "Verify safe unified Onclave diagnostic health contract"
        )
        ready = task_by_name(
            role_tasks,
            "Verify unified Onclave dependency readiness after automatic migration",
        )
        metrics = task_by_name(
            role_tasks, "Verify unified Onclave Prometheus metric families"
        )
        self.assertTrue(live["ansible.builtin.uri"]["url"].endswith("/live"))
        self.assertEqual(health["ansible.builtin.uri"]["status_code"], [200, 503])
        health_conditions = health_contract["ansible.builtin.assert"]["that"]
        self.assertIn(
            "onclave_onramp_health.json.git_sha == onclave_source_git_sha",
            health_conditions,
        )
        for condition in (
            "onclave_onramp_health.json.transcript.proxy.mode in ['webshare', 'custom', 'direct']",
            "onclave_onramp_health.json.transcript.proxy.configured is boolean",
            (
                "onclave_onramp_health.json.transcript.proxy.credentialStatus "
                "in ['present', 'missing', 'not_applicable']"
            ),
            (
                "onclave_onramp_health.json.transcript.proxy.dispatcherStatus "
                "in ['owned', 'injected', 'none']"
            ),
            "onclave_onramp_health.json.transcript.proxy.connectivity == 'not_checked'",
        ):
            self.assertIn(condition, health_conditions)
        for condition in (
            "onclave_onramp_ready.json.checks.postgres | default('') == 'ok'",
            "onclave_onramp_ready.json.checks.s3 | default('') == 'ok'",
            "onclave_onramp_ready.json.checks.ollama | default('') in ['ok', 'skipped']",
            "onclave_onramp_ready.json.checks.openrouter | default('') == 'ok'",
            "onclave_onramp_ready.json.checks.broker | default('') == 'ok'",
        ):
            self.assertIn(condition, ready["until"])
        self.assertEqual(len(metrics["loop"]), 10)
        names = task_names(role_tasks)
        self.assertLess(
            names.index("Enable native Onclave rootless target"),
            names.index(
                "Verify unified Onclave dependency readiness after automatic migration"
            ),
        )
        self.assertTrue(
            task_by_name(
                role_tasks, "Verify unified Onclave HTTPS liveness route locally"
            ).get("retries")
        )

    def test_onclave_signed_api_check_runs_once_on_the_controller(self) -> None:
        validation = task_by_name(
            ONCLAVE_ONRAMP_TASKS,
            "Validate public diagnostics and signed Onclave API",
        )
        command = validation["block"][0]
        self.assertEqual(command.get("delegate_to"), "localhost")
        self.assertFalse(command.get("become"))
        self.assertTrue(command.get("no_log"))
        self.assertNotIn("retries", command)
        self.assertEqual(
            command["ansible.builtin.command"]["argv"],
            [
                "{{ ansible_playbook_python }}",
                "{{ playbook_dir }}/../../../scripts/check-onclave-api.py",
                "https://{{ onclave_server_name }}",
                "~/.ssh/id_ed25519",
            ],
        )
        self.assertEqual(
            validation["rescue"][0]["ansible.builtin.fail"]["msg"],
            "Onclave diagnostics or signed API validation failed",
        )

    def test_onclave_omits_completed_retired_service_and_proxy_cleanup(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        role_tasks = role / "tasks" / "main.yml"
        names = task_names(role_tasks)
        role_task_source = role_tasks.read_text(encoding="utf-8")
        defaults = (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        argument_specs = (role / "meta" / "argument_specs.yml").read_text(
            encoding="utf-8"
        )
        service_registry = (REPO / "infra" / "services.json").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("menos-onramp", role_task_source)
        self.assertNotIn("menos.caddy", role_task_source)
        self.assertNotIn("menos_onramp_", role_task_source)
        self.assertNotIn("onclave_onramp_management_port", role_task_source)
        self.assertNotIn("onclave_onramp_management_port", defaults)
        self.assertNotIn("onclave_onramp_management_port", argument_specs)
        self.assertNotIn("onclave_onramp_amqp_allowed_cidrs", role_task_source)
        self.assertNotIn("onclave_onramp_amqp_allowed_cidrs", defaults)
        self.assertNotIn("onclave_onramp_amqp_allowed_cidrs", argument_specs)
        self.assertNotIn("onclave_onramp_amqp_allowed_cidrs", service_registry)
        self.assertNotIn("Allow approved clients to reach Onclave AMQP", names)

        caddy = (role / "templates" / "onclave.caddy.j2").read_text(encoding="utf-8")
        self.assertNotIn("management_port", caddy)
        self.assertNotIn("rabbitmq_server_name", caddy)

        remove_amqp_firewall = task_by_name(
            role_tasks, "Remove retired inbound Onclave AMQP firewall rules"
        )
        self.assertEqual(
            remove_amqp_firewall["loop"], "{{ onramp_host_allowed_ssh_cidrs }}"
        )
        self.assertEqual(
            remove_amqp_firewall["ansible.builtin.command"]["argv"],
            [
                "ufw",
                "--force",
                "delete",
                "allow",
                "from",
                "{{ item }}",
                "to",
                "any",
                "port",
                "{{ onclave_onramp_amqp_port | string }}",
                "proto",
                "tcp",
            ],
        )
        self.assertTrue(remove_amqp_firewall["no_log"])
        amqp_port_tasks = [
            task
            for task in load_tasks(role_tasks)
            if "onclave_onramp_amqp_port" in str(task)
        ]
        self.assertEqual(
            [task["name"] for task in amqp_port_tasks],
            [
                "Validate unified Onclave onramp required variables",
                "Remove retired inbound Onclave AMQP firewall rules",
            ],
        )

    def test_onclave_installs_pinned_backup_helpers_and_runtime_warmup_checks(
        self,
    ) -> None:
        role_tasks = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "onclave_onramp"
            / "tasks"
            / "main.yml"
        )
        helpers = task_by_name(
            role_tasks, "Install pinned unified Onclave PostgreSQL backup helpers"
        )
        self.assertEqual(
            [item["name"] for item in helpers["loop"]],
            ["backup-postgres.sh", "restore-postgres.sh"],
        )
        self.assertEqual(helpers["ansible.builtin.get_url"]["mode"], "0750")
        model = task_by_name(
            role_tasks, "Verify configured Onclave embedding provider"
        )
        bucket = task_by_name(
            role_tasks, "Verify SeaweedFS application bucket through the Onclave S3 contract"
        )
        self.assertIn("/api/pull", command_text(model))
        self.assertIn("/api/embed", command_text(model))
        self.assertIn("https://openrouter.ai/api/v1/embeddings", command_text(model))
        self.assertIn("bucketExists", command_text(bucket))
        self.assertIn("putObject", command_text(bucket))
        self.assertIn("removeObject", command_text(bucket))
        self.assertTrue(model.get("no_log"))
        self.assertTrue(bucket.get("no_log"))

    def test_onclave_onramp_reconciles_persisted_rabbitmq_password(self) -> None:
        role_tasks = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "onclave_onramp"
            / "tasks"
            / "main.yml"
        )
        verify = task_by_name(
            role_tasks, "Verify persisted RabbitMQ password matches BWS"
        )
        self.assertIn("authenticate_user", verify["ansible.builtin.command"]["argv"])
        self.assertFalse(verify["changed_when"])
        self.assertFalse(verify["failed_when"])
        self.assertTrue(verify["no_log"])
        reconcile = task_by_name(
            role_tasks, "Reconcile persisted RabbitMQ password from BWS"
        )
        self.assertIn("change_password", reconcile["ansible.builtin.command"]["argv"])
        self.assertEqual(
            reconcile["when"], "onclave_onramp_rabbitmq_auth.rc != 0"
        )
        self.assertTrue(reconcile["no_log"])

    def test_onramp_default_http_ports_do_not_collide(self) -> None:
        onclave_defaults = yaml.safe_load(
            (
                REPO
                / "infra"
                / "ansible"
                / "roles"
                / "onclave_onramp"
                / "defaults"
                / "main.yml"
            ).read_text(encoding="utf-8")
        )
        searxng_defaults = yaml.safe_load(
            (
                REPO
                / "infra"
                / "ansible"
                / "roles"
                / "searxng_onramp"
                / "defaults"
                / "main.yml"
            ).read_text(encoding="utf-8")
        )
        self.assertNotEqual(
            onclave_defaults["onclave_onramp_core_port"],
            searxng_defaults["searxng_onramp_container_port"],
        )

    def test_searxng_onramp_uses_deterministic_json_endpoints(self) -> None:
        environment = Environment(autoescape=False)
        environment.filters["bool"] = bool
        rendered = environment.from_string(
            SEARXNG_SETTINGS_TEMPLATE.read_text(encoding="utf-8")
        ).render(
            searxng_secret_key="public-safe-placeholder",
            searxng_onramp_enable_public_url=True,
            searxng_public_url="https://searxng.example.internal",
            searxng_onramp_instance_name="Homelab SearXNG",
        )
        settings = yaml.safe_load(rendered)
        self.assertEqual(settings["search"]["formats"], ["html", "json"])
        self.assertTrue(settings["use_default_settings"])
        self.assertEqual(settings["search"]["safe_search"], 1)
        self.assertEqual(settings["outgoing"]["request_timeout"], 5.0)
        self.assertEqual(settings["outgoing"]["max_request_timeout"], 8.0)
        engines = {engine["name"]: engine for engine in settings["engines"]}
        self.assertEqual({name for name, engine in engines.items() if not engine["disabled"]}, {"google", "brave"})
        self.assertTrue(engines["startpage"]["disabled"])
        self.assertTrue(engines["duckduckgo"]["disabled"])
        self.assertNotIn("inactive", str(settings["engines"]))

        health = task_by_name(
            SEARXNG_ONRAMP_TASKS, "Verify SearXNG loopback health endpoint"
        )
        self.assertTrue(health.get("retries"))
        self.assertEqual(health["ansible.builtin.uri"]["status_code"], 200)
        self.assertTrue(health["ansible.builtin.uri"]["return_content"])
        self.assertIn("/healthz", health["ansible.builtin.uri"]["url"])
        self.assertIn("searxng_onramp_loopback_check.content == 'OK'", health["until"])

        config = task_by_name(
            SEARXNG_ONRAMP_TASKS, "Verify SearXNG HTTPS configuration endpoint"
        )
        self.assertTrue(config.get("retries"))
        self.assertEqual(config.get("delegate_to"), "localhost")
        self.assertFalse(config.get("become"))
        config_uri = config["ansible.builtin.uri"]
        self.assertTrue(config_uri["validate_certs"])
        self.assertFalse(config_uri["use_proxy"])
        self.assertEqual(config_uri["follow_redirects"], "none")
        for field in (
            "instance_name",
            "safe_search",
            "version",
            "engines",
            "categories",
        ):
            self.assertIn(field, str(config["until"]))

        search = task_by_name(
            SEARXNG_ONRAMP_TASKS,
            "Verify SearXNG JSON search handler rejects a missing query",
        )
        self.assertEqual(search.get("delegate_to"), "localhost")
        self.assertFalse(search.get("become"))
        search_uri = search["ansible.builtin.uri"]
        self.assertEqual(search_uri["status_code"], 400)
        self.assertIn("/search?format=json", search_uri["url"])
        self.assertNotIn("retries", search)
        self.assertIn("No query", search["failed_when"])

    def test_searxng_onramp_ports_are_loopback_only(self) -> None:
        compose = (
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "searxng_onramp"
            / "templates"
            / "docker-compose.yml.j2"
        )
        text = compose.read_text(encoding="utf-8")
        self.assertIn(
            "{{ searxng_onramp_bind_address }}:"
            "{{ searxng_onramp_container_port }}:8080",
            text,
        )
        self.assertNotIn(
            "0.0.0.0:{{ searxng_onramp_container_port }}:8080", text
        )  # public-safety: allow-ip
        task = task_by_name(
            REPO
            / "infra"
            / "ansible"
            / "roles"
            / "searxng_onramp"
            / "tasks"
            / "main.yml",
            "Validate SearXNG onramp required variables",
        )
        self.assertIn(
            "searxng_onramp_bind_address in ['127.0.0.1', '::1']", str(task)
        )  # public-safety: allow-ip


if __name__ == "__main__":
    unittest.main()

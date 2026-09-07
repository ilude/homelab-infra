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
ONCLAVE_ONRAMP_PLAYBOOK = (
    REPO / "infra" / "ansible" / "playbooks" / "onclave-onramp.yml"
)
ONCLAVE_ONRAMP_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "onclave_onramp" / "tasks" / "main.yml"
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
        ("freellmapi_onramp", "freellmapi-onramp.service.j2"),
        ("searxng_onramp", "searxng-onramp.service.j2"),
        ("onclave_onramp", "onclave-onramp.service.j2"),
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
        compose = (role / "templates" / "docker-compose.yml.j2").read_text(
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
        self.assertFalse(registry["state_capable"])
        validate = task_by_name(tasks, "Validate FreeLLMAPI onramp required variables")
        self.assertIn(
            "freellmapi_onramp_bind_address == '127.0.0.1'",
            validate["ansible.builtin.assert"]["that"],
        )
        self.assertIn(
            "freellmapi_image: ghcr.io/tashfeenahmed/freellmapi:v0.8.4@sha256:",
            inventory_fixture,
        )
        self.assertIn("{{ freellmapi_onramp_bind_address }}:", compose)
        self.assertIn("./data:/app/server/data:Z,U", compose)
        self.assertIn("/api/ping", compose)
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

    def test_onclave_onramp_consumes_host_rendered_bws_secrets(self) -> None:
        plays = yaml.safe_load(ONCLAVE_ONRAMP_PLAYBOOK.read_text(encoding="utf-8"))
        deployment = plays[-1]
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
                "{{ onclave_onramp_data_root }}/minio",
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
            "'POSTGRES_PASSWORD: ${ONCLAVE_VAULT_POSTGRES_PASSWORD:?}' in onclave_onramp_upstream_text",
            "'MINIO_ROOT_USER: ${ONCLAVE_VAULT_S3_ACCESS_KEY:?}' in onclave_onramp_upstream_text",
            "'MINIO_ROOT_PASSWORD: ${ONCLAVE_VAULT_S3_SECRET_KEY:?}' in onclave_onramp_upstream_text",
            "'SEARXNG_SECRET: ${ONCLAVE_VAULT_SEARXNG_SECRET:?}' in onclave_onramp_upstream_text",
        ):
            self.assertIn(mapping, conditions)
        render = task_by_name(
            role_tasks, "Render unified Onclave app definition for the onramp host"
        )
        expression = render["ansible.builtin.set_fact"][
            "onclave_onramp_compose_content"
        ]
        self.assertIn("'onclave-core'", expression)
        self.assertNotIn("onclave_onramp_amqp_port", expression)
        self.assertNotIn("onclave_onramp_management_port", expression)
        self.assertEqual(expression.count("'ports': []"), 5)
        for mount in (
            "onclave_onramp_data_root ~ '/postgres:/var/lib/postgresql/data:Z,U'",
            "onclave_onramp_data_root ~ '/minio:/data:Z,U'",
            "onclave_onramp_data_root ~ '/ollama:/root/.ollama:Z,U'",
            "'./authorized_keys:/keys/authorized_keys:ro,Z'",
        ):
            self.assertIn(mount, expression)
        self.assertIn("'configs': []", expression)
        self.assertIn("'OLLAMA_KEEP_ALIVE': '-1'", expression)
        self.assertIn("onclave_onramp_rootless_healthcheck", expression)

        validate = task_by_name(
            role_tasks, "Validate rendered unified Onclave network isolation"
        )
        conditions = validate["ansible.builtin.assert"]["that"]
        self.assertIn(
            "onclave_onramp_rendered_definition.services.rabbitmq.ports | default([]) | length == 0",
            conditions,
        )
        self.assertIn(
            "onclave_onramp_rendered_definition.services['onclave-core'].volumes == "
            "['./data/onclave:/data:Z,U', './authorized_keys:/keys/authorized_keys:ro,Z']",
            conditions,
        )
        self.assertIn(
            "onclave_onramp_rendered_definition.services.postgres.volumes == "
            "[onclave_onramp_data_root ~ '/postgres:/var/lib/postgresql/data:Z,U']",
            conditions,
        )

    def test_onclave_env_uses_canonical_vault_inputs(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "onclave_onramp"
        defaults = yaml.safe_load(
            (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        )
        argument_specs = yaml.safe_load(
            (role / "meta" / "argument_specs.yml").read_text(encoding="utf-8")
        )
        options = argument_specs["argument_specs"]["main"]["options"]
        template = (role / "templates" / "onclave.env.j2").read_text(encoding="utf-8")
        self.assertEqual(defaults["onclave_onramp_s3_bucket"], "menos")
        self.assertEqual(defaults["onclave_onramp_embedding_provider"], "openrouter")
        self.assertEqual(defaults["onclave_onramp_embedding_model"], "intfloat/e5-large-v2")
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
            "POSTGRES_IMAGE={{ onclave_postgres_image }}",
            "MINIO_IMAGE={{ onclave_minio_image }}",
            "OLLAMA_IMAGE={{ onclave_ollama_image }}",
            "SEARXNG_IMAGE={{ onclave_searxng_image }}",
            "DOCLING_IMAGE={{ onclave_docling_image }}",
            "ONCLAVE_AUTHORIZED_KEYS_FILE=./authorized_keys",
            "ONCLAVE_VAULT_POSTGRES_PASSWORD={{ onclave_onramp_postgres_password }}",
            "ONCLAVE_VAULT_POSTGRES_DATABASE={{ onclave_onramp_postgres_database }}",
            "ONCLAVE_VAULT_POSTGRES_USER={{ onclave_onramp_postgres_user }}",
            "ONCLAVE_VAULT_S3_ACCESS_KEY={{ onclave_onramp_s3_access_key }}",
            "ONCLAVE_VAULT_S3_SECRET_KEY={{ onclave_onramp_s3_secret_key }}",
            "ONCLAVE_VAULT_SEARXNG_SECRET={{ onclave_onramp_searxng_secret }}",
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
            self.assertNotIn(retired_key, template)

    def test_onclave_unified_health_gate_checks_revision_and_dependencies(self) -> None:
        role_tasks = ONCLAVE_ONRAMP_TASKS
        health = task_by_name(
            role_tasks, "Verify unified Onclave health and source revision"
        )
        ready = task_by_name(role_tasks, "Verify unified Onclave dependency readiness")
        self.assertIn(
            "onclave_onramp_health.json.git_sha | default('') == onclave_source_git_sha",
            health["until"],
        )
        self.assertIn(
            "onclave_onramp_health.json.broker.connected | default(false) | bool",
            health["until"],
        )
        for condition in (
            "onclave_onramp_ready.json.checks.postgres | default('') == 'ok'",
            "onclave_onramp_ready.json.checks.s3 | default('') == 'ok'",
            "onclave_onramp_ready.json.checks.ollama | default('') == 'ok'",
        ):
            self.assertIn(condition, ready["until"])
        self.assertTrue(
            task_by_name(role_tasks, "Verify unified Onclave HTTPS route locally").get(
                "retries"
            )
        )

    def test_onclave_signed_api_check_runs_once_on_the_controller(self) -> None:
        validation = task_by_name(ONCLAVE_ONRAMP_TASKS, "Validate signed Onclave API")
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
            "signed Onclave API validation failed",
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
            role_tasks, "Ensure unified Onclave managed MinIO bucket exists"
        )
        self.assertIn("/api/pull", command_text(model))
        self.assertIn("/api/embed", command_text(model))
        self.assertIn("https://openrouter.ai/api/v1/embeddings", command_text(model))
        self.assertIn("bucketExists", command_text(bucket))
        self.assertIn("makeBucket", command_text(bucket))
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
        self.assertEqual(reconcile["when"], "onclave_onramp_rabbitmq_auth.rc != 0")
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

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
RUNNER_TASKS = REPO / "infra" / "ansible" / "roles" / "forgejo_runner" / "tasks" / "main.yml"
LXC_READY_TASKS = REPO / "infra" / "ansible" / "roles" / "lxc_ready" / "tasks" / "main.yml"
DIRECT_ACCESS_PLAYBOOK = REPO / "infra" / "ansible" / "playbooks" / "direct-access-ready.yml"
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
    REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml",
)
ALLOWLIST_PCT = {
    REPO / "infra" / "ansible" / "roles" / "lxc_ready" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo_bind_mount" / "tasks" / "main.yml",
    REPO / "infra" / "ansible" / "roles" / "forgejo_bind_mount" / "handlers" / "main.yml",
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
    def test_service_roles_do_not_use_pct_for_steady_state(self) -> None:
        for path in sorted((REPO / "infra" / "ansible" / "roles").glob("*/**/*.yml")):
            if path in ALLOWLIST_PCT:
                continue
            for task in load_tasks(path):
                self.assertNotRegex(command_text(task), r"(^|\s)pct(\s|$)", f"{path}: {task.get('name')}")

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
            self.assertEqual(task_by_name(path, directory).get("ansible.builtin.file", {}).get("state"), "directory")
            self.assertIn("Restart caddy", task_by_name(path, override).get("notify", []))

    def test_caddy_restart_handlers_reload_systemd_units(self) -> None:
        for role in ("caddy_proxy", "forgejo", "infisical", "hermes"):
            handler = REPO / "infra" / "ansible" / "roles" / role / "handlers" / "main.yml"
            self.assertIn("daemon_reload: true", handler.read_text(encoding="utf-8"), str(handler))

    def test_forgejo_runner_pve_access_targets_pve_inventory_host(self) -> None:
        directory = task_by_name(RUNNER_TASKS, "Ensure root SSH directory exists on Proxmox host")
        authorization = task_by_name(RUNNER_TASKS, "Authorize Forgejo runner SSH key on Proxmox host")
        trust = task_by_name(RUNNER_TASKS, "Trust Proxmox host key in Forgejo runner LXC")
        key_generation = task_by_name(RUNNER_TASKS, "Ensure Forgejo runner SSH key exists")
        for task in (directory, authorization):
            self.assertEqual(task.get("delegate_to"), "{{ groups['pve'][0] }}")
        self.assertNotIn("delegate_to", key_generation)
        self.assertIn("hostvars[groups['pve'][0]].ansible_host", command_text(trust))

    def test_direct_lxc_host_key_refresh_uses_proxmox_authority_not_network_scanning(self) -> None:
        play = load_tasks(DIRECT_ACCESS_PLAYBOOK)[0]
        tasks = [task for task in play.get("pre_tasks", []) if isinstance(task, dict)]
        names = [str(task.get("name")) for task in tasks]
        source = DIRECT_ACCESS_PLAYBOOK.read_text(encoding="utf-8")
        by_name = {str(task.get("name")): task for task in tasks}
        read_keys = by_name["Read LXC SSH host public keys through authenticated Proxmox access"]
        validate_keys = by_name["Fail closed when Proxmox did not provide valid LXC host public keys"]
        remove_stale = by_name["Remove stale controller SSH trust for the direct inventory aliases"]
        install_keys = by_name["Install exact Proxmox-authoritative SSH keys for direct inventory aliases"]

        self.assertIn("pct", command_text(read_keys))
        self.assertIn("exec", command_text(read_keys))
        self.assertIn("ssh_host_*_key.pub", command_text(read_keys))
        self.assertEqual(read_keys.get("delegate_to"), "{{ direct_access_pve_host }}")
        self.assertIn("direct_access_pve_host", str(by_name["Validate direct LXC host-key refresh inputs"]))
        self.assertTrue(read_keys.get("no_log"))
        self.assertTrue(validate_keys.get("no_log"))
        self.assertNotIn("ssh-keyscan", source)
        self.assertIn("direct_access_allowed_key_types", str(validate_keys))
        self.assertIn("A-Za-z0-9+/", str(validate_keys))
        self.assertIn("/tmp/homelab-infra/ansible/known_hosts", source)
        self.assertNotIn("/workspace/values/ansible/known_hosts", source)
        trust_file = by_name["Ensure the managed controller known_hosts file has restrictive permissions"]
        trust_directory = by_name["Ensure the managed controller known_hosts directory exists"]
        self.assertEqual(trust_directory.get("delegate_to"), "localhost")
        self.assertEqual(trust_directory["ansible.builtin.file"].get("mode"), "0700")
        self.assertEqual(trust_file.get("delegate_to"), "localhost")
        self.assertEqual(trust_file["ansible.builtin.file"].get("state"), "touch")
        self.assertEqual(trust_file["ansible.builtin.file"].get("mode"), "0600")
        self.assertLess(names.index(str(trust_file["name"])), names.index(str(remove_stale["name"])))
        self.assertLess(names.index(str(remove_stale["name"])), names.index(str(install_keys["name"])))
        self.assertIn("inventory_hostname", str(remove_stale))
        self.assertIn("ansible_host", str(remove_stale))
        self.assertIn("inventory_hostname", str(install_keys))
        self.assertIn("ansible_host", str(install_keys))
        self.assertFalse(play.get("gather_facts"))

    def test_all_direct_access_callers_select_only_registered_direct_lxc_groups(self) -> None:
        registry = json.loads((REPO / "infra" / "services.json").read_text(encoding="utf-8"))["services"]
        direct_groups = {
            config["inventory"]["group"]
            for config in registry.values()
            if config.get("execution_resource") == "direct_lxc_known_hosts"
        }
        caller_groups: set[str] = set()
        for path in sorted((REPO / "infra" / "ansible" / "playbooks").glob("*.yml")):
            for play in load_tasks(path):
                if play.get("ansible.builtin.import_playbook") != "direct-access-ready.yml":
                    continue
                group = play.get("vars", {}).get("direct_access_target_group")
                self.assertIsInstance(group, str, str(path))
                self.assertIn(group, direct_groups, str(path))
                caller_groups.add(group)
        self.assertEqual(caller_groups, direct_groups)

    def test_lxc_ready_checks_configured_node_before_pct(self) -> None:
        names = task_names(LXC_READY_TASKS)
        guard = "Fail when PVE inventory target does not match configured node"
        first_pct = "Wait for LXC to report running {{ lxc_ready_name | default(lxc_ready_vmid) }}"
        self.assertLess(names.index(guard), names.index(first_pct))
        guard_task = task_by_name(LXC_READY_TASKS, guard)
        self.assertNotIn("when", guard_task)
        self.assertIn("proxmox_node_name", str(guard_task))

    def test_verified_artifact_installs_check_hashes_before_atomic_moves(self) -> None:
        task_files = (
            REPO / "infra" / "ansible" / "roles" / "forgejo" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "forgejo_runner" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "infisical" / "tasks" / "main.yml",
            REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml",
        )
        for path in task_files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("sha256sum -c -", text, str(path))
            self.assertIn("mv -f", text, str(path))

    def test_caddy_build_is_shared_and_pinned(self) -> None:
        build_tasks = REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml"
        text = build_tasks.read_text(encoding="utf-8")
        self.assertIn("GOPROXY=proxy.golang.org,direct", text)
        self.assertIn("GOSUMDB=sum.golang.org", text)
        self.assertIn("caddy_build_cloudflare_version", text)
        for marker_name in ("Check installed Caddy build marker", "Verify installed Caddy build marker"):
            self.assertIn(
                'GOTOOLCHAIN=local go version -m "$(command -v caddy)"',
                command_text(task_by_name(build_tasks, marker_name)),
                marker_name,
            )
        self.assertIn(
            'GOBIN="${tmp}/bin" GOTOOLCHAIN=local GOPROXY=proxy.golang.org,direct GOSUMDB=sum.golang.org\n'
            '        "${tmp}/go/bin/go" install',
            text,
        )
        self.assertIn(
            'PATH="${tmp}/go/bin:${PATH}" GOTOOLCHAIN=local GOPROXY=proxy.golang.org,direct GOSUMDB=sum.golang.org\n'
            '        "${tmp}/bin/xcaddy" build',
            text,
        )
        for path in CADDY_TASK_FILES[:4]:
            self.assertIn("name: caddy_build", path.read_text(encoding="utf-8"), str(path))

    def test_caddy_build_markers_verify_pinned_cloudflare_module_version(self) -> None:
        build_tasks = REPO / "infra" / "ansible" / "roles" / "caddy_build" / "tasks" / "main.yml"
        expected = (
            "awk '$1 == \"dep\" && $2 == \"github.com/caddy-dns/cloudflare\" && "
            '$3 == \"v{{ caddy_build_cloudflare_version }}\" { found=1 } END { exit !found }'
        )
        for name in ("Check installed Caddy build marker", "Verify installed Caddy build marker"):
            marker = command_text(task_by_name(build_tasks, name))
            self.assertIn('go version -m "$(command -v caddy)"', marker, name)
            self.assertIn(expected, marker, name)

    def test_debian_security_updates_are_automatic_without_reboots(self) -> None:
        role = REPO / "infra" / "ansible" / "roles" / "debian_security_updates" / "tasks" / "main.yml"
        text = role.read_text(encoding="utf-8")
        self.assertIn('APT::Periodic::Unattended-Upgrade "1"', text)  # public-safety: allow-ip
        self.assertIn('codename=${distro_codename}-security', text)  # public-safety: allow-ip
        self.assertIn('Unattended-Upgrade::Automatic-Reboot "false"', text)  # public-safety: allow-ip
        for name in (
            "technitium.yml",
            "forgejo.yml",
            "forgejo-runner.yml",
            "infisical.yml",
            "hermes.yml",
            "tailscale-client.yml",
            "onramp-host.yml",
        ):
            playbook = (REPO / "infra" / "ansible" / "playbooks" / name).read_text(encoding="utf-8")
            self.assertIn("debian_security_updates", playbook, name)

    def test_tailscale_uses_signed_debian_13_repository(self) -> None:
        path = REPO / "infra" / "ansible" / "roles" / "tailscale_client" / "tasks" / "main.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("trixie.noarmor.gpg", text)
        self.assertIn("checksum: sha256:3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39", text)
        self.assertIn("trixie.tailscale-keyring.list", text)
        self.assertIn("checksum: sha256:5a1b21b30892bf22fb5d7c4f52fefe9b65efda2100e82abba2e0849da2a2264b", text)
        self.assertIn("tailscale-archive-keyring.gpg", text)
        self.assertIn('name: "tailscale={{ tailscale_client_version }}"', text)
        self.assertIn("Verify installed Tailscale version", text)
        self.assertNotIn("tailscale.com/install.sh", text)

    def test_caddy_validation_does_not_fmt_overwrite_managed_files(self) -> None:
        for path in CADDY_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("caddy fmt --overwrite", text, str(path))
            self.assertIn("caddy validate --config /etc/caddy/Caddyfile", text, str(path))

    def test_curl_output_is_not_accidentally_streamed_to_ansible(self) -> None:
        for path in ANSIBLE_TASK_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"curl[^\n]*\n\s+-o\b",
                f"{path} has curl URL and -o split across YAML lines; folded blocks preserve the newline here, causing curl to stream binary to Ansible stdout",
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
            "infra/ansible/roles/forgejo_runner/tasks/main.yml": "Verify Forgejo runner service is active",
            "infra/ansible/roles/onramp_host/tasks/main.yml": "Verify rootless Podman user namespace as deploy user",
            "infra/ansible/roles/tailscale_client/tasks/main.yml": "Verify tailscaled service is active",
        }
        for rel_path, task_name in checks.items():
            task = task_by_name(REPO / rel_path, task_name)
            self.assertNotEqual(task.get("failed_when"), False, rel_path)

    def test_forgejo_runner_registration_is_guarded_by_existing_lookup(self) -> None:
        existing = task_by_name(RUNNER_TASKS, "Check existing Forgejo Actions runner registration")
        registration = task_by_name(RUNNER_TASKS, "Register Forgejo Actions runner with Forgejo")
        config = task_by_name(RUNNER_TASKS, "Install Forgejo runner config")

        existing_text = command_text(existing)
        self.assertIn("action_runner", existing_text)
        self.assertIn("repository", existing_text)
        self.assertIn("repo_id", existing_text)
        self.assertIn("forgejo_runner_scope", existing_text)
        self.assertIn("forgejo_runner_name", existing_text)
        self.assertEqual(existing.get("changed_when"), False)
        self.assertIn('forgejo_runner_existing_registration.stdout | trim == ""', str(registration.get("when")))
        self.assertEqual(existing.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(registration.get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertEqual(task_by_name(RUNNER_TASKS, "Normalize Forgejo repository-scoped runner ownership").get("delegate_to"), "{{ groups['forgejo'][0] }}")
        self.assertNotIn("forgejo_runner_registration.stdout", str(config))
        self.assertIn("forgejo_runner_uuid", str(task_by_name(RUNNER_TASKS, "Set Forgejo runner UUID")))

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
            "infra/ansible/roles/infisical/tasks/main.yml": "/etc/infisical/infisical.env",
            "infra/ansible/roles/hermes/tasks/main.yml": "/etc/hermes-dashboard.env",
            "infra/ansible/roles/caddy_proxy/tasks/main.yml": "/etc/caddy/env",
            "infra/ansible/roles/forgejo_runner/tasks/main.yml": "/etc/forgejo-runner/config.yml",
            "infra/ansible/roles/searxng_onramp/tasks/main.yml": "{{ searxng_onramp_base_dir }}/settings.yml",
        }
        for rel_path, dest in checks.items():
            tasks = load_tasks(REPO / rel_path)
            matches = [task for task in tasks if dest in str(task)]
            self.assertTrue(matches, rel_path)
            self.assertTrue(any(task.get("no_log") for task in matches), rel_path)
            self.assertTrue(any("mode" in str(task) for task in matches), rel_path)

    def test_hermes_exports_native_searxng_url_key(self) -> None:
        template = REPO / "infra" / "ansible" / "roles" / "hermes" / "templates" / "hermes-dashboard.env.j2"
        text = template.read_text(encoding="utf-8")
        self.assertIn("HERMES_WEB_SEARXNG_URL={{ hermes_web_searxng_url }}", text)
        self.assertIn("SEARXNG_URL={{ hermes_web_searxng_url }}", text)

    def test_hermes_dashboard_uses_packaged_tui_bundle(self) -> None:
        env_template = REPO / "infra" / "ansible" / "roles" / "hermes" / "templates" / "hermes-dashboard.env.j2"
        tasks = REPO / "infra" / "ansible" / "roles" / "hermes" / "tasks" / "main.yml"
        self.assertIn("HERMES_TUI_DIR=/usr/local/lib/hermes-agent/tui", env_template.read_text(encoding="utf-8"))
        text = tasks.read_text(encoding="utf-8")
        self.assertIn("Link Hermes dashboard TUI bundle to the active release", text)
        self.assertIn("/usr/local/lib/hermes-agent/tui/dist/entry.js", text)
        self.assertIn("/usr/local/lib/hermes-agent/venv/lib/python3.13/site-packages/hermes_cli/tui_dist/entry.js", text)

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

    def test_searxng_onramp_ports_are_loopback_only(self) -> None:
        compose = REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "templates" / "docker-compose.yml.j2"
        text = compose.read_text(encoding="utf-8")
        self.assertIn("{{ searxng_onramp_bind_address }}:{{ searxng_onramp_container_port }}:8080", text)
        self.assertNotIn("0.0.0.0:{{ searxng_onramp_container_port }}:8080", text)  # public-safety: allow-ip
        task = task_by_name(REPO / "infra" / "ansible" / "roles" / "searxng_onramp" / "tasks" / "main.yml", "Validate SearXNG onramp required variables")
        self.assertIn("searxng_onramp_bind_address in ['127.0.0.1', '::1']", str(task))  # public-safety: allow-ip


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra" / "ansible"
PLAYBOOK = ANSIBLE / "playbooks" / "herdr.yml"
ROLES = ANSIBLE / "roles"


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def tasks(path: Path) -> list[dict[str, Any]]:
    value = load_yaml(path) or []
    return [item for item in value if isinstance(item, dict)]


def task(path: Path, name: str) -> dict[str, Any]:
    for item in tasks(path):
        if item.get("name") == name:
            return item
    raise AssertionError(f"missing task {name!r} in {path}")


class HerdrRuntimeContractTests(unittest.TestCase):
    def test_playbook_has_strict_lifecycle_and_return_handoff_sequence(self) -> None:
        plays = load_yaml(PLAYBOOK)
        self.assertIsInstance(plays, list)
        self.assertEqual(
            [play.get("hosts") for play in plays],
            ["pve", None, "herdr", None, "onramp_host", "localhost", "herdr"],
        )
        self.assertEqual(
            [role.get("role") for role in plays[0]["roles"]],
            ["lxc_ready", "herdr_lxc_bootstrap"],
        )
        self.assertEqual(
            plays[1]["ansible.builtin.import_playbook"],
            "direct-access-ready.yml",
        )
        self.assertEqual(
            plays[1]["vars"]["direct_access_target_group"],
            "herdr",
        )
        self.assertEqual(
            [role.get("role") for role in plays[2]["roles"]],
            ["herdr"],
        )
        self.assertEqual(
            plays[3]["ansible.builtin.import_playbook"],
            "vm-direct-access-ready.yml",
        )
        self.assertEqual(
            plays[3]["vars"]["direct_vm_access_target_group"],
            "onramp_host",
        )
        self.assertEqual(
            [role.get("role") for role in plays[4]["roles"]],
            ["herdr_onramp_access"],
        )
        self.assertIs(
            plays[4]["vars"]["onramp_host_enable_docker_compat_socket"],
            True,
        )
        self.assertEqual(
            [role.get("role") for role in plays[5]["roles"]],
            ["herdr_controller_trust"],
        )
        self.assertIn(
            "direct_access_host_keys", plays[5]["vars"]["herdr_controller_host_keys"]
        )
        self.assertEqual(
            plays[5]["vars"]["herdr_controller_known_hosts_file"],
            "/tmp/homelab-infra/ansible/herdr-known_hosts",
        )
        self.assertEqual(
            [role.get("role") for role in plays[6]["roles"]],
            ["herdr_remote_context"],
        )
        self.assertEqual(
            plays[6]["vars"]["ansible_ssh_common_args"],
            "-o UserKnownHostsFile=/tmp/homelab-infra/ansible/herdr-known_hosts "
            "-o GlobalKnownHostsFile=/dev/null "
            "-o StrictHostKeyChecking=yes "
            "-o ForwardAgent=no",
        )

    def test_pve_bootstrap_is_narrow_and_steady_state_roles_do_not_use_pve(self) -> None:
        bootstrap_defaults = (
            ROLES / "herdr_lxc_bootstrap" / "defaults" / "main.yml"
        ).read_text(encoding="utf-8")
        bootstrap_tasks = ROLES / "herdr_lxc_bootstrap" / "tasks" / "main.yml"
        bootstrap_source = bootstrap_tasks.read_text(encoding="utf-8")
        self.assertIn("herdr_lxc_bootstrap_command: pct", bootstrap_defaults)
        self.assertIn("herdr_lxc_bootstrap_command", bootstrap_source)
        self.assertIn("authorized_keys", bootstrap_source)
        self.assertIn("sudoers.d/herdr-operator", bootstrap_source)
        self.assertIn("sudo_tag='NOPASS'", bootstrap_source)
        self.assertIn('sudo_tag="${sudo_tag}WD"', bootstrap_source)
        self.assertIn("%s: ALL", bootstrap_source)

        for role in (
            "herdr",
            "herdr_onramp_access",
            "herdr_controller_trust",
            "herdr_remote_context",
        ):
            source = (ROLES / role / "tasks" / "main.yml").read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(^|\s)pct(\s|$)", role)

    def test_herdr_direct_role_enforces_platform_hardening_and_pins(self) -> None:
        path = ROLES / "herdr" / "tasks" / "main.yml"
        source = path.read_text(encoding="utf-8")
        package_task = task(
            path, "Install Herdr Debian and Docker CLI packages without a daemon"
        )
        packages = package_task["ansible.builtin.apt"]["name"]
        self.assertIn("{{ herdr_docker_cli_package }}", packages)
        self.assertIn(
            "herdr_docker_cli_package: docker-cli",
            (ROLES / "herdr" / "defaults" / "main.yml").read_text(
                encoding="utf-8"
            ),
        )
        self.assertNotIn("docker.io", packages)
        self.assertNotIn("docker-ce", packages)
        self.assertIn("ansible_distribution_major_version | int == 13", source)
        self.assertIn("ansible_architecture == 'x86_64'", source)
        self.assertIn("PasswordAuthentication no", source)
        self.assertIn("PermitRootLogin no", source)
        self.assertIn("ufw", source)
        self.assertIn(
            "https://github.com/herdrdev/herdr/releases/download/v0.8.2/herdr-linux-x86_64",
            source,
        )
        self.assertIn(
            "976150a14d490c94b243ea2e1a7eb2dfb67f12e36b182db90936f6728e6aecf4",
            source,
        )
        self.assertIn("sha256sum -c -", source)
        self.assertIn("${root}/releases/${version}-${sha256:0:12}", source)
        self.assertIn("mv -Tf", source)
        self.assertNotIn("OAUTH", source)
        self.assertNotIn("BITWARDEN_ACCESS_KEY", source)

    def test_pi_and_herdr_integration_use_the_operator_and_pnpm_only(self) -> None:
        path = ROLES / "herdr" / "tasks" / "main.yml"
        source = path.read_text(encoding="utf-8")
        package_task = task(
            path, "Install Herdr Debian and Docker CLI packages without a daemon"
        )
        packages = package_task["ansible.builtin.apt"]["name"]
        self.assertIn("xz-utils", packages)
        self.assertNotIn("nodejs", packages)
        self.assertNotIn("node-corepack", packages)
        self.assertNotIn("pnpm", packages)
        node_install = task(
            path, "Install the pinned official Node release with atomic activation"
        )
        node_source = node_install["ansible.builtin.command"]["argv"][2]
        self.assertIn("sha256sum -c -", node_source)
        self.assertIn("tar -xJf", node_source)
        self.assertIn('chmod 0755 "${staging}"', node_source)
        self.assertIn('chmod 0755 "${release}"', node_source)
        self.assertIn("for binary in node corepack", node_source)
        shim = task(
            path, "Enable the operator pnpm executable shim through official Corepack"
        )
        self.assertEqual(
            shim["ansible.builtin.command"]["argv"],
            [
                "corepack",
                "enable",
                "--install-directory",
                "{{ herdr_pnpm_home }}",
                "pnpm",
            ],
        )
        self.assertEqual(shim["become_user"], "{{ herdr_operator_user }}")
        activation = task(
            path, "Activate the pinned pnpm release through official Corepack"
        )
        self.assertEqual(
            activation["ansible.builtin.command"]["argv"],
            ["corepack", "install", "--global", "pnpm@{{ herdr_pnpm_version }}"],
        )
        self.assertEqual(
            activation["environment"]["COREPACK_HOME"],
            "{{ herdr_corepack_home }}",
        )
        verification = task(path, "Verify the pinned pnpm release as the operator")
        self.assertEqual(
            verification["ansible.builtin.command"]["argv"],
            ["pnpm", "--version"],
        )
        self.assertEqual(
            verification["become_user"],
            "{{ herdr_operator_user }}",
        )
        pi_install = task(
            path, "Install Pi 0.84.1 through pnpm as the Herdr operator"
        )
        argv = pi_install["ansible.builtin.command"]["argv"]
        self.assertEqual(argv[0], "pnpm")
        self.assertIn("--global", argv)
        self.assertIn("{{ herdr_pi_package }}@{{ herdr_pi_version }}", argv)
        self.assertEqual(pi_install["become_user"], "{{ herdr_operator_user }}")
        defaults = (ROLES / "herdr" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "herdr_pi_package: '@earendil-works/pi-coding-agent'",
            defaults,
        )
        self.assertIn("herdr_pi_version: '0.84.1'", defaults)
        self.assertIn("herdr_node_version: '22.22.0'", defaults)
        self.assertIn(
            "herdr_node_sha256: 9aa8e9d2298ab68c600bd6fb86a6c13bce11a4eca1ba9b39d79fa021755d7c37",
            defaults,
        )
        self.assertIn("herdr_pnpm_version: '10.28.2'", defaults)
        self.assertIn(
            "herdr_corepack_home: '{{ herdr_pi_home }}/.cache/node/corepack'",
            defaults,
        )
        self.assertEqual(
            pi_install["environment"]["COREPACK_HOME"],
            "{{ herdr_corepack_home }}",
        )
        self.assertNotRegex(source, r"(?<!p)npm\b")
        integration = task(
            path, "Install the official Herdr Pi integration as the operator"
        )
        self.assertEqual(
            integration["ansible.builtin.command"]["argv"],
            ["herdr", "integration", "install", "pi"],
        )
        self.assertEqual(
            integration["environment"]["PI_CODING_AGENT_DIR"],
            "{{ herdr_pi_agent_dir }}",
        )
        self.assertEqual(integration["become_user"], "{{ herdr_operator_user }}")
        state_stat = task(
            path, "Inspect the installed Herdr Pi integration state file"
        )
        self.assertEqual(
            state_stat["ansible.builtin.stat"]["path"],
            "{{ herdr_pi_agent_dir }}/extensions/herdr-agent-state.ts",
        )
        self.assertFalse(state_stat["ansible.builtin.stat"]["follow"])
        state_assert = task(
            path, "Enforce the Herdr Pi integration state file postcondition"
        )
        assertions = state_assert["ansible.builtin.assert"]["that"]
        self.assertIn(
            "herdr_pi_integration_state.stat.exists | default(false)", assertions
        )
        self.assertIn(
            "herdr_pi_integration_state.stat.isreg | default(false)", assertions
        )
        self.assertIn(
            "herdr_pi_integration_state.stat.pw_name | default('') == herdr_operator_user",
            assertions,
        )

    def test_herdr_ufw_reconciles_only_prior_managed_ssh_cidrs(self) -> None:
        path = ROLES / "herdr" / "tasks" / "main.yml"
        source = path.read_text(encoding="utf-8")
        defaults = (ROLES / "herdr" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "herdr_ufw_managed_cidrs_file: /etc/herdr/ufw-managed-ssh-cidrs",
            defaults,
        )
        self.assertIn(
            "{{ herdr_previous_managed_ssh_cidrs | difference(herdr_allowed_ssh_cidrs) | sort }}",
            source,
        )
        self.assertIn(
            "{{ herdr_allowed_ssh_cidrs | unique | list }}",
            source,
        )
        update = task(
            path, "Atomically update the root-owned Herdr-managed SSH CIDR set"
        )
        update_command = update["ansible.builtin.command"]["argv"]
        self.assertEqual(update_command[:2], ["bash", "-lc"])
        self.assertIn("mktemp", update_command[2])
        self.assertIn("mv -f", update_command[2])
        self.assertIn("chown root:root", update_command[2])
        self.assertNotIn("ufw flush", source)

    def test_dedicated_key_is_public_only_on_onramp_and_relay_is_restricted(self) -> None:
        direct = (ROLES / "herdr" / "tasks" / "main.yml").read_text(encoding="utf-8")
        onramp_path = ROLES / "herdr_onramp_access" / "tasks" / "main.yml"
        onramp = onramp_path.read_text(encoding="utf-8")
        self.assertIn("ssh-keygen", direct)
        self.assertIn("ed25519", direct)
        self.assertIn("herdr_remote_access_public_key", direct)
        self.assertIn(
            "hostvars[groups['herdr'][0]].herdr_remote_access_public_key",
            onramp,
        )
        self.assertIn("restrict,from=", onramp)
        self.assertIn('command=\"{{ herdr_onramp_relay_path }}\"', onramp)
        self.assertIn("/usr/local/libexec/podman-docker-stdio", onramp)
        self.assertIn("AuthorizedKeysFile .ssh/authorized_keys", onramp)
        self.assertIn("herdr_onramp_authorized_keys_file", onramp)
        self.assertNotIn(
            "/home/{{ onramp_host_deploy_user }}/.ssh/authorized_keys", onramp
        )
        self.assertNotIn("id_ed25519_herdr_onramp", onramp)

    def test_verified_vm_keys_are_the_only_persistent_herdr_trust_source(self) -> None:
        onramp = (ROLES / "herdr_onramp_access" / "tasks" / "main.yml").read_text(
            encoding="utf-8"
        )
        remote = (ROLES / "herdr_remote_context" / "tasks" / "main.yml").read_text(
            encoding="utf-8"
        )
        known_hosts = (
            ROLES / "herdr_remote_context" / "templates" / "known_hosts.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("direct_vm_access_host_keys", onramp)
        self.assertIn("herdr_verified_onramp_host_keys", onramp)
        self.assertIn("direct_vm_access_host_keys", remote)
        self.assertIn("herdr_verified_onramp_host_keys", known_hosts)
        self.assertNotIn("ssh-keyscan", onramp + remote + known_hosts)
        self.assertIn("herdr_remote_ssh_alias", known_hosts)

    def test_ssh_config_and_docker_context_are_exact_and_non_ambient(self) -> None:
        config = (
            ROLES / "herdr_remote_context" / "templates" / "ssh_config.j2"
        ).read_text(encoding="utf-8")
        remote = (ROLES / "herdr_remote_context" / "tasks" / "main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("IdentityFile {{ herdr_remote_identity_file }}", config)
        self.assertIn("IdentitiesOnly yes", config)
        self.assertIn("StrictHostKeyChecking yes", config)
        self.assertIn("UserKnownHostsFile {{ herdr_remote_known_hosts_file }}", config)
        self.assertIn("GlobalKnownHostsFile /dev/null", config)
        self.assertIn("ForwardAgent no", config)
        self.assertIn("IdentityAgent none", config)
        self.assertIn("grep -F 'forwardagent no'", remote)
        self.assertIn("ssh://", remote)
        self.assertIn("herdr_remote_ssh_alias", remote)
        self.assertIn("docker system dial-stdio", remote)
        self.assertIn("docker", remote)
        self.assertIn("--context", remote)
        self.assertNotIn("docker.io", remote)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ONRAMP_HOST_DEFAULTS = (
    REPO / "infra" / "ansible" / "roles" / "onramp_host" / "defaults" / "main.yml"
)
ONRAMP_HOST_ARGUMENT_SPECS = (
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "onramp_host"
    / "meta"
    / "argument_specs.yml"
)
ONRAMP_HOST_TASKS = (
    REPO / "infra" / "ansible" / "roles" / "onramp_host" / "tasks" / "main.yml"
)
PODMAN_DOCKER_STDIO_RELAY = (
    REPO
    / "infra"
    / "ansible"
    / "roles"
    / "onramp_host"
    / "templates"
    / "podman-docker-stdio.j2"
)


class HerdrOnrampContractTests(unittest.TestCase):
    def test_onramp_host_exposes_relay_path_and_installs_socat(self) -> None:
        defaults = ONRAMP_HOST_DEFAULTS.read_text(encoding="utf-8")
        argument_specs = ONRAMP_HOST_ARGUMENT_SPECS.read_text(encoding="utf-8")
        tasks = ONRAMP_HOST_TASKS.read_text(encoding="utf-8")

        socat_task = tasks.split(
            "- name: Ensure socat is installed for the Podman Docker stdio relay", 1
        )[1].split("- name: Ensure onramp-host deploy user exists", 1)[0]
        self.assertIn("name: socat", socat_task)
        self.assertIn("state: present", socat_task)
        self.assertIn(
            "onramp_host_podman_docker_stdio_relay_path: "
            "/usr/local/libexec/podman-docker-stdio",
            defaults,
        )
        self.assertIn("onramp_host_podman_docker_stdio_relay_path:", argument_specs)
        self.assertIn("type: str", argument_specs)

    def test_relay_accepts_only_docker_system_dial_stdio(self) -> None:
        relay = PODMAN_DOCKER_STDIO_RELAY.read_text(encoding="utf-8")

        self.assertIn(
            'if [ "${SSH_ORIGINAL_COMMAND-}" != "docker system dial-stdio" ]; then',
            relay,
        )
        self.assertIn(
            'exec /usr/bin/socat STDIO '
            '"UNIX-CONNECT:/run/user/{{ onramp_host_deploy_user_uid.stdout | trim }}'
            '/podman/podman.sock"',
            relay,
        )
        self.assertNotIn("TCP-LISTEN", relay)
        self.assertNotIn("dockerd", relay)

    def test_relay_is_root_owned_and_has_no_workload_restart_handler(self) -> None:
        tasks = ONRAMP_HOST_TASKS.read_text(encoding="utf-8")
        relay_task = tasks.split(
            "- name: Install root-owned Podman Docker stdio SSH relay", 1
        )[1].split("- name: Ensure rootless Podman socket unit", 1)[0]

        self.assertIn(
            'dest: "{{ onramp_host_podman_docker_stdio_relay_path }}"',
            relay_task,
        )
        self.assertIn("owner: root", relay_task)
        self.assertIn("group: root", relay_task)
        self.assertIn('mode: "0755"', relay_task)
        self.assertNotIn("notify:", relay_task)

    def test_rootless_podman_socket_remains_enabled_and_is_verified_as_unix_socket(
        self,
    ) -> None:
        tasks = ONRAMP_HOST_TASKS.read_text(encoding="utf-8")
        socket_task = tasks.split(
            "- name: Ensure rootless Podman socket unit is enabled for deploy user", 1
        )[1].split("- name: Verify rootless Podman socket is a Unix socket", 1)[0]
        verification = tasks.split(
            "- name: Verify rootless Podman socket is a Unix socket", 1
        )[1].split("- name: Verify onramp-host deployment directory ownership", 1)[0]

        self.assertIn("name: podman.socket", socket_task)
        self.assertIn("enabled: true", socket_task)
        self.assertIn("state: started", socket_task)
        self.assertIn(
            "/run/user/{{ onramp_host_deploy_user_uid.stdout | trim }}"
            "/podman/podman.sock",
            verification,
        )
        self.assertIn("stat.issock", verification)
        self.assertNotIn("TCP", tasks)
        self.assertNotIn("dockerd", tasks)


if __name__ == "__main__":
    unittest.main()

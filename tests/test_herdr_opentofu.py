from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
OPENTOFU = REPO / "infra" / "opentofu"


def variable_block(source: str, name: str) -> str:
    match = re.search(
        rf'(?ms)^variable "{re.escape(name)}" \{{.*?(?=^variable |\Z)',
        source,
    )
    if match is None:
        raise AssertionError(f"variable {name!r} not found")
    return match.group(0)


def effective_ipv4_address(configured_address: str, reserved_address: str) -> str:
    if configured_address == "dhcp":
        return reserved_address
    return configured_address.split("/", 1)[0]


class HerdrOpenTofuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resource = (OPENTOFU / "herdr.tf").read_text(encoding="utf-8")
        cls.module = (OPENTOFU / "modules" / "debian-lxc" / "main.tf").read_text(
            encoding="utf-8"
        )
        cls.services = (OPENTOFU / "services.tf").read_text(encoding="utf-8")
        cls.checks = (OPENTOFU / "herdr-checks.tf").read_text(encoding="utf-8")
        cls.outputs = (OPENTOFU / "outputs.tf").read_text(encoding="utf-8")
        cls.uniqueness = (OPENTOFU / "onramp-host-checks.tf").read_text(
            encoding="utf-8"
        )
        cls.variables = (OPENTOFU / "variables.tf").read_text(encoding="utf-8")

    def test_module_is_unprivileged_and_disables_nesting(self) -> None:
        self.assertIn('module "herdr"', self.resource)
        self.assertIn('source = "./modules/debian-lxc"', self.resource)
        self.assertIn("count  = local.herdr_enabled ? 1 : 0", self.resource)
        self.assertIn("features = {\n    nesting = false\n  }", self.resource)
        self.assertNotIn("privileged", self.resource)
        self.assertNotIn("nesting = true", self.resource)
        self.assertIn("unprivileged  = true", self.module)

    def test_enablement_uses_herdr_key_and_shared_debian_template(self) -> None:
        self.assertRegex(
            self.services,
            r'herdr_enabled\s*=\s*contains\(local\.enabled_services, "herdr"\)',
        )
        self.assertIn("local.herdr_enabled", self.services)
        self.assertIn(
            "proxmox_download_file.debian_13_lxc_template[0].id", self.resource
        )

    def test_uniqueness_checks_include_herdr(self) -> None:
        self.assertIn("tostring(var.herdr_container_vmid)", self.uniqueness)
        normalized = re.sub(r"\s+", "", self.uniqueness)
        self.assertIn(
            'var.herdr_container_ipv4_address=="dhcp"?var.herdr_lan_ip:'
            'split("/",var.herdr_container_ipv4_address)[0]',
            normalized,
        )

    def test_dhcp_herdr_reserved_address_collision_is_detected(self) -> None:
        addresses = [
            effective_ipv4_address("dhcp", "192.0.2.73"),
            effective_ipv4_address("192.0.2.73/24", "unused"),
        ]
        self.assertNotEqual(len(addresses), len(set(addresses)))

    def test_operator_and_ssh_policy_defaults_are_public_safe(self) -> None:
        operator = variable_block(self.variables, "herdr_operator_user")
        self.assertIn('default     = "herdr"', operator)
        self.assertIn("var.herdr_operator_user != \"root\"", operator)

        password_auth = variable_block(
            self.variables, "herdr_password_authentication"
        )
        self.assertIn("default     = false", password_auth)
        self.assertIn("var.herdr_password_authentication == false", password_auth)

        root_login = variable_block(self.variables, "herdr_permit_root_login")
        self.assertIn("default     = false", root_login)
        self.assertIn("var.herdr_permit_root_login == false", root_login)

        allowed_cidrs = variable_block(self.variables, "herdr_allowed_ssh_cidrs")
        self.assertIn('default     = ["192.0.2.0/24"]', allowed_cidrs)
        self.assertIn("length(var.herdr_allowed_ssh_cidrs) > 0", allowed_cidrs)
        self.assertIn("alltrue", allowed_cidrs)

    def test_hardening_check_repeats_ssh_policy(self) -> None:
        self.assertIn('check "herdr_hardening_policy"', self.checks)
        for expression in (
            "!var.herdr_password_authentication",
            "!var.herdr_permit_root_login",
            "length(var.herdr_allowed_ssh_cidrs) > 0",
            "alltrue",
        ):
            self.assertIn(expression, self.checks)

    def test_outputs_expose_vmid_lan_ip_and_operator_target(self) -> None:
        self.assertIn('output "herdr_container_vmid"', self.outputs)
        self.assertIn(
            "value       = local.herdr_enabled ? module.herdr[0].vm_id : null",
            self.outputs,
        )
        self.assertIn('output "herdr_lan_ip"', self.outputs)
        self.assertIn(
            "value       = local.herdr_enabled ? var.herdr_lan_ip : null",
            self.outputs,
        )
        self.assertIn('output "herdr_ssh_target"', self.outputs)
        self.assertIn(
            'value       = local.herdr_enabled ? '
            '"${var.herdr_operator_user}@${var.herdr_server_name}" : null',
            self.outputs,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LXC_PIN_URL = "http://download.proxmox.com/images/system/debian-13-standard_13.1-2_amd64.tar.zst"
LXC_PIN_FILE_NAME = "debian-13-standard_13.1-2_amd64.tar.zst"
LXC_PIN_CHECKSUM = "5aec4ab2ac5c16c7c8ecb87bfeeb10213abe96db6b85e2463585cea492fc861d7c390b3f9c95629bf690b95e9dfe1037207fc69c0912429605f208d5cb2621f8"
ONRAMP_PIN_URL = "https://cloud.debian.org/images/cloud/trixie/20260623-2518/debian-13-genericcloud-amd64-20260623-2518.qcow2"
ONRAMP_PIN_FILE_NAME = "debian-13-genericcloud-amd64-20260623-2518.qcow2"
ONRAMP_PIN_CHECKSUM = "df2bd468b08566c0409a7982d6489d73499ad22f9a28646b538c2f21d08f15040a5e4737952ca209e9ad4488cd00793191791be9f135dee93082c86fcca3300c"


class DebianBaselineTests(unittest.TestCase):
    def test_lxc_template_uses_the_verified_debian_13_download_with_checksum(self) -> None:
        text = (REPO / "infra" / "opentofu" / "main.tf").read_text(encoding="utf-8")

        self.assertIn('resource "proxmox_download_file" "debian_13_lxc_template"', text)
        self.assertIn("checksum            = var.debian_13_lxc_template_checksum", text)
        self.assertIn("checksum_algorithm  = var.debian_13_lxc_template_checksum_algorithm", text)
        moves = (REPO / "infra" / "opentofu" / "services.tf").read_text(encoding="utf-8")
        self.assertIn("from = proxmox_download_file.debian_12_lxc_template[0]", moves)
        self.assertIn("to   = proxmox_download_file.debian_13_lxc_template[0]", moves)

    def test_every_lxc_service_uses_the_debian_13_template(self) -> None:
        expected_modules = {
            "main.tf": "technitium_dns",
            "forgejo.tf": "forgejo",
            "forgejo-runner.tf": "forgejo_runner",
            "infisical.tf": "infisical",
            "hermes.tf": "hermes",
            "tailscale.tf": "tailscale_client",
        }
        root = REPO / "infra" / "opentofu"
        for name, module_name in expected_modules.items():
            text = (root / name).read_text(encoding="utf-8")
            self.assertIn(f'module "{module_name}"', text, name)
            self.assertIn("proxmox_download_file.debian_13_lxc_template[0].id", text, name)
            self.assertNotIn("proxmox_download_file.debian_12_lxc_template", text, name)
        for path in root.glob("*.tf"):
            self.assertNotIn('resource "proxmox_virtual_environment_container"', path.read_text(encoding="utf-8"), path.name)
        module_text = (root / "modules" / "debian-lxc" / "main.tf").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'resource\s+"proxmox_virtual_environment_container"', module_text)), 1)
        self.assertIn("template_file_id = var.template_file_id", module_text)
        self.assertNotIn("template_file_id,", module_text.split("ignore_changes", 1)[1])

    def test_onramp_host_keeps_its_separate_verified_debian_13_image(self) -> None:
        text = (REPO / "infra" / "opentofu" / "onramp-host.tf").read_text(encoding="utf-8")

        self.assertIn('resource "proxmox_download_file" "debian_13_onramp_host_image"', text)
        self.assertIn("checksum            = var.onramp_host_image_checksum", text)
        self.assertIn("checksum_algorithm  = var.onramp_host_image_checksum_algorithm", text)
        self.assertIn("var.onramp_host_image_url", text)
        self.assertNotIn("debian_12_lxc_template", text)

    def test_variables_and_scaffold_require_exact_pins(self) -> None:
        variables = (REPO / "infra" / "opentofu" / "variables.tf").read_text(encoding="utf-8")
        scaffold = (REPO / "scaffold" / "terraform.tfvars").read_text(encoding="utf-8")

        for text in (variables, scaffold):
            self.assertIn(LXC_PIN_URL, text)
            self.assertIn(LXC_PIN_FILE_NAME, text)
            self.assertIn(LXC_PIN_CHECKSUM, text)
            self.assertIn(ONRAMP_PIN_URL, text)
            self.assertIn(ONRAMP_PIN_FILE_NAME, text)
            self.assertIn(ONRAMP_PIN_CHECKSUM, text)
        self.assertIn('debian_13_lxc_template_checksum_algorithm = "sha512"', scaffold)
        self.assertNotIn("debian_template_", scaffold)
        self.assertIn('onramp_host_image_checksum_algorithm = "sha512"', scaffold)


if __name__ == "__main__":
    unittest.main()

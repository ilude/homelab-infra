from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate-values.py"
spec = importlib.util.spec_from_file_location("migrate_values", SCRIPT)
assert spec and spec.loader
migrate_values = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migrate_values
spec.loader.exec_module(migrate_values)


class MigrateValuesTests(unittest.TestCase):
    def test_removes_only_recognized_legacy_pve_inventory_block(self) -> None:
        inventory = (
            "---\nall:\n  hosts:\n    pve:\n"
            "      ansible_host: proxmox.example.internal\n"
            "      ansible_user: root\n"
            "    monitoring:\n      ansible_host: monitor.example.internal\n"
            "  vars:\n    custom: retained\n"
        )

        updated, changes = migrate_values.remove_legacy_pve_inventory_block(inventory)

        self.assertEqual(changes, ["removed legacy static pve inventory host"])
        self.assertNotIn("    pve:", updated)
        self.assertIn("    monitoring:", updated)
        self.assertIn("    custom: retained", updated)
        self.assertEqual(migrate_values.remove_legacy_pve_inventory_block(updated), (updated, []))

    def test_preserves_unrecognized_pve_inventory_block(self) -> None:
        inventory = (
            "all:\n  hosts:\n    pve:\n"
            "      ansible_host: proxmox.example.internal\n"
            "      ansible_user: deploy\n"
            "      custom: retained\n"
            "  vars:\n    custom: retained\n"
        )

        self.assertEqual(migrate_values.remove_legacy_pve_inventory_block(inventory), (inventory, []))

    def test_infisical_encryption_key_generator_matches_current_format(self) -> None:
        value = migrate_values.GENERATED_SECRET_KEYS["INFISICAL_ENCRYPTION_KEY"]()
        self.assertRegex(value, r"^[0-9a-f]{32}$")

    def test_normalizes_historical_infisical_encryption_key(self) -> None:
        lines = ["INFISICAL_ENCRYPTION_KEY=" + "a" * 64 + "\n"]
        entries = migrate_values.parse_env_lines(lines, Path("values/.env"))

        changes = migrate_values.migrate_infisical_secret_formats(lines, entries)

        self.assertEqual(changes, ["normalized INFISICAL_ENCRYPTION_KEY to Infisical 16-byte hex format"])
        self.assertEqual(migrate_values.envfile_parse_scalar(entries["INFISICAL_ENCRYPTION_KEY"].value), "a" * 32)

    def make_values(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        values = root / "values"
        inventory = values / "ansible" / "inventory"
        inventory.mkdir(parents=True)
        (inventory / "local.yml").write_text(
            "all:\n"
            "  vars:\n"
            "    forgejo_domain: git.example.internal\n"
            "    forgejo_version: \"12.0.4\"\n"
            "    caddy_server_name: dns.example.internal\n",
            encoding="utf-8",
        )
        return temp, values

    def test_renames_legacy_debian_lxc_template_inputs(self) -> None:
        lines = [
            'debian_template_url = "https://download.proxmox.com/old.tar.zst"',
            'debian_template_file_name = "old.tar.zst"',
            'debian_template_checksum_algorithm = "sha512"',
            'debian_template_checksum = "' + "a" * 128 + '"',
        ]

        for old_key, new_key in migrate_values.DEBIAN_LXC_TFVARS_RENAMES.items():
            self.assertTrue(migrate_values.rename_tfvars_key(lines, old_key, new_key))

        text = "\n".join(lines)
        for old_key, new_key in migrate_values.DEBIAN_LXC_TFVARS_RENAMES.items():
            self.assertNotRegex(text, rf"(?m)^\s*{old_key}\s*=")
            self.assertRegex(text, rf"(?m)^\s*{new_key}\s*=")

    def test_migrates_only_managed_debian_13_lxc_template_url_to_http(self) -> None:
        lines = [
            f'debian_13_lxc_template_url = "{migrate_values.DEBIAN_13_LXC_TEMPLATE_HTTPS_URL}"',
            'debian_13_lxc_template_file_name = "debian-13-standard_13.1-2_amd64.tar.zst"',
            'debian_13_lxc_template_checksum_algorithm = "sha512"',
            'debian_13_lxc_template_checksum = "' + "a" * 128 + '"',
        ]

        self.assertEqual(
            migrate_values.migrate_debian_13_lxc_template_url(lines),
            ["migrated managed Debian 13 LXC template URL to HTTP"],
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "debian_13_lxc_template_url"),
            migrate_values.DEBIAN_13_LXC_TEMPLATE_HTTP_URL,
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "debian_13_lxc_template_file_name"),
            "debian-13-standard_13.1-2_amd64.tar.zst",
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "debian_13_lxc_template_checksum_algorithm"),
            "sha512",
        )
        self.assertEqual(migrate_values.migrate_debian_13_lxc_template_url(lines), [])

    def test_preserves_custom_debian_13_lxc_template_url(self) -> None:
        lines = ['debian_13_lxc_template_url = "https://images.example.invalid/custom.tar.zst"']
        original = list(lines)

        self.assertEqual(migrate_values.migrate_debian_13_lxc_template_url(lines), [])
        self.assertEqual(lines, original)

    def test_migrates_technitium_values_from_old_locations(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TF_VAR_technitium_api_token='REPLACE_SECRET'\n"
                "export TF_VAR_container_root_password='REPLACE_PASSWORD'\n"
                "export SERVER_NAME='dns.example.internal'\n"
                "export FORGEJO_SERVER_NAME='git.example.internal'\n"
                "export FORGEJO_UPSTREAM='192.0.2.10:3000'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text(
                'container_root_password = "REPLACE_PASSWORD"\n'
                'container_ssh_public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA_REPLACE_ME user@host"]\n'
                'container_vmid = 106\n'
                'container_hostname = "technitium-dns"\n'
                'container_ipv4_address = "192.0.2.53/24"\n'
                'container_vlan_id = 42\n'
                'container_dns_servers = ["192.0.2.1"]\n'
                'technitium_api_url = "http://192.0.2.53:5380/api"\n'
                'dns_records_file = "../../values/dns-records.local.json"\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            env_text = (values / ".env").read_text(encoding="utf-8")
            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn("TECHNITIUM_API_TOKEN=REPLACE_SECRET", env_text)
            self.assertIn("TF_VAR_lxc_root_password=REPLACE_PASSWORD", env_text)
            self.assertIn("TECHNITIUM_API_URL=http://192.0.2.53:5380/api", env_text)
            self.assertIn("DNS_RECORDS_FILE=values/dns-records.local.json", env_text)
            self.assertNotIn("TF_VAR_technitium_api_token", env_text)
            self.assertNotIn("TF_VAR_container_root_password", env_text)
            self.assertNotIn("SERVER_NAME", env_text)
            self.assertNotIn("FORGEJO_SERVER_NAME", env_text)
            self.assertNotIn("FORGEJO_UPSTREAM", env_text)
            self.assertIn('lxc_root_password = "REPLACE_PASSWORD"', tfvars_text)
            self.assertIn('lxc_ssh_public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA_REPLACE_ME user@host"]', tfvars_text)
            self.assertIn("technitium_container_vmid = 106", tfvars_text)
            self.assertIn('technitium_container_hostname = "technitium-dns"', tfvars_text)
            self.assertIn('technitium_container_ipv4_address = "192.0.2.53/24"', tfvars_text)
            self.assertIn("technitium_container_vlan_id = 42", tfvars_text)
            self.assertIn('technitium_container_dns_servers = ["192.0.2.1"]', tfvars_text)
            self.assertNotIn("container_root_password", tfvars_text)
            self.assertNotIn("container_ssh_public_keys", tfvars_text)
            self.assertNotRegex(tfvars_text, r"(?m)^container_vmid\\s*=")
            self.assertNotRegex(tfvars_text, r"(?m)^container_hostname\\s*=")
            self.assertNotIn("technitium_api_url", tfvars_text)
            self.assertNotIn("dns_records_file", tfvars_text)
            self.assertTrue(changes)

    def test_conflicting_token_names_fail(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TF_VAR_technitium_api_token='REPLACE_OLD'\n"
                "export TECHNITIUM_API_TOKEN='REPLACE_NEW'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            with self.assertRaises(migrate_values.MigrationError):
                migrate_values.migrate(values)

    def test_infisical_dns_target_uses_enabled_deployment_mode(self) -> None:
        self.assertEqual(
            migrate_values.infisical_dns_target({"infisical"}, "192.0.2.70", "192.0.2.72"),
            "192.0.2.70",
        )
        self.assertEqual(
            migrate_values.infisical_dns_target({"infisical_onramp"}, "192.0.2.70", "192.0.2.72"),
            "192.0.2.72",
        )
        with self.assertRaisesRegex(migrate_values.MigrationError, "mutually exclusive"):
            migrate_values.infisical_dns_target({"infisical", "infisical_onramp"}, "192.0.2.70", "192.0.2.72")

    def test_infisical_dns_migration_replaces_legacy_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dns_path = Path(temp) / "dns-records.local.json"
            dns_path.write_text('{"a_records":{"infisical.lab.example":"192.0.2.70"}}\n', encoding="utf-8")

            changes = migrate_values.ensure_dns_records(
                dns_path,
                "lab.example",
                migrate_values.infisical_dns_target({"infisical_onramp"}, "192.0.2.70", "192.0.2.72"),
                "",
            )

            self.assertEqual(changes, ["added optional service DNS record"])
            self.assertIn('"infisical.lab.example": "192.0.2.72"', dns_path.read_text(encoding="utf-8"))

    def test_infisical_dns_migration_removes_disabled_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dns_path = Path(temp) / "dns-records.local.json"
            dns_path.write_text('{"a_records":{"infisical.lab.example":"192.0.2.70"}}\n', encoding="utf-8")

            changes = migrate_values.ensure_dns_records(
                dns_path,
                "lab.example",
                "",
                "",
                remove_infisical_when_absent=True,
            )

            self.assertEqual(changes, ["removed optional service DNS record"])
            self.assertNotIn("infisical.lab.example", dns_path.read_text(encoding="utf-8"))

    def test_replaces_only_mutable_oci_defaults_and_preserves_custom_pins(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            inventory = values / "ansible" / "inventory" / "local.yml"
            inventory.write_text("---\nall:\n  vars:\n    infisical_version: latest\n", encoding="utf-8")
            (values / "terraform.tfvars").write_text('searxng_container_image = "docker.io/searxng/searxng:latest"\n', encoding="utf-8")

            migrate_values.migrate(values)

            inventory_text = inventory.read_text(encoding="utf-8")
            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertNotIn("infisical_version: latest", inventory_text)
            self.assertIn("infisical_container_image: docker.io/infisical/infisical:v0.161.11@sha256:", inventory_text)
            self.assertIn("searxng_container_image = \"docker.io/searxng/searxng:2026.7.2-67973783d@sha256:", tfvars_text)
            self.assertEqual(migrate_values.migrate(values), [])

    def test_preserves_partial_custom_hermes_pin_group(self) -> None:
        inventory = (
            "---\nall:\n  vars:\n"
            '    hermes_discovery_version: "0.17.0"\n'
        )

        updated, changes = migrate_values.ensure_pin_inventory_vars(
            inventory,
            migrate_values.HERMES_DISCOVERY_PIN_DEFAULTS,
            "Hermes managed release",
        )

        self.assertEqual(updated, inventory)
        self.assertEqual(changes, [])
        self.assertNotIn("hermes_discovery_wheel_sha256", updated)

    def test_preserves_partial_custom_technitium_pin_group(self) -> None:
        inventory = (
            "---\nall:\n  vars:\n"
            '    technitium_discovery_version: "15.1.0"\n'
        )

        updated, changes = migrate_values.ensure_pin_inventory_vars(
            inventory,
            migrate_values.TECHNITIUM_DISCOVERY_PIN_DEFAULTS,
            "Technitium managed release",
        )

        self.assertEqual(updated, inventory)
        self.assertEqual(changes, [])
        self.assertNotIn("technitium_portable_sha256", updated)

    def test_preserves_partial_custom_pin_groups_without_filling_defaults(self) -> None:
        inventory = (
            "---\nall:\n  vars:\n"
            "    infisical_container_image: docker.io/example/custom:v1@sha256:" + "a" * 64 + "\n"
        )

        updated, changes = migrate_values.ensure_pin_inventory_vars(
            inventory, migrate_values.OCI_PIN_DEFAULTS, "OCI"
        )

        self.assertEqual(updated, inventory)
        self.assertEqual(changes, [])
        self.assertNotIn("infisical_postgres_image", updated)

    def test_moves_custom_searxng_inventory_pin_to_tfvars(self) -> None:
        custom = "docker.io/example/searxng:v1@sha256:" + "b" * 64
        inventory = f"---\nall:\n  vars:\n    searxng_container_image: {custom}\n"
        tfvars = [
            'searxng_container_image = "docker.io/searxng/searxng:2026.7.2-67973783d@sha256:33aa33278be6c0be379b95f7c91cd455c18141295291c2e5a396454761df7bbb"'
        ]

        updated, changes = migrate_values.migrate_searxng_inventory_image(
            inventory, tfvars
        )

        self.assertNotIn("searxng_container_image", updated)
        self.assertEqual(migrate_values.tfvars_scalar_value(tfvars, "searxng_container_image"), custom)
        self.assertEqual(changes, ["moved searxng_container_image ownership to terraform.tfvars"])

    def test_adds_missing_vlan_ids_for_existing_service_values(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'technitium_container_vmid = 106\n'
                'forgejo_container_bridge = "vmbr0"\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn("technitium_container_vlan_id = null", tfvars_text)
            self.assertIn("forgejo_container_vlan_id = null", tfvars_text)
            self.assertNotIn("hermes_container_vlan_id", tfvars_text)
            self.assertIn("added technitium_container_vlan_id", changes)
            self.assertIn("added forgejo_container_vlan_id", changes)

    def test_sets_dns_backed_services_static_from_lan_ips(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'technitium_container_ipv4_address = "192.0.2.22/24"\n'
                'technitium_container_ipv4_gateway = "192.0.2.1"\n'
                'forgejo_container_ipv4_address = "dhcp"\n'
                'forgejo_container_ipv4_gateway = null\n'
                'forgejo_lan_ip = "192.0.2.23"\n'
                'infisical_container_ipv4_address = "dhcp"\n'
                'infisical_container_ipv4_gateway = null\n'
                'infisical_lan_ip = "192.0.2.26"\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn('forgejo_container_ipv4_address = "192.0.2.23/24"', tfvars_text)
            self.assertIn('forgejo_container_ipv4_gateway = "192.0.2.1"', tfvars_text)
            self.assertIn('infisical_container_ipv4_address = "192.0.2.26/24"', tfvars_text)
            self.assertIn('infisical_container_ipv4_gateway = "192.0.2.1"', tfvars_text)
            self.assertIn("set forgejo static IPv4 address from forgejo_lan_ip", changes)

    def test_hashes_legacy_hermes_dashboard_plaintext_password(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export HERMES_DASHBOARD_BASIC_AUTH_PASS" "WORD='REPLACE_DASHBOARD_PASSWORD'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            changes = migrate_values.migrate(values)

            env_text = (values / ".env").read_text(encoding="utf-8")
            self.assertIn("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH='scrypt$", env_text)
            self.assertNotIn("HERMES_DASHBOARD_BASIC_AUTH_PASS" "WORD=", env_text)
            self.assertIn("hashed HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "\n".join(changes))

    def test_rewrites_dns_named_technitium_api_url_to_direct_lxc_endpoint(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TECHNITIUM_API_URL='https://dns.lab.example/api'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text(
                'technitium_container_ipv4_address = "192.0.2.53/24"\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            env_text = (values / ".env").read_text(encoding="utf-8")
            self.assertIn("TECHNITIUM_API_URL=http://192.0.2.53:5380/api", env_text)
            self.assertIn("set TECHNITIUM_API_URL to direct Technitium LXC API endpoint", changes)

    def test_optional_service_migration_has_relative_and_absolute_path_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            relative_values = root / "relative" / "values"
            absolute_values = root / "absolute" / "values"
            for values in (relative_values, absolute_values):
                inventory = values / "ansible" / "inventory"
                inventory.mkdir(parents=True)
                (inventory / "local.yml").write_text("---\nall:\n  vars:\n", encoding="utf-8")
                (values / ".env").write_text("", encoding="utf-8")
                (values / "terraform.tfvars").write_text(
                    'technitium_container_ipv4_address = "192.0.2.53/24"\n'
                    'technitium_container_ipv4_gateway = "192.0.2.1"\n'
                    'technitium_container_search_domain = "example.internal"\n',
                    encoding="utf-8",
                )
                (values.parent / "settings.local.json").write_text(
                    '{"services":["onramp_host"]}\n', encoding="utf-8"
                )

            original_cwd = Path.cwd()
            try:
                with patch.object(migrate_values, "GENERATED_SECRET_KEYS", {}):
                    os.chdir(relative_values.parent)
                    relative_changes = migrate_values.migrate(Path("values"))
                    os.chdir(root)
                    absolute_changes = migrate_values.migrate(absolute_values)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(relative_changes, absolute_changes)
            for relative_path in (".env", "terraform.tfvars", "ansible/inventory/local.yml"):
                self.assertEqual(
                    (relative_values / relative_path).read_text(encoding="utf-8"),
                    (absolute_values / relative_path).read_text(encoding="utf-8"),
                )

    def test_adds_onramp_host_values_only_when_onramp_host_enabled(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'technitium_container_ipv4_address = "192.0.2.53/24"\n'
                'technitium_container_ipv4_gateway = "192.0.2.1"\n'
                'technitium_container_search_domain = "example.internal"\n'
                'technitium_container_bridge = "vmbr0"\n'
                'technitium_container_dns_servers = ["192.0.2.1"]\n',
                encoding="utf-8",
            )
            settings = values.parent / "settings.local.json"
            original = settings.read_text(encoding="utf-8") if settings.exists() else None
            settings.write_text('{"services":["onramp_host"]}\n', encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(values.parent)
                changes = migrate_values.migrate(Path("values"))
                second_changes = migrate_values.migrate(Path("values"))
            finally:
                os.chdir(original_cwd)
                if original is None:
                    settings.unlink(missing_ok=True)
                else:
                    settings.write_text(original, encoding="utf-8")

            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn("onramp_host_vmid = 112", tfvars_text)
            self.assertIn('onramp_host_hostname = "onramp-host"', tfvars_text)
            self.assertIn(f'onramp_host_image_url = "{migrate_values.ONRAMP_HOST_IMAGE_URL}"', tfvars_text)
            self.assertIn(f'onramp_host_image_file_name = "{migrate_values.ONRAMP_HOST_IMAGE_FILE_NAME}"', tfvars_text)
            self.assertIn(f'onramp_host_image_checksum_algorithm = "{migrate_values.ONRAMP_HOST_IMAGE_CHECKSUM_ALGORITHM}"', tfvars_text)
            self.assertIn(f'onramp_host_image_checksum = "{migrate_values.ONRAMP_HOST_IMAGE_CHECKSUM}"', tfvars_text)
            self.assertIn('onramp_host_ipv4_address = "192.0.2.72/24"', tfvars_text)
            self.assertIn('onramp_host_deploy_user = "onramp"', tfvars_text)
            self.assertNotIn("onramp_host_template_vmid", tfvars_text)
            self.assertIn("added onramp_host_vmid", changes)
            self.assertEqual(second_changes, [])

    def test_migrates_only_exact_mutable_onramp_image_pair(self) -> None:
        lines = [
            f'onramp_host_image_url = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_URL}"',
            f'onramp_host_image_file_name = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_FILE_NAME}"',
        ]

        self.assertEqual(
            migrate_values.migrate_onramp_host_image_pin(lines),
            ["migrated mutable onramp-host cloud image to reviewed pin"],
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "onramp_host_image_url"),
            migrate_values.ONRAMP_HOST_IMAGE_URL,
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "onramp_host_image_file_name"),
            migrate_values.ONRAMP_HOST_IMAGE_FILE_NAME,
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "onramp_host_image_checksum_algorithm"),
            migrate_values.ONRAMP_HOST_IMAGE_CHECKSUM_ALGORITHM,
        )
        self.assertEqual(
            migrate_values.tfvars_scalar_value(lines, "onramp_host_image_checksum"),
            migrate_values.ONRAMP_HOST_IMAGE_CHECKSUM,
        )
        self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])

    def test_preserves_onramp_image_when_only_url_matches(self) -> None:
        lines = [
            f'onramp_host_image_url = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_URL}"',
            'onramp_host_image_file_name = "custom.qcow2"',
        ]
        original = list(lines)

        self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])
        self.assertEqual(lines, original)

    def test_preserves_onramp_image_when_only_filename_matches(self) -> None:
        lines = [
            'onramp_host_image_url = "https://images.example.invalid/debian.qcow2"',
            f'onramp_host_image_file_name = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_FILE_NAME}"',
        ]
        original = list(lines)

        self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])
        self.assertEqual(lines, original)

    def test_preserves_exact_mutable_onramp_pair_with_custom_checksum_group(self) -> None:
        lines = [
            f'onramp_host_image_url = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_URL}"',
            f'onramp_host_image_file_name = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_FILE_NAME}"',
            'onramp_host_image_checksum_algorithm = "sha256"',
            'onramp_host_image_checksum = "' + "a" * 64 + '"',
        ]
        original = list(lines)

        self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])
        self.assertEqual(lines, original)

    def test_preserves_exact_mutable_onramp_pair_with_partial_checksum_group(self) -> None:
        base = [
            f'onramp_host_image_url = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_URL}"',
            f'onramp_host_image_file_name = "{migrate_values.ONRAMP_HOST_MUTABLE_IMAGE_FILE_NAME}"',
        ]
        partial_groups = (
            ['onramp_host_image_checksum_algorithm = "sha512"'],
            ['onramp_host_image_checksum = "' + "a" * 128 + '"'],
        )

        for partial_group in partial_groups:
            with self.subTest(partial_group=partial_group):
                lines = base + partial_group
                original = list(lines)
                self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])
                self.assertEqual(lines, original)

    def test_preserves_custom_onramp_image_pins_and_custom_integrity_group(self) -> None:
        lines = [
            'onramp_host_image_url = "https://images.example.invalid/debian.qcow2"',
            'onramp_host_image_file_name = "debian.qcow2"',
            'onramp_host_image_checksum_algorithm = "sha512"',
            'onramp_host_image_checksum = "' + "a" * 128 + '"',
        ]
        original = list(lines)
        custom_integrity = "---\nall:\n  vars:\n    forgejo_sha256_amd64: " + "b" * 64 + "\n"

        self.assertEqual(migrate_values.migrate_onramp_host_image_pin(lines), [])
        updated, changes = migrate_values.ensure_integrity_inventory_vars(custom_integrity)

        self.assertEqual(lines, original)
        self.assertEqual(updated, custom_integrity)
        self.assertEqual(changes, [])

    def test_updates_only_complete_legacy_managed_caddy_go_pin_group(self) -> None:
        inventory = "---\nall:\n  vars:\n" + "\n".join(
            f"    {key}: {value}" for key, value in migrate_values.CADDY_GO_LEGACY_MANAGED_DEFAULTS.items()
        ) + "\n"

        updated, changes = migrate_values.migrate_caddy_go_managed_defaults(inventory)

        self.assertEqual(changes, ["updated managed Caddy Go pin group"])
        self.assertIn('caddy_build_go_version: "1.25.1"', updated)
        self.assertIn("caddy_build_go_sha256_amd64: 7716a0d940a0", updated)
        self.assertIn("caddy_build_go_sha256_arm64: 65a3e34fb212", updated)
        self.assertEqual(migrate_values.migrate_caddy_go_managed_defaults(updated), (updated, []))

    def test_preserves_custom_caddy_go_pin_group(self) -> None:
        inventory = "---\nall:\n  vars:\n" + "\n".join(
            f"    {key}: {value}" for key, value in migrate_values.CADDY_GO_LEGACY_MANAGED_DEFAULTS.items()
        ) + "\n"
        inventory = inventory.replace("1.24.4", "1.24.3")

        self.assertEqual(migrate_values.migrate_caddy_go_managed_defaults(inventory), (inventory, []))

    def test_onramp_host_absent_does_not_add_onramp_host_values(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            changes = migrate_values.migrate(values)

            self.assertNotIn("onramp_host", (values / "terraform.tfvars").read_text(encoding="utf-8"))
            self.assertFalse(any("onramp_host" in change for change in changes))

    def test_adds_searxng_onramp_values_without_printing_url(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'technitium_container_ipv4_address = "192.0.2.53/24"\n'
                'technitium_container_ipv4_gateway = "192.0.2.1"\n'
                'technitium_container_search_domain = "lab.example"\n'
                'technitium_container_bridge = "vmbr0"\n'
                'technitium_container_dns_servers = ["192.0.2.1"]\n',
                encoding="utf-8",
            )
            (values / "dns-records.local.json").write_text('{"a_records":{}}\n', encoding="utf-8")
            settings = values.parent / "settings.local.json"
            original = settings.read_text(encoding="utf-8") if settings.exists() else None
            settings.write_text('{"services":["onramp_host","searxng_onramp"]}\n', encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(values.parent)
                changes = migrate_values.migrate(Path("values"))
                second_changes = migrate_values.migrate(Path("values"))
            finally:
                os.chdir(original_cwd)
                if original is None:
                    settings.unlink(missing_ok=True)
                else:
                    settings.write_text(original, encoding="utf-8")

            env_text = (values / ".env").read_text(encoding="utf-8")
            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            dns_text = (values / "dns-records.local.json").read_text(encoding="utf-8")
            self.assertIn("SEARXNG_SECRET_KEY=", env_text)  # public-safety: allow-secret
            self.assertIn("HERMES_WEB_SEARXNG_URL=https://searxng.apps.lab.example", env_text)
            self.assertIn('searxng_server_name = "searxng.apps.lab.example"', tfvars_text)
            self.assertIn('"searxng.apps.lab.example": "192.0.2.72"', dns_text)
            self.assertIn("added HERMES_WEB_SEARXNG_URL for SearXNG onramp", changes)
            self.assertNotIn("https://searxng.apps.lab.example", "\n".join(changes))
            self.assertEqual(second_changes, [])

    def test_idempotent_after_first_run(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text(
                "export TECHNITIUM_API_TOKEN='REPLACE_SECRET'\n"
                "export TF_VAR_lxc_root_password='REPLACE_PASSWORD'\n"
                "export TECHNITIUM_API_URL='http://192.0.2.53:5380/api'\n"
                "export DNS_RECORDS_FILE='values/dns-records.local.json'\n",
                encoding="utf-8",
            )
            (values / "terraform.tfvars").write_text("", encoding="utf-8")

            self.assertTrue(migrate_values.migrate(values))
            self.assertEqual(migrate_values.migrate(values), [])


if __name__ == "__main__":
    unittest.main()

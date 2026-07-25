from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate-values.py"
spec = importlib.util.spec_from_file_location("migrate_values", SCRIPT)
assert spec and spec.loader
migrate_values = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = migrate_values
spec.loader.exec_module(migrate_values)


class MigrateValuesTests(unittest.TestCase):
    def test_site_metadata_controls_enabled_services(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / "site.json").write_text(
                json.dumps({"name": "dev", "services": ["hermes"]}),
                encoding="utf-8",
            )
            self.assertEqual(migrate_values.enabled_services(values), {"hermes"})

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

    def test_ensure_lxc_template_integrity_tfvars_adds_missing_pins(self) -> None:
        lines = ['debian_template_url = "http://download.proxmox.com/images/system/debian-13-standard_13.1-2_amd64.tar.zst"\n']

        changes = migrate_values.ensure_lxc_template_integrity_tfvars(lines)

        self.assertIn("added debian_template_checksum", changes)
        self.assertIn("guest_vm_image_checksum", "\n".join(lines))
        self.assertEqual(migrate_values.ensure_lxc_template_integrity_tfvars(lines), [])

    def test_dns_migration_preserves_disabled_optional_service_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            records = Path(temp_dir) / "dns-records.local.json"
            original = {"a_records": {"infisical.example.internal": "192.0.2.70"}}
            records.write_text(json.dumps(original), encoding="utf-8")

            changes = migrate_values.ensure_dns_records(records, "example.internal", "", "")

            self.assertEqual(changes, [])
            self.assertEqual(json.loads(records.read_text(encoding="utf-8")), original)

    def test_dns_migration_adds_control_record_with_hermes_address(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            records = Path(temp_dir) / "dns-records.local.json"
            records.write_text('{"a_records": {}}', encoding="utf-8")

            changes = migrate_values.ensure_dns_records(records, "example.internal", "", "192.0.2.71")

            self.assertIn("added optional service DNS record", changes)
            output = json.loads(records.read_text(encoding="utf-8"))
            self.assertEqual(output["a_records"]["control.hermes.example.internal"], "192.0.2.71")
            self.assertEqual(migrate_values.ensure_dns_records(records, "example.internal", "", "192.0.2.71"), [])

    def test_ensure_technitium_pin_inventory_vars_adds_missing_pins(self) -> None:
        text, changes = migrate_values.ensure_technitium_pin_inventory_vars("all:\n  vars:\n")

        self.assertIn('technitium_discovery_version: "15.2.0"', text)
        self.assertIn("technitium_portable_sha256:", text)
        self.assertIn("added inventory technitium_discovery_version", changes)
        text_again, changes_again = migrate_values.ensure_technitium_pin_inventory_vars(text)
        self.assertEqual(text_again, text)
        self.assertEqual(changes_again, [])

    def test_ensure_hermes_pin_inventory_vars_adds_missing_pins(self) -> None:
        text, changes = migrate_values.ensure_hermes_pin_inventory_vars("all:\n  vars:\n    hermes_domain: hermes.example.internal\n")

        self.assertIn('hermes_discovery_version: "0.18.0"', text)
        self.assertIn('hermes_node_version: "22.23.1"', text)
        self.assertIn("hermes_node_sha256_amd64:", text)
        self.assertIn("added inventory hermes_discovery_version", changes)
        text_again, changes_again = migrate_values.ensure_hermes_pin_inventory_vars(text)
        self.assertEqual(text_again, text)
        self.assertEqual(changes_again, [])

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

    def test_migrates_legacy_forgejo_storage_to_service_storage(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'forgejo_data_dataset = "tank/forgejo"\n'
                'forgejo_data_host_path = "/tank/forgejo"\n'
                'forgejo_data_mount_path = "/var/lib/forgejo"\n'
                'forgejo_data_host_uid = 100000\n'
                'forgejo_data_host_gid = 100000\n',
                encoding="utf-8",
            )

            changes = migrate_values.migrate(values)

            tfvars_text = (values / "terraform.tfvars").read_text(encoding="utf-8")
            self.assertIn("service_storage = {", tfvars_text)
            self.assertIn('type          = "bind"', tfvars_text)
            self.assertIn('source        = "/tank/forgejo"', tfvars_text)
            self.assertIn('type       = "zfs_dataset"', tfvars_text)
            self.assertIn('dataset    = "tank/forgejo"', tfvars_text)
            self.assertIn('mountpoint = "/tank/forgejo"', tfvars_text)
            self.assertNotRegex(tfvars_text, r"(?m)^forgejo_data_dataset\s*=")
            self.assertNotRegex(tfvars_text, r"(?m)^forgejo_data_host_path\s*=")
            self.assertIn("migrated Forgejo storage to service_storage", changes)

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
            self.assertIn('onramp_host_image_url = "https://cloud.debian.org/images/cloud/trixie/20260623-2518/debian-13-genericcloud-amd64-20260623-2518.qcow2"', tfvars_text)
            self.assertIn('onramp_host_image_checksum_algorithm = "sha512"', tfvars_text)
            self.assertIn('onramp_host_image_checksum = "df2bd468b08566c0409a7982d6489d73499ad22f9a28646b538c2f21d08f15040a5e4737952ca209e9ad4488cd00793191791be9f135dee93082c86fcca3300c"', tfvars_text)
            self.assertIn('onramp_host_ipv4_address = "192.0.2.72/24"', tfvars_text)
            self.assertIn('onramp_host_deploy_user = "onramp"', tfvars_text)
            self.assertNotIn("onramp_host_template_vmid", tfvars_text)
            self.assertIn("added onramp_host_vmid", changes)
            self.assertEqual(second_changes, [])

    def test_pins_existing_legacy_onramp_image_values(self) -> None:
        lines = [
            'onramp_host_image_url = "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2"\n',
            'onramp_host_image_file_name = "debian-13-genericcloud-amd64.qcow2"\n',
        ]
        changes = migrate_values.ensure_onramp_image_integrity_tfvars(lines)
        text = "".join(lines)
        self.assertIn(migrate_values.PINNED_GUEST_VM_IMAGE_URL, text)
        self.assertIn(migrate_values.PINNED_GUEST_VM_IMAGE_FILE_NAME, text)
        self.assertIn("onramp_host_image_checksum", text)
        self.assertIn("pinned onramp_host_image_url", changes)
        self.assertIn("pinned onramp_host_image_file_name", changes)

    def test_forgejo_bootstrap_defaults_to_dedicated_admin_and_remote_owner(self) -> None:
        temp, values = self.make_values()
        with temp:
            (values / ".env").write_text("", encoding="utf-8")
            (values / "terraform.tfvars").write_text(
                'technitium_container_search_domain = "example.internal"\n',
                encoding="utf-8",
            )
            settings = values.parent / "settings.local.json"
            settings.write_text('{"services":["forgejo","forgejo_runner"]}\n', encoding="utf-8")
            original_cwd = Path.cwd()
            original_values_remote_scope = migrate_values.values_remote_scope
            try:
                import os

                migrate_values.values_remote_scope = lambda _values_dir: "salverius/homelab-values"
                os.chdir(values.parent)
                changes = migrate_values.migrate(Path("values"))
                second_changes = migrate_values.migrate(Path("values"))
            finally:
                os.chdir(original_cwd)
                migrate_values.values_remote_scope = original_values_remote_scope

            env_text = (values / ".env").read_text(encoding="utf-8")
            inventory_text = (values / "ansible" / "inventory" / "local.yml").read_text(encoding="utf-8")
            self.assertIn("FORGEJO_ADMIN_USERNAME=anvil", env_text)
            self.assertIn("FORGEJO_ADMIN_EMAIL=anvil@example.internal", env_text)
            self.assertIn("FORGEJO_ADMIN_PASSWORD=", env_text)  # public-safety: allow-secret
            self.assertIn("FORGEJO_REPO_OWNER_EMAIL=salverius@example.internal", env_text)
            self.assertIn("FORGEJO_REPO_OWNER_PASSWORD=", env_text)  # public-safety: allow-secret
            self.assertIn("forgejo_bootstrap_admin_username: \"{{ lookup('env', 'FORGEJO_ADMIN_USERNAME') }}\"", inventory_text)
            self.assertIn("forgejo_bootstrap_owner_email: \"{{ lookup('env', 'FORGEJO_REPO_OWNER_EMAIL') }}\"", inventory_text)
            self.assertIn("forgejo_bootstrap_owner_password: \"{{ lookup('env', 'FORGEJO_REPO_OWNER_PASSWORD') }}\"", inventory_text)
            self.assertIn("forgejo_runner_scope: salverius/homelab-values", inventory_text)
            self.assertIn("added FORGEJO_ADMIN_USERNAME default", changes)
            self.assertEqual(second_changes, [])

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

            self.assertIn("added debian_template_checksum", migrate_values.migrate(values))
            self.assertEqual(migrate_values.migrate(values), [])


if __name__ == "__main__":
    unittest.main()

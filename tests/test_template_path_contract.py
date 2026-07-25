from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VARIABLES = (ROOT / "infra" / "opentofu" / "variables.tf").read_text(encoding="utf-8")
RESOURCE = (ROOT / "infra" / "opentofu" / "main.tf").read_text(encoding="utf-8")


class TemplatePathContractTests(unittest.TestCase):
    datastore_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    filename_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    url_pattern = re.compile(r"^https?://[^\s]+$")

    def test_valid_template_identity_is_pathless(self) -> None:
        self.assertRegex("local", self.datastore_pattern)
        self.assertRegex("debian-13-standard_13.1-2_amd64.tar.zst", self.filename_pattern)
        self.assertRegex("http://download.example.invalid/debian.tar.zst", self.url_pattern)

    def test_path_like_template_identity_is_rejected(self) -> None:
        for value in ("/local", "local/storage", "../local", ""):
            self.assertNotRegex(value, self.datastore_pattern)
        for value in ("/tmp/template.tar.zst", "nested/template.tar.zst", "../template.tar.zst", ""):
            self.assertNotRegex(value, self.filename_pattern)
        for value in ("download.example.invalid/template.tar.zst", "file:///tmp/template.tar.zst", ""):
            self.assertNotRegex(value, self.url_pattern)

    def test_opentofu_resource_uses_the_same_identity_fields(self) -> None:
        self.assertIn("datastore_id        = var.template_datastore_id", RESOURCE)
        self.assertIn("file_name           = var.debian_template_file_name", RESOURCE)
        self.assertIn("node_name           = var.proxmox_node_name", RESOURCE)
        self.assertIn("url                 = var.debian_template_url", RESOURCE)
        self.assertIn("template_datastore_id must be a single Proxmox datastore identifier", VARIABLES)
        self.assertIn("debian_template_file_name must be a file name, not a path", VARIABLES)


if __name__ == "__main__":
    unittest.main()

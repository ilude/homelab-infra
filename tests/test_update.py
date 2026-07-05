from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.py"
spec = importlib.util.spec_from_file_location("update_script", SCRIPT)
assert spec and spec.loader
update_script = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = update_script
spec.loader.exec_module(update_script)


class UpdateTests(unittest.TestCase):
    def fake_release(self, version: str, published_at: datetime) -> bytes:
        return json.dumps(
            {
                "tag_name": f"v{version}",
                "published_at": published_at.isoformat().replace("+00:00", "Z"),
                "html_url": "https://example.invalid/release",
                "assets": [
                    {
                        "name": f"tofu_{version}_SHA256SUMS",
                        "browser_download_url": "https://example.invalid/checksums",
                    }
                ],
            }
        ).encode("utf-8")

    def fake_opener(self, version: str, published_at: datetime) -> callable:
        def opener(url: str) -> bytes:
            if url.endswith("/checksums"):
                return f"abc123  tofu_{version}_linux_amd64.zip\n".encode("utf-8")
            return self.fake_release(version, published_at)

        return opener

    def test_updates_eligible_dockerfile_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            dockerfile = root / "tools" / "Dockerfile"
            dockerfile.write_text(
                "ARG OPENTOFU_VERSION=1.0.0\n"
                "ARG OPENTOFU_LINUX_AMD64_SHA256=old\n",
                encoding="utf-8",
            )
            target = update_script.TARGETS[0]
            now = datetime(2026, 7, 5, tzinfo=timezone.utc)

            result = update_script.process_target(
                target,
                root,
                now,
                timedelta(hours=48),
                self.fake_opener("1.1.0", now - timedelta(hours=72)),
            )

            self.assertEqual(result.status, "updated")
            self.assertEqual(
                dockerfile.read_text(encoding="utf-8"),
                "ARG OPENTOFU_VERSION=1.1.0\n"
                "ARG OPENTOFU_LINUX_AMD64_SHA256=abc123\n",
            )

    def test_holds_recent_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values_inventory = root / "values" / "ansible" / "inventory"
            values_inventory.mkdir(parents=True)
            inventory = values_inventory / "local.yml"
            inventory.write_text('forgejo_version: "12.0.4"\n', encoding="utf-8")
            target = update_script.TARGETS[2]
            now = datetime(2026, 7, 5, tzinfo=timezone.utc)

            result = update_script.process_target(
                target,
                root,
                now,
                timedelta(hours=48),
                lambda _url: self.fake_release("12.1.0", now - timedelta(hours=12)),
            )

            self.assertEqual(result.status, "hold")
            self.assertEqual(inventory.read_text(encoding="utf-8"), 'forgejo_version: "12.0.4"\n')

    def test_skips_missing_private_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = update_script.TARGETS[2]
            result = update_script.process_target(
                target,
                Path(temp),
                datetime(2026, 7, 5, tzinfo=timezone.utc),
                timedelta(hours=48),
                lambda _url: self.fake_release("12.1.0", datetime(2026, 7, 1, tzinfo=timezone.utc)),
            )

            self.assertEqual(result.status, "skip")
            self.assertEqual(result.detail, "file not present")


if __name__ == "__main__":
    unittest.main()

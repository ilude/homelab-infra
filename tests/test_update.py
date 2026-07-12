from __future__ import annotations

import base64
import importlib.util
import json
import sys
from hashlib import sha256
import tempfile
import unittest
from unittest.mock import patch
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
                return f"{'a' * 64}  tofu_{version}_linux_amd64.zip\n".encode("utf-8")
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
                f"ARG OPENTOFU_LINUX_AMD64_SHA256={'a' * 64}\n",
            )

    def test_holds_recent_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values_inventory = root / "values" / "ansible" / "inventory"
            values_inventory.mkdir(parents=True)
            inventory = values_inventory / "local.yml"
            inventory.write_text(
                'forgejo_version: "12.0.4"\n'
                "forgejo_sha256_amd64: 59fb6129e0396dc3502be60950438a03d227bb5691ee08b02dd38794f3d25a2a\n",
                encoding="utf-8",
            )
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
            self.assertEqual(
                inventory.read_text(encoding="utf-8"),
                'forgejo_version: "12.0.4"\n'
                "forgejo_sha256_amd64: 59fb6129e0396dc3502be60950438a03d227bb5691ee08b02dd38794f3d25a2a\n",
            )

    def test_custom_private_pin_and_checksum_are_not_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_dir = root / "values" / "ansible" / "inventory"
            inventory_dir.mkdir(parents=True)
            inventory = inventory_dir / "local.yml"
            original = (
                'forgejo_version: "12.0.3"\n'
                "forgejo_sha256_amd64: custom-checksum\n"
            )
            inventory.write_text(original, encoding="utf-8")

            result = update_script.process_target(
                update_script.TARGETS[2],
                root,
                datetime(2026, 7, 5, tzinfo=timezone.utc),
                timedelta(hours=48),
                lambda _url: self.fail("custom pins must not query releases"),
            )

            self.assertEqual(result.status, "skip")
            self.assertEqual(result.detail, "custom operator pin")
            self.assertEqual(inventory.read_text(encoding="utf-8"), original)

    def test_managed_private_version_and_checksum_advance_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_dir = root / "values" / "ansible" / "inventory"
            inventory_dir.mkdir(parents=True)
            inventory = inventory_dir / "local.yml"
            inventory.write_text(
                'forgejo_version: "12.0.4"\n'
                "forgejo_sha256_amd64: 59fb6129e0396dc3502be60950438a03d227bb5691ee08b02dd38794f3d25a2a\n",
                encoding="utf-8",
            )
            now = datetime(2026, 7, 5, tzinfo=timezone.utc)

            def opener(url: str) -> bytes:
                if url.endswith("checksums"):
                    return f"{'b' * 64}  forgejo-12.1.0-linux-amd64\n".encode()
                return json.dumps(
                    {
                        "tag_name": "v12.1.0",
                        "published_at": (now - timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
                        "assets": [{"name": "forgejo_12.1.0_sha256sums.txt", "browser_download_url": "https://example.invalid/checksums"}],
                    }
                ).encode("utf-8")

            result = update_script.process_target(update_script.TARGETS[2], root, now, timedelta(hours=48), opener)

            self.assertEqual(result.status, "updated")
            self.assertEqual(
                inventory.read_text(encoding="utf-8"),
                f'forgejo_version: "12.1.0"\nforgejo_sha256_amd64: {"b" * 64}\n',
            )

    def test_updates_paired_architecture_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_dir = root / "values" / "ansible" / "inventory"
            inventory_dir.mkdir(parents=True)
            inventory = inventory_dir / "local.yml"
            inventory.write_text(
                'forgejo_runner_version: "12.7.3"\n'
                'forgejo_runner_sha256_amd64: 706f718bdf63baa345a1794924eec089be80df9bc38f02cefdc9a492f7c86b83\n'
                'forgejo_runner_sha256_arm64: be77c54925aed80b0967dcdfe89aa8c9310fddefacbe16ca05ed22fe2bfd659c\n',
                encoding="utf-8",
            )
            target = update_script.TARGETS[3]
            now = datetime(2026, 7, 5, tzinfo=timezone.utc)

            def opener(url: str) -> bytes:
                if url.endswith("checksums"):
                    return (
                        f"{'a' * 64}  forgejo-runner-12.8.0-linux-amd64\n"
                        f"{'b' * 64}  forgejo-runner-12.8.0-linux-arm64\n"
                    ).encode()
                return json.dumps(
                    {
                        "tag_name": "v12.8.0",
                        "published_at": (now - timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
                        "assets": [
                            {
                                "name": "forgejo-runner-12.8.0-sha256sums.txt",
                                "browser_download_url": "https://example.invalid/checksums",
                            }
                        ],
                    }
                ).encode("utf-8")

            result = update_script.process_target(target, root, now, timedelta(hours=48), opener)

            self.assertEqual(result.status, "updated")
            text = inventory.read_text(encoding="utf-8")
            self.assertIn(f"forgejo_runner_sha256_amd64: {'a' * 64}", text)
            self.assertIn(f"forgejo_runner_sha256_arm64: {'b' * 64}", text)

    def test_resolves_verified_linux_amd64_oci_index_fixture(self) -> None:
        target = update_script.OCI_TARGETS[0]
        config_body = b'{"created":"2026-06-01T00:00:00Z"}'
        config_digest = f"sha256:{sha256(config_body).hexdigest()}"
        manifest_body = json.dumps({"config": {"digest": config_digest}}).encode()
        manifest_digest = f"sha256:{sha256(manifest_body).hexdigest()}"
        index_body = json.dumps({
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [{"digest": manifest_digest, "platform": {"os": "linux", "architecture": "amd64", "os.version": "fixture"}}],
        }).encode()
        index_digest = f"sha256:{sha256(index_body).hexdigest()}"

        def response(body: bytes) -> update_script.OciResponse:
            return update_script.OciResponse(body, {"Docker-Content-Digest": f"sha256:{sha256(body).hexdigest()}"})

        def fetch(url: str, _accept: str) -> update_script.OciResponse:
            if url.endswith("/tags/list?n=1000"):
                return response(b'{"tags":["v0.161.9","v0.161.10","v0.161.12"]}')
            if url.endswith("/manifests/v0.161.12"):
                return response(index_body)
            if url.endswith(f"/manifests/{manifest_digest}"):
                return response(manifest_body)
            if url.endswith(f"/blobs/{config_digest}"):
                return response(config_body)
            self.fail(url)

        reference, created = update_script.resolve_oci_reference(target, fetch)
        self.assertEqual(reference, f"docker.io/infisical/infisical:v0.161.12@{index_digest}")
        self.assertEqual(created, datetime(2026, 6, 1, tzinfo=timezone.utc))

    def test_updates_managed_oci_group_together_after_re_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            members = [target for target in update_script.OCI_TARGETS if target.group == "infisical"]
            inventory.write_text(
                "infisical_container_image: " + members[0].managed_default + "\n"
                "infisical_postgres_image: " + members[1].managed_default + "\n"
                "infisical_redis_image: " + members[2].managed_default + "\n",
                encoding="utf-8",
            )
            created = datetime(2026, 6, 1, tzinfo=timezone.utc)
            resolved = {
                target: (target.managed_default.replace("@sha256:", "-next@sha256:"), created)
                for target in members
            }

            with patch.object(update_script, "resolve_oci_reference", side_effect=lambda target, _fetch: resolved[target]) as resolver:
                results = update_script.process_oci_group(
                    "infisical",
                    root,
                    datetime(2026, 7, 5, tzinfo=timezone.utc),
                    lambda _url, _accept: self.fail("resolver is mocked"),
                )

            self.assertEqual([result.status for result in results], ["updated"] * 3)
            self.assertEqual(resolver.call_count, 6)
            updated = inventory.read_text(encoding="utf-8")
            for reference, _created in resolved.values():
                self.assertIn(reference, updated)

    def test_custom_oci_group_is_preserved_without_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            members = [target for target in update_script.OCI_TARGETS if target.group == "infisical"]
            original = (
                "infisical_container_image: docker.io/example/custom:v1@sha256:" + "a" * 64 + "\n"
                "infisical_postgres_image: " + members[1].managed_default + "\n"
                "infisical_redis_image: " + members[2].managed_default + "\n"
            )
            inventory.write_text(original, encoding="utf-8")

            results = update_script.process_oci_group(
                "infisical",
                root,
                datetime(2026, 7, 5, tzinfo=timezone.utc),
                lambda _url, _accept: self.fail("custom groups must not query the registry"),
            )

            self.assertTrue(all(result.status == "skip" for result in results))
            self.assertEqual(inventory.read_text(encoding="utf-8"), original)

    def test_rejects_oci_digest_header_body_mismatch(self) -> None:
        response = update_script.OciResponse(b"{}", {"Docker-Content-Digest": "sha256:" + "0" * 64})
        with self.assertRaisesRegex(update_script.UpdateError, "header does not match body"):
            update_script.oci_digest(response, "fixture")

    def technitium_release(self, version: str, published_at: datetime, release_id: int) -> dict[str, object]:
        return {
            "id": release_id,
            "tag_name": f"v{version}",
            "published_at": published_at.isoformat().replace("+00:00", "Z"),
            "draft": False,
            "prerelease": False,
        }

    def test_technitium_selects_current_eligible_release_while_latest_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            target = update_script.TECHNITIUM_DISCOVERY
            inventory.write_text(
                f'technitium_discovery_version: "{target.managed_version}"\n'
                f"technitium_portable_sha256: {target.managed_checksum}\n"
                f"technitium_artifact_path: {target.managed_artifact_path}\n",
                encoding="utf-8",
            )
            now = datetime(2026, 7, 10, tzinfo=timezone.utc)
            releases = [
                self.technitium_release("15.3.0", now - timedelta(hours=167), 2),
                self.technitium_release("15.2.0", now - timedelta(days=30), 1),
            ]

            result = update_script.process_discovery_target(
                target, root, now, lambda _url: json.dumps(releases).encode()
            )

            self.assertEqual(result.status, "current")
            self.assertIn("15.3.0 remains inside", result.detail)
            self.assertEqual(inventory.read_text(encoding="utf-8").count("15.2.0"), 1)

    def test_technitium_updates_at_exact_hold_boundary_and_re_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            target = update_script.TECHNITIUM_DISCOVERY
            inventory.write_text(
                f'technitium_discovery_version: "{target.managed_version}"\n'
                f"technitium_portable_sha256: {target.managed_checksum}\n"
                f"technitium_artifact_path: {target.managed_artifact_path}\n",
                encoding="utf-8",
            )
            now = datetime(2026, 7, 12, tzinfo=timezone.utc)
            release = self.technitium_release("15.3.0", now - timedelta(hours=168), 349170811)
            checksum = "b" * 64
            commit = "c" * 40
            calls = {"release": 0, "checksum": 0, "tag": 0}

            def opener(url: str) -> bytes:
                if url.endswith(".sha256"):
                    calls["checksum"] += 1
                    return checksum.encode()
                if "/git/ref/tags/" in url:
                    calls["tag"] += 1
                    return json.dumps({"object": {"type": "commit", "sha": commit}}).encode()
                calls["release"] += 1
                return json.dumps([release]).encode()

            result = update_script.process_discovery_target(target, root, now, opener)

            self.assertEqual(result.status, "updated")
            self.assertEqual(calls, {"release": 2, "checksum": 2, "tag": 2})
            self.assertIn("release id 349170811", result.detail)
            self.assertIn(commit, result.detail)
            text = inventory.read_text(encoding="utf-8")
            self.assertIn('technitium_discovery_version: "15.3.0"', text)
            self.assertIn(checksum, text)
            self.assertIn(target.managed_artifact_path, text)

    def test_technitium_custom_pin_group_is_preserved_without_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            original = (
                'technitium_discovery_version: "15.1.0"\n'
                f"technitium_portable_sha256: {'d' * 64}\n"
                "technitium_artifact_path: custom/cache/\n"
            )
            inventory.write_text(original, encoding="utf-8")

            result = update_script.process_discovery_target(
                update_script.TECHNITIUM_DISCOVERY,
                root,
                datetime(2026, 7, 12, tzinfo=timezone.utc),
                lambda _url: self.fail("custom groups must not query upstream"),
            )

            self.assertEqual(result.status, "skip")
            self.assertEqual(inventory.read_text(encoding="utf-8"), original)

    def test_technitium_rejects_invalid_published_checksum(self) -> None:
        target = update_script.TECHNITIUM_DISCOVERY
        with self.assertRaisesRegex(update_script.UpdateError, "invalid published SHA-256"):
            update_script.technitium_checksum(target, "15.2.0", lambda _url: b"not-a-sha256")

    def test_hermes_current_pin_verifies_strict_hold_pypi_provenance_and_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            target = update_script.HERMES_DISCOVERY
            inventory.write_text(
                f'hermes_discovery_version: "{target.managed_version}"\n'
                f'hermes_discovery_tag: "{target.managed_tag}"\n'
                f"hermes_discovery_commit: {target.managed_commit}\n"
                f"hermes_discovery_wheel_sha256: {target.managed_wheel_sha256}\n",
                encoding="utf-8",
            )
            lock = root / "infra" / "ansible" / "roles" / "hermes" / "files" / "requirements-0.18.0.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text(
                (
                    Path(__file__).resolve().parents[1]
                    / "infra"
                    / "ansible"
                    / "roles"
                    / "hermes"
                    / "files"
                    / "requirements-0.18.0.lock"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            now = datetime(2026, 7, 10, 20, 8, 6, tzinfo=timezone.utc)
            eligible = {
                "id": 1,
                "tag_name": target.managed_tag,
                "published_at": "2026-07-01T20:08:06Z",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "hermes_agent-0.18.0-py3-none-any.whl.sigstore.json"}],
            }
            held = {
                "id": 2,
                "tag_name": "v2026.7.7.2",
                "published_at": "2026-07-08T20:08:06Z",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "hermes_agent-0.18.1-py3-none-any.whl.sigstore.json"}],
            }
            filename = "hermes_agent-0.18.0-py3-none-any.whl"
            statement = base64.b64encode(json.dumps({
                "subject": [{"name": filename, "digest": {"sha256": target.managed_wheel_sha256}}]
            }).encode()).decode()

            def opener(url: str) -> bytes:
                if "/pypi/hermes-agent/" in url:
                    return json.dumps({"urls": [{
                        "filename": filename,
                        "packagetype": "bdist_wheel",
                        "python_version": "py3",
                        "url": f"https://files.pythonhosted.org/packages/fixture/{filename}",
                        "digests": {"sha256": target.managed_wheel_sha256},
                    }]}).encode()
                if "/integrity/hermes-agent/" in url:
                    return json.dumps({"attestation_bundles": [{
                        "publisher": {
                            "environment": "pypi",
                            "kind": "GitHub",
                            "repository": "NousResearch/hermes-agent",
                            "workflow": "upload_to_pypi.yml",
                        },
                        "attestations": [{"envelope": {"statement": statement}}],
                    }]}).encode()
                if "/git/ref/tags/" in url:
                    return json.dumps({"object": {"type": "commit", "sha": target.managed_commit}}).encode()
                return json.dumps([held, eligible]).encode()

            result = update_script.process_hermes_discovery_target(target, root, now, opener)

            self.assertEqual(result.status, "current")
            self.assertIn("v2026.7.7.2 remains inside", result.detail)

    def test_hermes_rejects_incomplete_tracked_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock = root / "infra" / "ansible" / "roles" / "hermes" / "files" / "requirements-0.18.0.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text(
                "hermes-agent[messaging, pty, web]==0.18.0 \\\n"
                f"    --hash=sha256:{update_script.HERMES_DISCOVERY.managed_wheel_sha256}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(update_script.UpdateError, "expected 79"):
                update_script.validate_hermes_lock(
                    root,
                    update_script.HERMES_DISCOVERY.managed_version,
                    update_script.HERMES_DISCOVERY.managed_wheel_sha256,
                )

    def test_hermes_pin_write_replaces_file_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "local.yml"
            path.write_text("before\n", encoding="utf-8")

            with patch.object(update_script.os, "replace", wraps=update_script.os.replace) as replace:
                update_script.atomic_write_text(path, "after\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "after\n")
            replace.assert_called_once()
            self.assertEqual(Path(replace.call_args.args[0]).parent, path.parent)
            self.assertEqual(replace.call_args.args[1], path)

    def test_hermes_custom_pin_group_is_preserved_without_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            original = (
                'hermes_discovery_version: "0.17.0"\n'
                'hermes_discovery_tag: "v2026.6.1"\n'
                f"hermes_discovery_commit: {'a' * 40}\n"
                f"hermes_discovery_wheel_sha256: {'b' * 64}\n"
            )
            inventory.write_text(original, encoding="utf-8")

            result = update_script.process_hermes_discovery_target(
                update_script.HERMES_DISCOVERY,
                root,
                datetime(2026, 7, 20, tzinfo=timezone.utc),
                lambda _url: self.fail("custom Hermes pins must not query upstream"),
            )

            self.assertEqual(result.status, "skip")
            self.assertEqual(result.detail, "custom operator pin group (hermes)")
            self.assertEqual(inventory.read_text(encoding="utf-8"), original)

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

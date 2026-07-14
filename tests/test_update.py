from __future__ import annotations

import base64
import io
import importlib.util
import json
import sys
from hashlib import sha256
import tempfile
import unittest
import zipfile
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
                "hermes_artifact_source: official_pypi\n"
                "hermes_custom_tag_prefix: homelab-v\n"
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

    def custom_wheel(self, version: str, requirements: tuple[str, ...] = (), requires_python: str | None = None, extras: tuple[str, ...] = (), tags: tuple[str, ...] = ("py3-none-any",)) -> bytes:
        output = io.BytesIO()
        metadata = f"Name: hermes-agent\nVersion: {version}\n" + "".join(f"Requires-Dist: {item}\n" for item in requirements)
        if requires_python is not None:
            metadata += f"Requires-Python: {requires_python}\n"
        metadata += "".join(f"Provides-Extra: {item}\n" for item in extras)
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(f"hermes_agent-{version}.dist-info/METADATA", metadata)
            archive.writestr(f"hermes_agent-{version}.dist-info/WHEEL", "Wheel-Version: 1.0\n" + "".join(f"Tag: {item}\n" for item in tags))
        return output.getvalue()

    def test_custom_hermes_release_writes_verified_pins_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "hermes_artifact_source: custom_github_release\n"
                "hermes_custom_repository: operator/hermes\n"
                "hermes_custom_tag_prefix: homelab-v\n"
                'hermes_discovery_version: "0.18.0"\n'
                'hermes_discovery_tag: "v2026.7.1"\n'
                f"hermes_discovery_commit: {'a' * 40}\n"
                f"hermes_discovery_wheel_sha256: {'b' * 64}\n",
                encoding="utf-8",
            )
            version = "0.18.0"
            wheel = self.custom_wheel(version, ("known-package>=1",))
            official_wheel = self.custom_wheel(version, ("known-package>=1",))
            checksum = sha256(wheel).hexdigest()
            official_checksum = sha256(official_wheel).hexdigest()
            lock = root / "infra" / "ansible" / "roles" / "hermes" / "files" / "requirements-0.18.0.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text((Path(__file__).resolve().parents[1] / "infra" / "ansible" / "roles" / "hermes" / "files" / "requirements-0.18.0.lock").read_text(encoding="utf-8"), encoding="utf-8")
            now = datetime(2026, 7, 12, tzinfo=timezone.utc)
            filename = f"hermes_agent-{version}-py3-none-any.whl"
            release = {
                "tag_name": "homelab-v0.18.0.1", "published_at": (now - timedelta(hours=168)).isoformat().replace("+00:00", "Z"),  # public-safety: allow-ip
                "draft": False, "prerelease": False,
                "assets": [
                    {"name": filename, "browser_download_url": f"https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}"},  # public-safety: allow-ip
                    {"name": f"{filename}.sha256", "browser_download_url": f"https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}.sha256"},  # public-safety: allow-ip
                ],
            }

            limits: dict[str, list[int | None]] = {}

            def opener(url: str, max_bytes: int | None = None) -> bytes:
                limits.setdefault(url, []).append(max_bytes)
                if url.endswith(f"/{filename}.sha256"):
                    return f"{checksum}  {filename}\n".encode()
                if url == f"https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}":  # public-safety: allow-ip
                    return wheel
                if url.endswith("/" + filename):
                    return official_wheel
                if "/pypi/hermes-agent/" in url:
                    return json.dumps({"urls": [{
                        "filename": filename,
                        "packagetype": "bdist_wheel",
                        "python_version": "py3",
                        "url": f"https://files.pythonhosted.org/packages/fixture/{filename}",
                        "digests": {"sha256": official_checksum},
                    }]}).encode()
                if "/integrity/hermes-agent/" in url:
                    self.fail("custom Hermes releases must not query PyPI provenance")
                if "/git/ref/tags/" in url:
                    return json.dumps({"object": {"type": "commit", "sha": "c" * 40}}).encode()
                return json.dumps([release]).encode()

            writes: list[Path] = []
            original_write = update_script.atomic_write_if_changed
            with patch.object(update_script, "atomic_write_if_changed", side_effect=lambda path, content: (writes.append(path), original_write(path, content))[1]):
                result = update_script.process_hermes_discovery_target(update_script.HERMES_DISCOVERY, root, now, opener)

            self.assertEqual(result.status, "updated")
            self.assertEqual(writes[-1], inventory)
            self.assertTrue(all(path.parent == writes[0].parent for path in writes[:-1]))
            updated = inventory.read_text(encoding="utf-8")
            self.assertIn(f"hermes_discovery_wheel_sha256: {checksum}", updated)
            artifact = root / "values" / "artifacts" / "hermes" / f"homelab-v0.18.0.1-{checksum[:12]}"  # public-safety: allow-ip
            self.assertIn(f"hermes_custom_wheel_url: https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}", updated)  # public-safety: allow-ip
            self.assertIn(f"hermes_custom_requirements_lock_path: /workspace/values/artifacts/hermes/{artifact.name}/requirements.lock", updated)
            full_lock = artifact / "requirements.lock"
            dependencies_lock = artifact / "requirements-dependencies.lock"
            self.assertIn(f"--hash=sha256:{checksum}", full_lock.read_text(encoding="utf-8"))
            self.assertNotIn("hermes-agent[messaging, pty, web]==0.18.0", dependencies_lock.read_text(encoding="utf-8"))
            original = inventory.read_text(encoding="utf-8")
            second = update_script.process_hermes_discovery_target(update_script.HERMES_DISCOVERY, root, now, opener)
            self.assertEqual(second.status, "current")
            self.assertEqual(inventory.read_text(encoding="utf-8"), original)
            self.assertEqual(
                limits[f"https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}"],  # public-safety: allow-ip
                [update_script.HERMES_MAX_WHEEL_BYTES] * 4,
            )
            self.assertEqual(
                limits[f"https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1/{filename}.sha256"],  # public-safety: allow-ip
                [update_script.HERMES_MAX_MANIFEST_BYTES] * 4,
            )

    def test_fetch_url_limits_opener_and_rejects_oversized_data(self) -> None:
        limits: list[int | None] = []

        def opener(_url: str, max_bytes: int | None) -> bytes:
            limits.append(max_bytes)
            return b"ok"

        self.assertEqual(update_script.fetch_url("https://example.invalid/fixture", opener, 2), b"ok")
        self.assertEqual(limits, [2])
        with self.assertRaisesRegex(update_script.UpdateError, "exceeds 1 bytes"):
            update_script.fetch_url("https://example.invalid/fixture", lambda _url: b"xx", 1)

    def test_fetch_url_rejects_declared_and_streamed_oversize_responses(self) -> None:
        class Response:
            def __init__(self, content_length: str | None, body: bytes) -> None:
                self.headers = {} if content_length is None else {"Content-Length": content_length}
                self.body = body
                self.read_limits: list[int | None] = []

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, limit: int | None = None) -> bytes:
                self.read_limits.append(limit)
                return self.body if limit is None else self.body[:limit]

        declared = Response("3", b"ok")
        with patch.object(update_script.urllib.request, "urlopen", return_value=declared):
            with self.assertRaisesRegex(update_script.UpdateError, "exceeds 2 bytes"):
                update_script.fetch_url("https://example.invalid/fixture", max_bytes=2)
        self.assertEqual(declared.read_limits, [])

        streamed = Response(None, b"xyz")
        with patch.object(update_script.urllib.request, "urlopen", return_value=streamed):
            with self.assertRaisesRegex(update_script.UpdateError, "exceeds 2 bytes"):
                update_script.fetch_url("https://example.invalid/fixture", max_bytes=2)
        self.assertEqual(streamed.read_limits, [3])

    def test_hermes_rejects_partial_artifact_source_configuration(self) -> None:
        cases = (
            "hermes_artifact_source: custom_github_release\n",
            "hermes_artifact_source: official_pypi\nhermes_custom_repository: operator/hermes\n",
            "hermes_artifact_source: custom_github_release\nhermes_custom_repository: operator/hermes\n",
            "hermes_artifact_source: custom_github_release\nhermes_custom_repository: operator/hermes\nhermes_custom_tag_prefix: homelab-v\nhermes_custom_wheel_url: https://example.invalid/wheel\n",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(update_script.UpdateError):
                update_script.hermes_custom_config(text)

    def test_custom_hermes_release_accepts_only_prefix_version_and_positive_revision(self) -> None:
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        release = {
            "tag_name": "homelab-v0.18.0.2",  # public-safety: allow-ip
            "published_at": (now - timedelta(hours=168)).isoformat().replace("+00:00", "Z"),
            "draft": False,
            "prerelease": False,
            "assets": [],
        }
        ignored = [
            {**release, "tag_name": "v2026.7.1"},
            {**release, "tag_name": "homelab-v0.18.0.0"},  # public-safety: allow-ip
        ]
        selected, version = update_script.hermes_custom_release(
            "operator/hermes", "homelab-v", now, lambda _url: json.dumps([*ignored, release]).encode()
        )
        self.assertEqual(
            (selected.version, version),
            ("homelab-v0.18.0.2", "0.18.0"),  # public-safety: allow-ip
        )

    def test_custom_hermes_rejects_malformed_release_assets(self) -> None:
        release = update_script.Release(
            "homelab-v0.18.0.1", datetime(2026, 7, 1, tzinfo=timezone.utc), "", {  # public-safety: allow-ip
                "assets": [{"name": "hermes_agent-0.18.0-py3-none-any.whl", "browser_download_url": "https://example.invalid/wheel"}],
            },
        )

        with self.assertRaisesRegex(update_script.UpdateError, "assets are malformed"):
            update_script.hermes_custom_assets("operator/hermes", release, "0.18.0")

    def test_custom_hermes_rejects_noncanonical_asset_url(self) -> None:
        filename = "hermes_agent-0.18.0-py3-none-any.whl"
        release = update_script.Release(
            "homelab-v0.18.0.1", datetime(2026, 7, 1, tzinfo=timezone.utc), "", {  # public-safety: allow-ip
                "assets": [
                    {"name": filename, "browser_download_url": "https://example.invalid/wheel"},
                    {"name": f"{filename}.sha256", "browser_download_url": "https://example.invalid/manifest"},
                ],
            },
        )
        with self.assertRaisesRegex(update_script.UpdateError, "assets are malformed"):
            update_script.hermes_custom_assets("operator/hermes", release, "0.18.0")

    def test_custom_hermes_rejects_duplicate_associated_asset(self) -> None:
        filename = "hermes_agent-0.18.0-py3-none-any.whl"
        release = update_script.Release(
            "homelab-v0.18.0.1", datetime(2026, 7, 1, tzinfo=timezone.utc), "", {  # public-safety: allow-ip
                "assets": [
                    *({"name": f"{filename}{suffix}", "browser_download_url": f"https://example.invalid/{suffix}"} for suffix in ("", ".sha256")),

                    {"name": f"{filename}.sha256", "browser_download_url": "https://example.invalid/duplicate"},
                ],
            },
        )

        with self.assertRaisesRegex(update_script.UpdateError, "assets are malformed"):
            update_script.hermes_custom_assets("operator/hermes", release, "0.18.0")

    def test_custom_hermes_rejects_changed_wheel_dependency_metadata(self) -> None:
        for requirements in ((), ("known-package>=2",), ("known-package==1", "added-package==1")):
            with self.subTest(requirements=requirements):
                with self.assertRaisesRegex(update_script.UpdateError, "metadata differs"):
                    update_script.hermes_custom_wheel_metadata(
                        self.custom_wheel("0.18.0", requirements), "0.18.0",
                        ("hermes-agent", "0.18.0", ("known-package>=1",), None, (), ("py3-none-any",)),
                    )

    def test_custom_hermes_rejects_rollback_from_current_valid_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "values" / "ansible" / "inventory" / "local.yml"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "hermes_artifact_source: custom_github_release\nhermes_custom_repository: operator/hermes\n"
                "hermes_custom_tag_prefix: homelab-v\n"
                "hermes_discovery_version: 0.18.0\nhermes_discovery_tag: homelab-v0.18.0.2\n"  # public-safety: allow-ip
                f"hermes_discovery_commit: {'a' * 40}\nhermes_discovery_wheel_sha256: {'b' * 64}\n"
                "hermes_custom_wheel_url: https://github.com/operator/hermes/releases/download/homelab-v0.18.0.2/wheel\n"  # public-safety: allow-ip
                "hermes_custom_requirements_lock_path: /workspace/values/artifacts/hermes/current/requirements.lock\n"
                "hermes_custom_dependencies_lock_path: /workspace/values/artifacts/hermes/current/requirements-dependencies.lock\n",
                encoding="utf-8",
            )
            release = update_script.Release("homelab-v0.18.0.1", datetime(2026, 7, 1, tzinfo=timezone.utc), "", {})  # public-safety: allow-ip
            with patch.object(update_script, "hermes_custom_release", return_value=(release, "0.18.0")):
                with self.assertRaisesRegex(update_script.UpdateError, "refusing custom release rollback"):
                    update_script.process_hermes_discovery_target(update_script.HERMES_DISCOVERY, root, datetime(2026, 7, 12, tzinfo=timezone.utc), lambda _url: self.fail("rollback must precede downloads"))

    def test_custom_hermes_rejects_first_full_release_page(self) -> None:
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        with self.assertRaisesRegex(update_script.UpdateError, "pagination is unsupported"):
            update_script.hermes_custom_release(
                "operator/hermes", "homelab-v", now, lambda _url: json.dumps([{}] * 100).encode()
            )

    def test_custom_hermes_canonical_url_encodes_tag(self) -> None:
        filename = "hermes_agent-0.18.0-py3-none-any.whl"
        tag = "homelab-v0.18.0.1+fixture"  # public-safety: allow-ip
        base = "https://github.com/operator/hermes/releases/download/homelab-v0.18.0.1%2Bfixture/"  # public-safety: allow-ip
        release = update_script.Release(tag, datetime(2026, 7, 1, tzinfo=timezone.utc), "", {"assets": [
            {"name": filename, "browser_download_url": base + filename},
            {"name": f"{filename}.sha256", "browser_download_url": base + f"{filename}.sha256"},
        ]})
        self.assertEqual(
            update_script.hermes_custom_assets("operator/hermes", release, "0.18.0"),
            (filename, base + filename, base + f"{filename}.sha256"),
        )

    def test_custom_hermes_compares_all_wheel_metadata(self) -> None:
        expected = update_script.hermes_wheel_metadata(
            self.custom_wheel("0.18.0", ("known-package>=1",), ">=3.11", ("web",), ("py3-none-any",)),
            "0.18.0", "official",
        )
        for wheel in (
            self.custom_wheel("0.18.0", ("known-package>=1",), ">=3.12", ("web",)),
            self.custom_wheel("0.18.0", ("known-package>=1",), ">=3.11", ("cli",)),
            self.custom_wheel("0.18.0", ("known-package>=1",), ">=3.11", ("web",), ("cp313-cp313-linux_x86_64",)),
        ):
            with self.assertRaisesRegex(update_script.UpdateError, "metadata differs"):
                update_script.hermes_custom_wheel_metadata(wheel, "0.18.0", expected)

    def test_custom_hermes_rejects_oversize_wheel_and_metadata_entries(self) -> None:
        with self.assertRaisesRegex(update_script.UpdateError, "exceeds"):
            update_script.hermes_wheel_metadata(b"x" * (update_script.HERMES_MAX_WHEEL_BYTES + 1), "0.18.0", "custom")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("hermes_agent-0.18.0.dist-info/METADATA", b"x" * (update_script.HERMES_MAX_METADATA_ENTRY_BYTES + 1))
            archive.writestr("hermes_agent-0.18.0.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
        with self.assertRaisesRegex(update_script.UpdateError, "metadata entry exceeds"):
            update_script.hermes_wheel_metadata(output.getvalue(), "0.18.0", "custom")

    def test_custom_hermes_rejects_symlinked_artifact_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "values" / "artifacts" / "hermes").mkdir(parents=True)
            with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path.name == "hermes"):
                with self.assertRaisesRegex(update_script.UpdateError, "not symlinks"):
                    update_script.hermes_custom_artifact_dir(root, "homelab-v0.18.0.1", "a" * 64)  # public-safety: allow-ip

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

#!/usr/bin/env python3
"""Update pinned tool and service versions after a release-age hold period."""
from __future__ import annotations

import argparse
import base64
import email.parser
import io
import inspect
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

DEFAULT_MIN_AGE_HOURS = 48
OCI_MIN_AGE_HOURS = 168
USER_AGENT = "homelab-infra-update/1.0"
OCI_REFERENCE_RE = re.compile(r"^(docker\.io)/([a-z0-9][a-z0-9._/-]*):([^@\s]+)@sha256:([0-9a-f]{64})$")
OCI_INDEX_MEDIA_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
OCI_MANIFEST_ACCEPT = ", ".join((*OCI_INDEX_MEDIA_TYPES, "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"))
OCI_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HERMES_LOCK_PACKAGE_COUNT = 79
HERMES_LOCK_REQUIREMENT_RE = re.compile(
    r"(?m)^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==[^ \t\\]+"
    r"(?: \\| --hash=sha256:[0-9a-f]{64}(?:\s+#.*)?)$"
)
HERMES_CUSTOM_ARTIFACT_DIR = Path("values/artifacts/hermes")
HERMES_MAX_WHEEL_BYTES = 128 * 1024 * 1024
HERMES_MAX_MANIFEST_BYTES = 1024 * 1024
HERMES_MAX_METADATA_ENTRY_BYTES = 2 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    published_at: datetime
    url: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Target:
    name: str
    path: Path
    pattern: str
    replacement: str
    release_url: str
    strip_prefix: str = "v"
    checksum_pattern: str | None = None
    checksum_replacement: str | None = None
    checksum_asset_template: str | None = None
    checksum_file_template: str | None = None
    extra_checksums: tuple[tuple[str, str, str], ...] = ()
    extra_checksum_asset_templates: tuple[str, ...] = ()
    managed_default_version: str | None = None
    managed_default_checksums: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdateResult:
    name: str
    path: Path
    current: str | None
    latest: str | None
    status: str
    detail: str


@dataclass(frozen=True)
class OciResponse:
    body: bytes
    headers: dict[str, str]


@dataclass(frozen=True)
class OciTarget:
    name: str
    path: Path
    pattern: str
    replacement: str
    repository: str
    tag_pattern: str
    managed_default: str
    group: str


@dataclass(frozen=True)
class DiscoveryTarget:
    name: str
    path: Path
    version_pattern: str
    version_replacement: str
    checksum_pattern: str
    checksum_replacement: str
    artifact_path_pattern: str
    release_url: str
    checksum_url_template: str
    tag_ref_url_template: str
    managed_version: str
    managed_checksum: str
    managed_artifact_path: str


@dataclass(frozen=True)
class HermesDiscoveryTarget:
    name: str
    path: Path
    release_url: str
    tag_ref_url_template: str
    managed_version: str
    managed_tag: str
    managed_commit: str
    managed_wheel_sha256: str


@dataclass(frozen=True)
class TagPinTarget:
    name: str
    path: Path
    pattern: str
    replacement: str
    tags_url: str
    commit_url_template: str
    managed_version: str


@dataclass(frozen=True)
class GoToolchainTarget:
    name: str
    path: Path
    releases_url: str
    commit_url_template: str
    managed_version: str
    managed_sha256_amd64: str
    managed_sha256_arm64: str


OCI_TARGETS = (
    OciTarget("Infisical image", Path("values/ansible/inventory/local.yml"), r"(?m)^(\s*infisical_container_image:\s*)(\S+)\s*$", r"\g<1>{reference}", "infisical/infisical", r"v0\.161\.\d+", "docker.io/infisical/infisical:v0.161.11@sha256:efe2d4fe5f37fb250ce5956ecc4734cc9ab1b50629d97cf7793d54200a18642b", "infisical"),
    OciTarget("PostgreSQL image", Path("values/ansible/inventory/local.yml"), r"(?m)^(\s*infisical_postgres_image:\s*)(\S+)\s*$", r"\g<1>{reference}", "library/postgres", r"16\.\d+-alpine[\w.-]*", "docker.io/library/postgres:16.14-alpine3.22@sha256:786dab398303b8ce7cb76b407bb21ef2e4dfbbbd4c6abcf3d29b3130467ffdbc", "infisical"),
    OciTarget("Redis image", Path("values/ansible/inventory/local.yml"), r"(?m)^(\s*infisical_redis_image:\s*)(\S+)\s*$", r"\g<1>{reference}", "library/redis", r"7\.4\.\d+-alpine", "docker.io/library/redis:7.4.9-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99", "infisical"),
    OciTarget("SearXNG image", Path("values/terraform.tfvars"), r'(?m)^(\s*searxng_container_image\s*=\s*")([^"\s]+)("\s*)$', r"\g<1>{reference}\g<3>", "searxng/searxng", r"2026\.7\.2-[0-9a-f]+", "docker.io/searxng/searxng:2026.7.2-67973783d@sha256:33aa33278be6c0be379b95f7c91cd455c18141295291c2e5a396454761df7bbb", "searxng"),
    OciTarget("Tooling Debian image", Path("tools/Dockerfile"), r"(?m)^(FROM\s+)(\S+)\s*$", r"\g<1>{reference}", "library/debian", r"bookworm-\d{8}-slim", "docker.io/library/debian:bookworm-20260623-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df", "tools-debian"),
)

HERMES_DISCOVERY = HermesDiscoveryTarget(
    name="Hermes Agent PyPI wheel",
    path=Path("values/ansible/inventory/local.yml"),
    release_url="https://api.github.com/repos/NousResearch/hermes-agent/releases?per_page=100",
    tag_ref_url_template="https://api.github.com/repos/NousResearch/hermes-agent/git/ref/tags/{tag}",
    managed_version="0.18.0",
    managed_tag="v2026.7.1",
    managed_commit="7c1a029553d87c43ecff8a3821336bc95872213b",
    managed_wheel_sha256="bf75c02d59f7c464cd0d85026fb7ee2e6bb15f003beccab3442b572f1ae1fd37",
)

CADDY_CLOUDFLARE_TAG = TagPinTarget(
    name="Caddy Cloudflare module",
    path=Path("values/ansible/inventory/local.yml"),
    pattern=r'(?m)^(\s*caddy_build_cloudflare_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
    replacement=r"\g<1>{version}\g<3>",
    tags_url="https://api.github.com/repos/caddy-dns/cloudflare/tags?per_page=100",
    commit_url_template="https://api.github.com/repos/caddy-dns/cloudflare/commits/{commit}",
    managed_version="0.2.4",
)

CADDY_GO_TOOLCHAIN = GoToolchainTarget(
    name="Caddy Go toolchain",
    path=Path("values/ansible/inventory/local.yml"),
    releases_url="https://go.dev/dl/?mode=json",
    commit_url_template="https://api.github.com/repos/golang/go/commits/go{version}",
    managed_version="1.25.1",
    managed_sha256_amd64="7716a0d940a0f6ae8e1f3b3f4f36299dc53e31b16840dbd171254312c41ca12e",
    managed_sha256_arm64="65a3e34fb2126f55b34e1edfc709121660e1be2dee6bdf405fc399a63a95a87d",
)

TECHNITIUM_DISCOVERY = DiscoveryTarget(
    name="Technitium portable release",
    path=Path("values/ansible/inventory/local.yml"),
    version_pattern=r'(?m)^(\s*technitium_discovery_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
    version_replacement=r"\g<1>{version}\g<3>",
    checksum_pattern=r"(?m)^(\s*technitium_portable_sha256:\s*)([0-9a-f]+)\s*$",
    checksum_replacement=r"\g<1>{checksum}",
    artifact_path_pattern=r"(?m)^\s*technitium_artifact_path:\s*([^\s]+)\s*$",
    release_url="https://api.github.com/repos/TechnitiumSoftware/DnsServer/releases?per_page=100",
    checksum_url_template="https://download.technitium.com/dns/archive/{version}/DnsServerPortable.tar.gz.sha256",
    tag_ref_url_template="https://api.github.com/repos/TechnitiumSoftware/DnsServer/git/ref/tags/v{version}",
    managed_version="15.2.0",
    managed_checksum="2e39fb8d0718475790cc025e083a1bcfd837a5e79e4a1d0ed775881bd90287ef",
    managed_artifact_path="values/artifacts/technitium/",
)


TARGETS = (
    Target(
        name="Caddy",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*caddy_build_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/caddyserver/caddy/releases/latest",
        managed_default_version="2.11.4",
    ),
    Target(
        name="xcaddy",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*caddy_build_xcaddy_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/caddyserver/xcaddy/releases/latest",
        managed_default_version="0.4.6",
    ),
    Target(
        name="Tailscale",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*tailscale_client_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/tailscale/tailscale/releases/latest",
        managed_default_version="1.98.8",
    ),
    Target(
        name="OpenTofu",
        path=Path("tools/Dockerfile"),
        pattern=r"(?m)^(ARG OPENTOFU_VERSION=)([^\s]+)$",
        replacement=r"\g<1>{version}",
        release_url="https://api.github.com/repos/opentofu/opentofu/releases/latest",
        checksum_pattern=r"(?m)^(ARG OPENTOFU_LINUX_AMD64_SHA256=)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="tofu_{version}_SHA256SUMS",
        checksum_file_template="tofu_{version}_linux_amd64.zip",
    ),
    Target(
        name="TFLint",
        path=Path("tools/Dockerfile"),
        pattern=r"(?m)^(ARG TFLINT_VERSION=)([^\s]+)$",
        replacement=r"\g<1>{version}",
        release_url="https://api.github.com/repos/terraform-linters/tflint/releases/latest",
        checksum_pattern=r"(?m)^(ARG TFLINT_LINUX_AMD64_SHA256=)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="checksums.txt",
        checksum_file_template="tflint_linux_amd64.zip",
    ),
    Target(
        name="Forgejo",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*forgejo_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://codeberg.org/api/v1/repos/forgejo/forgejo/releases/latest",
        checksum_pattern=r"(?m)^(\s*forgejo_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="forgejo-{version}-linux-amd64.sha256",
        checksum_file_template="forgejo-{version}-linux-amd64",
        managed_default_version="12.0.4",
        managed_default_checksums=("59fb6129e0396dc3502be60950438a03d227bb5691ee08b02dd38794f3d25a2a",),
    ),
    Target(
        name="Forgejo runner",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*forgejo_runner_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://code.forgejo.org/api/v1/repos/forgejo/runner/releases/latest",
        checksum_pattern=r"(?m)^(\s*forgejo_runner_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="forgejo-runner-{version}-linux-amd64.sha256",
        checksum_file_template="forgejo-runner-{version}-linux-amd64",
        extra_checksums=((r"(?m)^(\s*forgejo_runner_sha256_arm64:\s*)([^\s]+)$", "forgejo-runner-{version}-linux-arm64", r"\g<1>{checksum}"),),
        extra_checksum_asset_templates=("forgejo-runner-{version}-linux-arm64.sha256",),
        managed_default_version="12.7.3",
        managed_default_checksums=(
            "706f718bdf63baa345a1794924eec089be80df9bc38f02cefdc9a492f7c86b83",
            "be77c54925aed80b0967dcdfe89aa8c9310fddefacbe16ca05ed22fe2bfd659c",
        ),
    ),
    Target(
        name="Docker Compose plugin",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*forgejo_runner_compose_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/docker/compose/releases/latest",
        checksum_pattern=r"(?m)^(\s*forgejo_runner_compose_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="checksums.txt",
        checksum_file_template="docker-compose-linux-x86_64",
        extra_checksums=((r"(?m)^(\s*forgejo_runner_compose_sha256_arm64:\s*)([^\s]+)$", "docker-compose-linux-aarch64", r"\g<1>{checksum}"),),
        managed_default_version="5.3.0",
        managed_default_checksums=(
            "fffb010206c952ee5e45d0cd05dc88d3ca063c4634d40eaad6b72677c4c7bbf0",
            "ba0d9f5ce70086b3830448ce2f8a6405513c996065fe45d2f7c144a1f0d99398",
        ),
    ),
    Target(
        name="Hermes Docker Compose plugin",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*hermes_compose_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/docker/compose/releases/latest",
        checksum_pattern=r"(?m)^(\s*hermes_compose_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="checksums.txt",
        checksum_file_template="docker-compose-linux-x86_64",
        extra_checksums=((r"(?m)^(\s*hermes_compose_sha256_arm64:\s*)([^\s]+)$", "docker-compose-linux-aarch64", r"\g<1>{checksum}"),),
        managed_default_version="5.3.0",
        managed_default_checksums=(
            "fffb010206c952ee5e45d0cd05dc88d3ca063c4634d40eaad6b72677c4c7bbf0",
            "ba0d9f5ce70086b3830448ce2f8a6405513c996065fe45d2f7c144a1f0d99398",
        ),
    ),
    Target(
        name="Infisical Docker Compose plugin",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*infisical_compose_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/docker/compose/releases/latest",
        checksum_pattern=r"(?m)^(\s*infisical_compose_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="checksums.txt",
        checksum_file_template="docker-compose-linux-x86_64",
        extra_checksums=((r"(?m)^(\s*infisical_compose_sha256_arm64:\s*)([^\s]+)$", "docker-compose-linux-aarch64", r"\g<1>{checksum}"),),
        managed_default_version="5.3.0",
        managed_default_checksums=(
            "fffb010206c952ee5e45d0cd05dc88d3ca063c4634d40eaad6b72677c4c7bbf0",
            "ba0d9f5ce70086b3830448ce2f8a6405513c996065fe45d2f7c144a1f0d99398",
        ),
    ),
    Target(
        name="just",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*forgejo_runner_just_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/casey/just/releases/latest",
        checksum_pattern=r"(?m)^(\s*forgejo_runner_just_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="SHA256SUMS",
        checksum_file_template="just-{version}-x86_64-unknown-linux-musl.tar.gz",
        extra_checksums=((r"(?m)^(\s*forgejo_runner_just_sha256_arm64:\s*)([^\s]+)$", "just-{version}-aarch64-unknown-linux-musl.tar.gz", r"\g<1>{checksum}"),),
        managed_default_version="1.55.1",
        managed_default_checksums=(
            "b0ef600f0df20d5ae91ae931627c499fc52b477ffe5f5ea7b7b3ec616b16c778",
            "b0ee814c9656427408e339893541e30d9027828686839499b2a2a34dd61ad173",
        ),
    ),
    Target(
        name="Hermes just",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*hermes_just_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/casey/just/releases/latest",
        checksum_pattern=r"(?m)^(\s*hermes_just_sha256_amd64:\s*)([^\s]+)$",
        checksum_replacement=r"\g<1>{checksum}",
        checksum_asset_template="SHA256SUMS",
        checksum_file_template="just-{version}-x86_64-unknown-linux-musl.tar.gz",
        extra_checksums=((r"(?m)^(\s*hermes_just_sha256_arm64:\s*)([^\s]+)$", "just-{version}-aarch64-unknown-linux-musl.tar.gz", r"\g<1>{checksum}"),),
        managed_default_version="1.55.1",
        managed_default_checksums=(
            "b0ef600f0df20d5ae91ae931627c499fc52b477ffe5f5ea7b7b3ec616b16c778",
            "b0ee814c9656427408e339893541e30d9027828686839499b2a2a34dd61ad173",
        ),
    ),
)


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_version(tag: str, strip_prefix: str) -> str:
    if strip_prefix and tag.startswith(strip_prefix):
        return tag[len(strip_prefix) :]
    return tag


def fetch_url(
    url: str,
    opener: Callable[..., bytes] | None = None,
    max_bytes: int | None = None,
) -> bytes:
    if max_bytes is not None and max_bytes < 0:
        raise ValueError("max_bytes must not be negative")
    if opener is not None:
        try:
            inspect.signature(opener).bind(url, max_bytes)
        except TypeError:
            data = opener(url)
        else:
            data = opener(url, max_bytes)
        if max_bytes is not None and len(data) > max_bytes:
            raise UpdateError(f"response from {url} exceeds {max_bytes} bytes")
        return data
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise UpdateError(f"response from {url} has an invalid Content-Length") from error
                if declared_length < 0 or (max_bytes is not None and declared_length > max_bytes):
                    raise UpdateError(f"response from {url} exceeds {max_bytes} bytes")
            data = response.read() if max_bytes is None else response.read(max_bytes + 1)
            if max_bytes is not None and len(data) > max_bytes:
                raise UpdateError(f"response from {url} exceeds {max_bytes} bytes")
            return data
    except urllib.error.URLError as error:
        raise UpdateError(f"failed to fetch {url}: {error}") from error


def fetch_release(url: str, opener: Callable[[str], bytes] | None = None) -> dict[str, object]:
    raw = fetch_url(url, opener)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid JSON from {url}: {error}") from error
    if not isinstance(data, dict):
        raise UpdateError(f"unexpected release payload from {url}")
    return data


def first_string(payload: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def release_from_payload(target: Target, payload: dict[str, object]) -> Release:
    tag = first_string(payload, ("tag_name", "name"))
    published = first_string(payload, ("published_at", "created_at"))
    url = first_string(payload, ("html_url", "url")) or target.release_url
    if tag is None:
        raise UpdateError(f"{target.name}: release payload does not include tag_name")
    if published is None:
        raise UpdateError(f"{target.name}: release payload does not include published_at")
    return Release(
        version=normalize_version(tag, target.strip_prefix),
        published_at=parse_timestamp(published),
        url=url,
        payload=payload,
    )


def read_current(target: Target, root: Path) -> tuple[str | None, str | None]:
    path = root / target.path
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    match = re.search(target.pattern, text)
    if not match:
        return None, text
    return match.group(2), text


def is_managed_default(target: Target, current: str, text: str) -> bool:
    """Return whether every version/checksum field retains its scaffold default.

    Private inventory pins are operator-owned once any field in their paired pin
    set differs from the managed default.  This prevents `just update` from
    combining an upstream version with a checksum chosen for a custom pin.
    """
    if target.managed_default_version is None:
        return True
    if current != target.managed_default_version:
        return False
    patterns = tuple(
        pattern
        for pattern in (target.checksum_pattern,)
        if pattern is not None
    ) + tuple(pattern for pattern, _file_name, _replacement in target.extra_checksums)
    if len(patterns) != len(target.managed_default_checksums):
        raise UpdateError(f"{target.name}: incomplete managed-default checksum policy")
    return all(
        pattern is not None
        and (match := re.search(pattern, text)) is not None
        and match.group(2) == expected
        for pattern, expected in zip(patterns, target.managed_default_checksums)
    )


def replace_once(pattern: str, replacement: str, text: str, target: Target) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise UpdateError(
            f"{target.name}: expected one match in {target.path}, found {count}"
        )
    return updated


def release_asset_url(release: Release, asset_name: str) -> str:
    assets = release.payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError(f"release payload for {release.version} does not include assets")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != asset_name:
            continue
        url = asset.get("browser_download_url")
        if isinstance(url, str) and url:
            return url
    raise UpdateError(f"release {release.version} does not include asset {asset_name}")


def release_identity(release: Release) -> tuple[str, datetime, str, tuple[tuple[str, str, int | None], ...]]:
    assets = release.payload.get("assets", [])
    if not isinstance(assets, list):
        raise UpdateError(f"release payload for {release.version} has invalid assets")
    identity: list[tuple[str, str, int | None]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise UpdateError(f"release payload for {release.version} has invalid asset")
        name = asset.get("name")
        url = asset.get("browser_download_url")
        asset_id = asset.get("id")
        if not isinstance(name, str) or not name or not isinstance(url, str) or not url:
            raise UpdateError(f"release payload for {release.version} has unidentified asset")
        if asset_id is not None and not isinstance(asset_id, int):
            raise UpdateError(f"release payload for {release.version} has invalid asset id")
        identity.append((name, url, asset_id))
    return release.version, release.published_at, release.url, tuple(sorted(identity))


def checksum_from_manifest(checksum_text: str, asset_name: str, file_name: str) -> str:
    for line in checksum_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].lstrip("*") == file_name:
            checksum = fields[0].lower()
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise UpdateError(f"{asset_name} has an invalid SHA-256 for {file_name}")
            return checksum
    raise UpdateError(f"{asset_name} does not include checksum for {file_name}")


def checksums_for_release(
    target: Target,
    release: Release,
    opener: Callable[[str], bytes] | None,
) -> tuple[str | None, tuple[str, ...]]:
    if not target.checksum_asset_template or not target.checksum_file_template:
        return None, ()
    asset_name = target.checksum_asset_template.format(version=release.version)
    checksum_url = release_asset_url(release, asset_name)
    checksum_text = fetch_url(checksum_url, opener).decode("utf-8")
    primary = checksum_from_manifest(
        checksum_text, asset_name, target.checksum_file_template.format(version=release.version)
    )
    if target.extra_checksum_asset_templates and len(
        target.extra_checksum_asset_templates
    ) != len(target.extra_checksums):
        raise UpdateError(f"{target.name}: incomplete extra checksum asset policy")
    extra = []
    for index, (_pattern, file_template, _replacement) in enumerate(target.extra_checksums):
        extra_asset_name = (
            target.extra_checksum_asset_templates[index].format(version=release.version)
            if target.extra_checksum_asset_templates
            else asset_name
        )
        extra_checksum_text = (
            fetch_url(release_asset_url(release, extra_asset_name), opener).decode("utf-8")
            if extra_asset_name != asset_name
            else checksum_text
        )
        extra.append(
            checksum_from_manifest(
                extra_checksum_text,
                extra_asset_name,
                file_template.format(version=release.version),
            )
        )
    return primary, tuple(extra)


def replace_version(target: Target, text: str, release: Release, checksum: str | None, extra_checksums: tuple[str, ...] = ()) -> str:
    updated = replace_once(
        target.pattern,
        target.replacement.format(version=release.version),
        text,
        target,
    )
    if target.checksum_pattern and target.checksum_replacement:
        if checksum is None:
            raise UpdateError(f"{target.name}: checksum is required")
        updated = replace_once(
            target.checksum_pattern,
            target.checksum_replacement.format(checksum=checksum),
            updated,
            target,
        )
    for (pattern, _file_name, replacement), extra_checksum in zip(target.extra_checksums, extra_checksums):
        updated = replace_once(pattern, replacement.format(checksum=extra_checksum), updated, target)
    return updated


def process_target(
    target: Target,
    root: Path,
    now: datetime,
    min_age: timedelta,
    opener: Callable[[str], bytes] | None = None,
) -> UpdateResult:
    current, text = read_current(target, root)
    if text is None:
        return UpdateResult(target.name, target.path, None, None, "skip", "file not present")
    if current is None:
        return UpdateResult(
            target.name,
            target.path,
            None,
            None,
            "skip",
            "version pin not present",
        )
    if not is_managed_default(target, current, text):
        return UpdateResult(
            target.name,
            target.path,
            current,
            None,
            "skip",
            "custom operator pin",
        )

    release = release_from_payload(target, fetch_release(target.release_url, opener))
    age = now - release.published_at
    if release.version == current:
        return UpdateResult(
            target.name,
            target.path,
            current,
            release.version,
            "current",
            f"already at latest ({release.url})",
        )
    if age < min_age:
        remaining = min_age - age
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        return UpdateResult(
            target.name,
            target.path,
            current,
            release.version,
            "hold",
            f"published {release.published_at.isoformat()}; "
            f"wait {hours}h {minutes}m more ({release.url})",
        )

    checksum, extra_checksums = checksums_for_release(target, release, opener)
    confirmed_release = release_from_payload(
        target, fetch_release(target.release_url, opener)
    )
    confirmed_checksum, confirmed_extra_checksums = checksums_for_release(
        target, confirmed_release, opener
    )
    if (
        release_identity(confirmed_release) != release_identity(release)
        or confirmed_checksum != checksum
        or confirmed_extra_checksums != extra_checksums
    ):
        raise UpdateError(f"{target.name}: release changed during re-resolution")
    path = root / target.path
    if path.read_text(encoding="utf-8") != text:
        raise UpdateError(f"{target.name}: pin file changed during resolution")
    updated = replace_version(
        target, text, confirmed_release, confirmed_checksum, confirmed_extra_checksums
    )
    path.write_text(updated, encoding="utf-8", newline="\n")
    return UpdateResult(
        target.name,
        target.path,
        current,
        release.version,
        "updated",
        f"release age {age}; {release.url}",
    )


def oci_json(response: OciResponse, context: str) -> dict[str, object]:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid OCI JSON from {context}: {error}") from error
    if not isinstance(value, dict):
        raise UpdateError(f"unexpected OCI payload from {context}")
    return value


def response_header(response: OciResponse, name: str) -> str:
    return next(
        (value for key, value in response.headers.items() if key.lower() == name.lower()),
        "",
    )


def oci_digest(response: OciResponse, context: str, expected: str | None = None) -> str:
    header = response_header(response, "Docker-Content-Digest")
    computed = f"sha256:{sha256(response.body).hexdigest()}"
    if header:
        if not OCI_DIGEST_RE.fullmatch(header) or header != computed:
            raise UpdateError(f"{context}: registry digest header does not match body")
        digest = header
    elif expected is not None and computed == expected:
        digest = computed
    else:
        raise UpdateError(f"{context}: registry digest header is missing")
    if expected is not None and digest != expected:
        raise UpdateError(f"{context}: registry digest changed during resolution")
    return digest


def validate_oci_reference(reference: str, repository: str) -> None:
    match = OCI_REFERENCE_RE.fullmatch(reference)
    if match is None or match.group(2) != repository:
        raise UpdateError(f"invalid OCI reference for {repository}: {reference}")


def natural_tag_key(tag: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"(\d+)", tag)
        if part
    )


def oci_tags(
    base: str, target: OciTarget, fetch: Callable[[str, str], OciResponse]
) -> list[str]:
    url = f"{base}/tags/list?n=1000"
    tags: list[str] = []
    seen_urls: set[str] = set()
    while url:
        if url in seen_urls:
            raise UpdateError(f"{target.name}: registry tag pagination loop")
        seen_urls.add(url)
        response = fetch(url, "application/json")
        page = oci_json(response, target.name).get("tags")
        if not isinstance(page, list):
            raise UpdateError(f"{target.name}: registry did not return tags")
        tags.extend(tag for tag in page if isinstance(tag, str))
        link = response_header(response, "Link")
        if not link:
            break
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="next"\s*', link)
        if match is None:
            raise UpdateError(f"{target.name}: invalid registry pagination link")
        next_url = urllib.parse.urljoin(url, match.group(1))
        parsed = urllib.parse.urlparse(next_url)
        expected = urllib.parse.urlparse(base)
        if parsed.scheme != "https" or parsed.netloc != expected.netloc or not parsed.path.startswith(expected.path + "/tags/list"):
            raise UpdateError(f"{target.name}: unsafe registry pagination link")
        url = next_url
    return tags


def resolve_oci_tag(
    target: OciTarget,
    tag: str,
    fetch: Callable[[str, str], OciResponse],
) -> tuple[str, datetime]:
    base = f"https://registry-1.docker.io/v2/{target.repository}"
    index_response = fetch(f"{base}/manifests/{tag}", OCI_MANIFEST_ACCEPT)
    index_digest = oci_digest(index_response, f"{target.name} index")
    index = oci_json(index_response, target.name)
    if index.get("mediaType") not in OCI_INDEX_MEDIA_TYPES:
        raise UpdateError(f"{target.name}: tag must resolve to a multi-arch index")
    manifests = index.get("manifests")
    if not isinstance(manifests, list):
        raise UpdateError(f"{target.name}: index has no manifests")
    descriptor = next(
        (
            item
            for item in manifests
            if isinstance(item, dict)
            and isinstance(item.get("platform"), dict)
            and item["platform"].get("os") == "linux"
            and item["platform"].get("architecture") == "amd64"
        ),
        None,
    )
    if descriptor is None or not isinstance(descriptor.get("digest"), str):
        raise UpdateError(f"{target.name}: index has no linux/amd64 manifest")
    manifest_digest = descriptor["digest"]
    if not OCI_DIGEST_RE.fullmatch(manifest_digest):
        raise UpdateError(f"{target.name}: linux/amd64 manifest has invalid digest")
    manifest_response = fetch(f"{base}/manifests/{manifest_digest}", OCI_MANIFEST_ACCEPT)
    oci_digest(manifest_response, f"{target.name} linux/amd64 manifest", manifest_digest)
    manifest = oci_json(manifest_response, target.name)
    config = manifest.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("digest"), str):
        raise UpdateError(f"{target.name}: linux/amd64 manifest has no config")
    if not OCI_DIGEST_RE.fullmatch(config["digest"]):
        raise UpdateError(f"{target.name}: linux/amd64 config has invalid digest")
    config_response = fetch(f"{base}/blobs/{config['digest']}", "application/vnd.oci.image.config.v1+json")
    oci_digest(config_response, f"{target.name} config", config["digest"])
    created = oci_json(config_response, target.name).get("created")
    if not isinstance(created, str):
        raise UpdateError(f"{target.name}: linux/amd64 config has no creation time")
    reference = f"docker.io/{target.repository}:{tag}@{index_digest}"
    validate_oci_reference(reference, target.repository)
    return reference, parse_timestamp(created)


def resolve_oci_reference(
    target: OciTarget,
    fetch: Callable[[str, str], OciResponse],
) -> tuple[str, datetime]:
    """Resolve the newest bounded Docker Hub tag to a verified linux/amd64 index."""
    base = f"https://registry-1.docker.io/v2/{target.repository}"
    candidates = {
        tag
        for tag in oci_tags(base, target, fetch)
        if re.fullmatch(target.tag_pattern, tag)
    }
    if not candidates:
        raise UpdateError(f"{target.name}: no tag matches bounded series {target.tag_pattern}")
    tag = max(candidates, key=natural_tag_key)
    return resolve_oci_tag(target, tag, fetch)


def fetch_oci_registry(url: str, accept: str) -> OciResponse:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return OciResponse(response.read(), dict(response.headers.items()))
    except urllib.error.HTTPError as error:
        challenge = error.headers.get("WWW-Authenticate", "")
        match = re.match(r'Bearer realm="([^"]+)",service="([^"]+)",scope="([^"]+)"', challenge)
        if not match:
            raise UpdateError(f"failed to fetch OCI registry {url}: {error}") from error
        realm, service, scope = match.groups()
        token_url = f"{realm}?service={urllib.parse.quote(service)}&scope={urllib.parse.quote(scope)}"
        try:
            with urllib.request.urlopen(token_url, timeout=30) as token_response:
                token = oci_json(OciResponse(token_response.read(), dict(token_response.headers.items())), token_url).get("token")
            if not isinstance(token, str) or not token:
                raise UpdateError(f"OCI token response for {url} has no token")
            authenticated = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(authenticated, timeout=30) as response:
                return OciResponse(response.read(), dict(response.headers.items()))
        except urllib.error.URLError as nested:
            raise UpdateError(f"failed to authenticate OCI registry {url}: {nested}") from nested


def process_oci_group(
    group: str,
    root: Path,
    now: datetime,
    fetch: Callable[[str, str], OciResponse],
) -> list[UpdateResult]:
    members = [target for target in OCI_TARGETS if target.group == group]
    originals: dict[Path, str] = {}
    present: list[tuple[OciTarget, str]] = []
    for target in members:
        path = root / target.path
        if not path.exists():
            continue
        text = originals.setdefault(target.path, path.read_text(encoding="utf-8"))
        match = re.search(target.pattern, text)
        if match is not None:
            present.append((target, match.group(2)))

    if not present:
        return [
            UpdateResult(target.name, target.path, None, None, "skip", "OCI pin not present")
            for target in members
        ]
    if len(present) != len(members):
        return [
            UpdateResult(target.name, target.path, None, None, "skip", f"incomplete operator pin group ({group})")
            for target in members
        ]
    if any(current != target.managed_default for target, current in present):
        return [
            UpdateResult(target.name, target.path, current, None, "skip", f"custom operator pin group ({group})")
            for target, current in present
        ]

    resolutions = {
        target: resolve_oci_reference(target, fetch) for target, _current in present
    }
    held = {
        target
        for target, current in present
        if resolutions[target][0] != current
        and now - resolutions[target][1] < timedelta(hours=OCI_MIN_AGE_HOURS)
    }
    if held:
        held_names = ", ".join(sorted(target.name for target in held))
        return [
            UpdateResult(
                target.name,
                target.path,
                current,
                resolutions[target][0],
                "hold" if target in held else "current",
                f"pin group held by {held_names}; strict {OCI_MIN_AGE_HOURS}h OCI hold",
            )
            for target, current in present
        ]

    changed = [
        (target, current)
        for target, current in present
        if resolutions[target][0] != current
    ]
    if not changed:
        return [
            UpdateResult(target.name, target.path, current, current, "current", "verified OCI index is current")
            for target, current in present
        ]

    confirmed = {
        target: resolve_oci_reference(target, fetch) for target, _current in present
    }
    if confirmed != resolutions:
        raise UpdateError(f"{group}: OCI tag changed during re-resolution")
    for relative_path, original in originals.items():
        if (root / relative_path).read_text(encoding="utf-8") != original:
            raise UpdateError(f"{group}: pin file changed during resolution")

    updated_files = dict(originals)
    for target, _current in changed:
        updated_files[target.path] = replace_once(
            target.pattern,
            target.replacement.format(reference=confirmed[target][0]),
            updated_files[target.path],
            Target(target.name, target.path, target.pattern, target.replacement, ""),
        )
    for relative_path, updated in updated_files.items():
        (root / relative_path).write_text(updated, encoding="utf-8", newline="\n")

    changed_targets = {target for target, _current in changed}
    return [
        UpdateResult(
            target.name,
            target.path,
            current,
            confirmed[target][0],
            "updated" if target in changed_targets else "current",
            f"verified linux/amd64 OCI index; strict {OCI_MIN_AGE_HOURS}h hold",
        )
        for target, current in present
    ]


def technitium_releases(
    target: DiscoveryTarget,
    now: datetime,
    opener: Callable[[str], bytes] | None,
) -> tuple[Release, Release | None]:
    raw = fetch_url(target.release_url, opener)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid JSON from {target.release_url}: {error}") from error
    if not isinstance(payload, list):
        raise UpdateError(f"unexpected release list from {target.release_url}")

    release_target = Target(
        target.name,
        target.path,
        target.version_pattern,
        target.version_replacement,
        target.release_url,
    )
    stable: list[Release] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft") is not False or item.get("prerelease") is not False:
            continue
        published = item.get("published_at")
        if not isinstance(published, str) or not published:
            continue
        stable.append(release_from_payload(release_target, item))
    if not stable:
        raise UpdateError(f"{target.name}: no stable published releases found")

    stable.sort(key=lambda release: release.published_at, reverse=True)
    eligible = [
        release
        for release in stable
        if now - release.published_at >= timedelta(hours=OCI_MIN_AGE_HOURS)
    ]
    if not eligible:
        raise UpdateError(
            f"{target.name}: no release satisfies the strict {OCI_MIN_AGE_HOURS}h hold"
        )
    held = next((release for release in stable if release not in eligible), None)
    return eligible[0], held


def technitium_checksum(
    target: DiscoveryTarget,
    version: str,
    opener: Callable[[str], bytes] | None,
) -> str:
    checksum_url = target.checksum_url_template.format(version=version)
    checksum = fetch_url(checksum_url, opener).decode("ascii").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise UpdateError(f"{target.name}: invalid published SHA-256 for {version}")
    return checksum


def technitium_provenance(
    target: DiscoveryTarget,
    release: Release,
    opener: Callable[[str], bytes] | None,
) -> tuple[int, str]:
    release_id = release.payload.get("id")
    if not isinstance(release_id, int):
        raise UpdateError(f"{target.name}: release {release.version} has no numeric id")
    ref_url = target.tag_ref_url_template.format(version=release.version)
    ref = fetch_release(ref_url, opener)
    ref_object = ref.get("object")
    if not isinstance(ref_object, dict):
        raise UpdateError(f"{target.name}: tag {release.version} has no git object")
    object_type = ref_object.get("type")
    commit = ref_object.get("sha")
    if object_type == "tag":
        object_url = ref_object.get("url")
        if not isinstance(object_url, str):
            raise UpdateError(f"{target.name}: annotated tag {release.version} has no object URL")
        tag_object = fetch_release(object_url, opener).get("object")
        if not isinstance(tag_object, dict) or tag_object.get("type") != "commit":
            raise UpdateError(f"{target.name}: annotated tag {release.version} does not resolve to a commit")
        commit = tag_object.get("sha")
    elif object_type != "commit":
        raise UpdateError(f"{target.name}: tag {release.version} does not resolve to a commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError(f"{target.name}: tag {release.version} has an invalid commit")
    return release_id, commit


def process_discovery_target(
    target: DiscoveryTarget,
    root: Path,
    now: datetime,
    opener: Callable[[str], bytes] | None = None,
) -> UpdateResult:
    path = root / target.path
    if not path.exists():
        return UpdateResult(target.name, target.path, None, None, "skip", "file not present")
    text = path.read_text(encoding="utf-8")
    version_match = re.search(target.version_pattern, text)
    checksum_match = re.search(target.checksum_pattern, text)
    artifact_path_match = re.search(target.artifact_path_pattern, text)
    if not version_match or not checksum_match or not artifact_path_match:
        return UpdateResult(target.name, target.path, None, None, "skip", "incomplete operator pin group (technitium)")
    current = version_match.group(2)
    if (
        current != target.managed_version
        or checksum_match.group(2) != target.managed_checksum
        or artifact_path_match.group(1).strip("\"'") != target.managed_artifact_path
    ):
        return UpdateResult(target.name, target.path, current, None, "skip", "custom operator pin group (technitium)")

    release_target = Target(
        target.name,
        target.path,
        target.version_pattern,
        target.version_replacement,
        target.release_url,
    )
    release, held_release = technitium_releases(target, now, opener)
    if release.version == current:
        held_detail = (
            f"; {held_release.version} remains inside the strict {OCI_MIN_AGE_HOURS}h hold"
            if held_release is not None
            else ""
        )
        return UpdateResult(
            target.name,
            target.path,
            current,
            current,
            "current",
            f"newest eligible managed release is current{held_detail}",
        )

    checksum = technitium_checksum(target, release.version, opener)
    provenance = technitium_provenance(target, release, opener)
    confirmed_release, _confirmed_held = technitium_releases(target, now, opener)
    confirmed_checksum = technitium_checksum(target, confirmed_release.version, opener)
    confirmed_provenance = technitium_provenance(target, confirmed_release, opener)
    if (
        release_identity(confirmed_release) != release_identity(release)
        or confirmed_checksum != checksum
        or confirmed_provenance != provenance
    ):
        raise UpdateError(f"{target.name}: release or portable artifact changed during re-resolution")
    if path.read_text(encoding="utf-8") != text:
        raise UpdateError(f"{target.name}: pin file changed during resolution")
    updated = replace_once(
        target.version_pattern,
        target.version_replacement.format(version=confirmed_release.version),
        text,
        release_target,
    )
    updated = replace_once(
        target.checksum_pattern,
        target.checksum_replacement.format(checksum=confirmed_checksum),
        updated,
        release_target,
    )
    path.write_text(updated, encoding="utf-8", newline="\n")
    return UpdateResult(
        target.name,
        target.path,
        current,
        confirmed_release.version,
        "updated",
        f"release id {provenance[0]}, published {confirmed_release.published_at.isoformat()}, "
        f"tag commit {provenance[1]}; strict {OCI_MIN_AGE_HOURS}h hold",
    )


def hermes_release_version(release: Release) -> str:
    assets = release.payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError(f"Hermes release {release.version} has no assets")
    versions = {
        match.group(1)
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and (match := re.fullmatch(
            r"hermes_agent-([0-9]+[.][0-9]+[.][0-9]+)-py3-none-any[.]whl[.]sigstore[.]json",
            asset["name"],
        ))
    }
    if len(versions) != 1:
        raise UpdateError(
            f"Hermes release {release.version} must identify exactly one wheel provenance asset"
        )
    return versions.pop()


def hermes_releases(
    target: HermesDiscoveryTarget,
    now: datetime,
    opener: Callable[[str], bytes] | None,
) -> tuple[Release, Release | None]:
    raw = fetch_url(target.release_url, opener)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid JSON from {target.release_url}: {error}") from error
    if not isinstance(payload, list):
        raise UpdateError(f"unexpected release list from {target.release_url}")
    release_target = Target(target.name, target.path, "", "", target.release_url, strip_prefix="")
    stable = [
        release_from_payload(release_target, item)
        for item in payload
        if isinstance(item, dict)
        and item.get("draft") is False
        and item.get("prerelease") is False
        and isinstance(item.get("published_at"), str)
    ]
    stable.sort(key=lambda release: release.published_at, reverse=True)
    eligible = [
        release
        for release in stable
        if now - release.published_at >= timedelta(hours=OCI_MIN_AGE_HOURS)
    ]
    if not eligible:
        raise UpdateError(
            f"{target.name}: no release satisfies the strict {OCI_MIN_AGE_HOURS}h hold"
        )
    held = next((release for release in stable if release not in eligible), None)
    return eligible[0], held


def hermes_pypi_artifact(
    version: str,
    opener: Callable[[str], bytes] | None,
) -> tuple[str, str, str]:
    filename = f"hermes_agent-{version}-py3-none-any.whl"
    metadata_url = f"https://pypi.org/pypi/hermes-agent/{version}/json"
    payload = fetch_release(metadata_url, opener)
    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise UpdateError(f"Hermes {version}: PyPI metadata has no artifacts")
    artifact = next(
        (
            item
            for item in urls
            if isinstance(item, dict)
            and item.get("filename") == filename
            and item.get("packagetype") == "bdist_wheel"
            and item.get("python_version") == "py3"
        ),
        None,
    )
    if artifact is None:
        raise UpdateError(f"Hermes {version}: official universal wheel is absent from PyPI")
    digests = artifact.get("digests")
    url = artifact.get("url")
    if (
        not isinstance(digests, dict)
        or not isinstance(digests.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", digests["sha256"])
        or not isinstance(url, str)
        or not url.startswith("https://files.pythonhosted.org/packages/")
        or not url.endswith("/" + filename)
    ):
        raise UpdateError(f"Hermes {version}: invalid official PyPI wheel metadata")
    return filename, digests["sha256"], url


def hermes_pypi_provenance(
    version: str,
    filename: str,
    checksum: str,
    opener: Callable[[str], bytes] | None,
) -> None:
    url = f"https://pypi.org/integrity/hermes-agent/{version}/{filename}/provenance"
    payload = fetch_release(url, opener)
    bundles = payload.get("attestation_bundles")
    if not isinstance(bundles, list):
        raise UpdateError(f"Hermes {version}: PyPI provenance has no attestation bundles")
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        publisher = bundle.get("publisher")
        attestations = bundle.get("attestations")
        if publisher != {
            "environment": "pypi",
            "kind": "GitHub",
            "repository": "NousResearch/hermes-agent",
            "workflow": "upload_to_pypi.yml",
        } or not isinstance(attestations, list):
            continue
        for attestation in attestations:
            try:
                statement = json.loads(
                    base64.b64decode(attestation["envelope"]["statement"], validate=True)
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            subjects = statement.get("subject") if isinstance(statement, dict) else None
            if isinstance(subjects, list) and any(
                isinstance(subject, dict)
                and subject.get("name") == filename
                and subject.get("digest") == {"sha256": checksum}
                for subject in subjects
            ):
                return
    raise UpdateError(
        f"Hermes {version}: PyPI provenance does not attest the expected repository, wheel, and SHA-256"
    )


def hermes_tag_commit(
    target: HermesDiscoveryTarget,
    release: Release,
    opener: Callable[[str], bytes] | None,
) -> str:
    ref = fetch_release(target.tag_ref_url_template.format(tag=release.version), opener)
    ref_object = ref.get("object")
    if not isinstance(ref_object, dict):
        raise UpdateError(f"{target.name}: tag {release.version} has no git object")
    object_type = ref_object.get("type")
    commit = ref_object.get("sha")
    if object_type == "tag":
        object_url = ref_object.get("url")
        if not isinstance(object_url, str):
            raise UpdateError(f"{target.name}: annotated tag {release.version} has no object URL")
        tag_object = fetch_release(object_url, opener).get("object")
        if not isinstance(tag_object, dict) or tag_object.get("type") != "commit":
            raise UpdateError(f"{target.name}: annotated tag does not resolve to a commit")
        commit = tag_object.get("sha")
    elif object_type != "commit":
        raise UpdateError(f"{target.name}: tag does not resolve to a commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise UpdateError(f"{target.name}: tag has an invalid commit")
    return commit


def validate_hermes_lock(root: Path, version: str, checksum: str | None) -> None:
    path = root / "infra/ansible/roles/hermes/files" / f"requirements-{version}.lock"
    if not path.exists():
        raise UpdateError(f"Hermes {version}: tracked transitive requirements lock is absent")
    text = path.read_text(encoding="utf-8")
    requirements = HERMES_LOCK_REQUIREMENT_RE.findall(text)
    if len(requirements) != HERMES_LOCK_PACKAGE_COUNT:
        raise UpdateError(
            f"Hermes {version}: tracked lock has {len(requirements)} requirements; "
            f"expected {HERMES_LOCK_PACKAGE_COUNT} for the approved dashboard and messaging extras"
        )
    blocks = re.split(r"(?m)(?=^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==)", text)
    requirement_blocks = [block for block in blocks if HERMES_LOCK_REQUIREMENT_RE.match(block)]
    if (
        "Debian 13 amd64, CPython 3.13" not in text
        or "--only-binary :all:" not in text
        or len(requirement_blocks) != len(requirements)
        or any(not re.search(r"--hash=sha256:[0-9a-f]{64}", block) for block in requirement_blocks)
        or re.search(r"(?m)^[^#\n]*(?:https?://|git\+|--find-links|--extra-index-url|--trusted-host)", text)
    ):
        raise UpdateError(f"Hermes {version}: tracked lock is not a complete official-PyPI wheel lock")
    has_requirement = any(
        line.startswith("hermes-agent[") and line.endswith(f"]=={version} \\")
        for line in text.splitlines()
    )
    if not has_requirement or (checksum is not None and f"--hash=sha256:{checksum}" not in text):
        raise UpdateError(f"Hermes {version}: tracked lock does not contain the official wheel pin")


def atomic_write_text(path: Path, text: str) -> None:
    """Durably replace a private pin file without exposing a partial pin group."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            os.chmod(temporary_path, stat.S_IMODE(path.stat().st_mode))
        else:
            os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    atomic_write_text(path, text)
    return True


def resolve_hermes_release(
    target: HermesDiscoveryTarget,
    release: Release,
    root: Path,
    opener: Callable[[str], bytes] | None,
) -> tuple[str, str, str]:
    version = hermes_release_version(release)
    filename, checksum, _url = hermes_pypi_artifact(version, opener)
    hermes_pypi_provenance(version, filename, checksum, opener)
    commit = hermes_tag_commit(target, release, opener)
    validate_hermes_lock(root, version, checksum)
    return version, commit, checksum


def hermes_inventory_value(text: str, key: str) -> str | None:
    matches = re.findall(rf"(?m)^\s*{re.escape(key)}:\s*[\"']?([^\s\"'#]+)[\"']?\s*$", text)
    if len(matches) > 1:
        raise UpdateError(f"Hermes: duplicate inventory field {key}")
    return matches[0] if matches else None


def hermes_custom_config(text: str) -> tuple[str, str] | None:
    source = hermes_inventory_value(text, "hermes_artifact_source") or "official_pypi"
    repository = hermes_inventory_value(text, "hermes_custom_repository")
    tag_prefix = hermes_inventory_value(text, "hermes_custom_tag_prefix")
    custom_fields = (
        "hermes_custom_repository",
        "hermes_custom_wheel_url",
        "hermes_custom_requirements_lock_path",
        "hermes_custom_dependencies_lock_path",
    )
    if source == "official_pypi":
        if any(hermes_inventory_value(text, key) is not None for key in custom_fields):
            raise UpdateError("Hermes: official_pypi source cannot include custom release fields")
        return None
    if source != "custom_github_release":
        raise UpdateError("Hermes: artifact source must be official_pypi or custom_github_release")
    if repository is None or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateError("Hermes: custom_github_release requires hermes_custom_repository owner/repo")
    if tag_prefix is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tag_prefix):
        raise UpdateError("Hermes: custom_github_release tag prefix is invalid")
    output = tuple(hermes_inventory_value(text, key) for key in custom_fields[1:])
    if any(value is not None for value in output) and any(value is None for value in output):
        raise UpdateError("Hermes: custom release pin group is incomplete")
    return repository, tag_prefix


def hermes_custom_release(
    repository: str, tag_prefix: str, now: datetime, opener: Callable[[str], bytes] | None
) -> tuple[Release, str]:
    url = f"https://api.github.com/repos/{repository}/releases?per_page=100"
    payload = fetch_json_value(url, opener)
    if not isinstance(payload, list):
        raise UpdateError("Hermes: custom GitHub releases payload is invalid")
    if len(payload) == 100:
        raise UpdateError("Hermes: custom GitHub release pagination is unsupported")
    candidates: list[tuple[Release, str]] = []
    pattern = re.compile(rf"^{re.escape(tag_prefix)}([0-9]+[.][0-9]+[.][0-9]+)[.]([1-9][0-9]*)$")
    release_target = Target("Hermes custom wheel", Path(), "", "", url, strip_prefix="")
    for item in payload:
        if not isinstance(item, dict) or item.get("draft") is not False or item.get("prerelease") is not False:
            continue
        release = release_from_payload(release_target, item)
        match = pattern.fullmatch(release.version)
        if match is not None:
            candidates.append((release, match.group(1)))
    eligible = [item for item in candidates if item[0].published_at <= now]
    if not eligible:
        raise UpdateError("Hermes: no published custom release is eligible")
    return max(eligible, key=lambda item: (natural_tag_key(item[1]), int(item[0].version.rsplit('.', 1)[1])))


def hermes_custom_assets(repository: str, release: Release, version: str) -> tuple[str, str, str]:
    filename = f"hermes_agent-{version}-py3-none-any.whl"
    required = (filename, f"{filename}.sha256")
    assets = release.payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError(f"Hermes {release.version}: custom release has no assets")
    found: dict[str, str] = {}
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") not in required:
            continue
        name = asset["name"]
        url = asset.get("browser_download_url")
        expected = "https://github.com/{}/releases/download/{}/{}".format(
            repository, urllib.parse.quote(release.version, safe=""), urllib.parse.quote(name, safe="")
        )
        if name in found or not isinstance(url, str) or url != expected:
            raise UpdateError(f"Hermes {release.version}: custom release assets are malformed")
        found[name] = url
    if set(found) != set(required):
        raise UpdateError(f"Hermes {release.version}: custom release assets are malformed")
    return filename, found[filename], found[f"{filename}.sha256"]


def hermes_wheel_metadata(wheel: bytes, version: str, source: str) -> tuple[object, ...]:
    if len(wheel) > HERMES_MAX_WHEEL_BYTES:
        raise UpdateError(f"Hermes: {source} wheel exceeds {HERMES_MAX_WHEEL_BYTES} bytes")
    try:
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            names = {
                kind: [entry for entry in archive.infolist() if re.fullmatch(rf"[^/]+[.]dist-info/{kind}", entry.filename)]
                for kind in ("METADATA", "WHEEL")
            }
            if any(len(entries) != 1 for entries in names.values()):
                raise UpdateError(f"Hermes: {source} wheel has no unique METADATA and WHEEL files")
            if any(entry.file_size > HERMES_MAX_METADATA_ENTRY_BYTES for entries in names.values() for entry in entries):
                raise UpdateError(f"Hermes: {source} wheel metadata entry exceeds {HERMES_MAX_METADATA_ENTRY_BYTES} bytes")
            message = email.parser.BytesParser().parsebytes(archive.read(names["METADATA"][0]))
            wheel_message = email.parser.BytesParser().parsebytes(archive.read(names["WHEEL"][0]))
    except (OSError, zipfile.BadZipFile) as error:
        raise UpdateError(f"Hermes: {source} wheel is invalid") from error
    if message.get("Name") != "hermes-agent" or message.get("Version") != version:
        raise UpdateError(f"Hermes: {source} wheel metadata does not match its release version")
    return (
        message["Name"], message["Version"],
        tuple(sorted(" ".join(value.split()) for value in message.get_all("Requires-Dist", []))),
        message.get("Requires-Python"),
        tuple(sorted(message.get_all("Provides-Extra", []))),
        tuple(sorted(wheel_message.get_all("Tag", []))),
    )


def hermes_official_wheel_metadata(
    version: str, opener: Callable[[str], bytes] | None, verify_provenance: bool = True
) -> tuple[object, ...]:
    filename, checksum, url = hermes_pypi_artifact(version, opener)
    if verify_provenance:
        hermes_pypi_provenance(version, filename, checksum, opener)
    wheel = fetch_url(url, opener)
    if sha256(wheel).hexdigest() != checksum:
        raise UpdateError(f"Hermes {version}: official PyPI wheel SHA-256 does not match metadata")
    return hermes_wheel_metadata(wheel, version, "official PyPI")


def hermes_custom_wheel_metadata(wheel: bytes, version: str, expected: tuple[object, ...]) -> None:
    if hermes_wheel_metadata(wheel, version, "custom") != expected:
        raise UpdateError("Hermes: custom wheel metadata differs from the official wheel")


def hermes_custom_locks(root: Path, version: str, checksum: str) -> tuple[str, str]:
    path = root / "infra/ansible/roles/hermes/files" / f"requirements-{version}.lock"
    if not path.exists():
        raise UpdateError(f"Hermes {version}: tracked transitive requirements lock is absent")
    full = path.read_text(encoding="utf-8")
    validate_hermes_lock(root, version, checksum=None)
    pattern = re.compile(rf"(?ms)^hermes-agent\[[^]]+\]=={re.escape(version)}.*?(?=^[a-z0-9][a-z0-9_.-]*(?:\[[^]]+\])?==|\Z)")
    match = pattern.search(full)
    if match is None:
        raise UpdateError(f"Hermes {version}: tracked lock does not contain the Hermes requirement block")
    block = re.sub(r"(?m)^\s*--hash=sha256:[0-9a-f]{64}.*\n?", "", match.group())
    block = re.sub(r"(?m)^(hermes-agent\[[^]]+\]==[^\\]+\\)\s*$", rf"\1\n    --hash=sha256:{checksum}", block)
    if f"--hash=sha256:{checksum}" not in block:
        raise UpdateError(f"Hermes {version}: unable to replace the Hermes wheel hash")
    return full[:match.start()] + block + full[match.end():], full[:match.start()] + full[match.end():]


def hermes_custom_tag_key(tag_prefix: str, tag: str) -> tuple[tuple[tuple[int, int | str], ...], int] | None:
    match = re.fullmatch(rf"{re.escape(tag_prefix)}([0-9]+[.][0-9]+[.][0-9]+)[.]([1-9][0-9]*)", tag)
    return (natural_tag_key(match.group(1)), int(match.group(2))) if match is not None else None


def hermes_custom_artifact_dir(root: Path, tag: str, checksum: str) -> Path:
    current = root
    for component in HERMES_CUSTOM_ARTIFACT_DIR.parts:
        current /= component
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise UpdateError("Hermes: custom artifact hierarchy must contain only directories, not symlinks")
        else:
            current.mkdir()
    directory = current / f"{urllib.parse.quote(tag, safe='')}-{checksum[:12]}"
    if directory.exists():
        if directory.is_symlink() or not directory.is_dir():
            raise UpdateError("Hermes: custom artifact directory must not be a symlink")
    else:
        directory.mkdir()
    return directory


def process_custom_hermes_discovery_target(
    target: HermesDiscoveryTarget, root: Path, now: datetime, text: str, repository: str, tag_prefix: str,
    opener: Callable[[str], bytes] | None,
) -> UpdateResult:
    fields = ("hermes_discovery_version", "hermes_discovery_tag", "hermes_discovery_commit", "hermes_discovery_wheel_sha256")
    if any(hermes_inventory_value(text, key) is None for key in fields):
        raise UpdateError("Hermes: custom release discovery pin group is incomplete")
    release, version = hermes_custom_release(repository, tag_prefix, now, opener)
    current_tag = hermes_inventory_value(text, "hermes_discovery_tag")
    current_group_complete = all(hermes_inventory_value(text, key) is not None for key in (
        "hermes_custom_wheel_url", "hermes_custom_requirements_lock_path", "hermes_custom_dependencies_lock_path",
    ))
    current_key = hermes_custom_tag_key(tag_prefix, current_tag) if current_group_complete and current_tag is not None else None
    selected_key = hermes_custom_tag_key(tag_prefix, release.version)
    if current_key is not None and selected_key is not None and selected_key < current_key:
        raise UpdateError("Hermes: refusing custom release rollback")
    filename, wheel_url, manifest_url = hermes_custom_assets(repository, release, version)
    checksum = checksum_from_manifest(
        fetch_url(manifest_url, opener, HERMES_MAX_MANIFEST_BYTES).decode("utf-8"),
        f"{filename}.sha256",
        filename,
    )
    wheel = fetch_url(wheel_url, opener, HERMES_MAX_WHEEL_BYTES)
    if sha256(wheel).hexdigest() != checksum:
        raise UpdateError("Hermes: custom wheel SHA-256 does not match its manifest")
    expected_metadata = hermes_official_wheel_metadata(version, opener, verify_provenance=False)
    hermes_custom_wheel_metadata(wheel, version, expected_metadata)
    tag_target = HermesDiscoveryTarget(target.name, target.path, "", f"https://api.github.com/repos/{repository}/git/ref/tags/{{tag}}", "", "", "", "")
    commit = hermes_tag_commit(tag_target, release, opener)
    full_lock, dependencies_lock = hermes_custom_locks(root, version, checksum)
    confirmed_release, confirmed_version = hermes_custom_release(repository, tag_prefix, now, opener)
    confirmed_filename, confirmed_wheel_url, confirmed_manifest_url = hermes_custom_assets(repository, confirmed_release, confirmed_version)
    confirmed_checksum = checksum_from_manifest(
        fetch_url(confirmed_manifest_url, opener, HERMES_MAX_MANIFEST_BYTES).decode("utf-8"),
        f"{confirmed_filename}.sha256",
        confirmed_filename,
    )
    confirmed_wheel = fetch_url(confirmed_wheel_url, opener, HERMES_MAX_WHEEL_BYTES)
    if sha256(confirmed_wheel).hexdigest() != confirmed_checksum:
        raise UpdateError("Hermes: custom wheel SHA-256 does not match its manifest")
    confirmed_metadata = hermes_official_wheel_metadata(confirmed_version, opener, verify_provenance=False)
    hermes_custom_wheel_metadata(confirmed_wheel, confirmed_version, confirmed_metadata)
    confirmed_commit = hermes_tag_commit(tag_target, confirmed_release, opener)
    confirmed_full, confirmed_dependencies = hermes_custom_locks(root, confirmed_version, confirmed_checksum)
    if (release_identity(confirmed_release), confirmed_version, confirmed_checksum, confirmed_commit, confirmed_metadata, confirmed_full, confirmed_dependencies) != (release_identity(release), version, checksum, commit, expected_metadata, full_lock, dependencies_lock):
        raise UpdateError("Hermes: custom release changed during re-resolution")
    if (root / target.path).read_text(encoding="utf-8") != text:
        raise UpdateError("Hermes: pin file changed during resolution")
    artifact_dir = hermes_custom_artifact_dir(root, release.version, checksum)
    full_path = artifact_dir / "requirements.lock"
    dependencies_path = artifact_dir / "requirements-dependencies.lock"
    lock_base = f"/workspace/{HERMES_CUSTOM_ARTIFACT_DIR.as_posix()}/{artifact_dir.name}"
    replacements = {
        "version": version, "tag": release.version, "commit": commit, "checksum": checksum,
        "wheel_url": wheel_url, "requirements_lock_path": f"{lock_base}/requirements.lock",
        "dependencies_lock_path": f"{lock_base}/requirements-dependencies.lock",
    }
    current_group = tuple(hermes_inventory_value(text, field) for field in (
        "hermes_discovery_version", "hermes_discovery_tag", "hermes_discovery_commit", "hermes_discovery_wheel_sha256",
        "hermes_custom_wheel_url", "hermes_custom_requirements_lock_path", "hermes_custom_dependencies_lock_path",
    ))
    resolved_group = tuple(replacements[key] for key in ("version", "tag", "commit", "checksum", "wheel_url", "requirements_lock_path", "dependencies_lock_path"))
    if current_group == resolved_group and full_path.exists() and dependencies_path.exists() and not full_path.is_symlink() and not dependencies_path.is_symlink() and full_path.read_text(encoding="utf-8") == full_lock and dependencies_path.read_text(encoding="utf-8") == dependencies_lock:
        return UpdateResult(target.name, target.path, version, version, "current", "current custom GitHub release is verified")
    atomic_write_if_changed(full_path, full_lock)
    atomic_write_if_changed(dependencies_path, dependencies_lock)
    updated = text
    replacement_target = Target(target.name, target.path, "", "", target.release_url)
    for key, value in replacements.items():
        field = {"checksum": "hermes_discovery_wheel_sha256", "wheel_url": "hermes_custom_wheel_url", "requirements_lock_path": "hermes_custom_requirements_lock_path", "dependencies_lock_path": "hermes_custom_dependencies_lock_path"}.get(key, f"hermes_discovery_{key}")
        pattern = rf"(?m)^(\s*{field}:\s*)[^\n]*$"
        updated = replace_once(pattern, rf"\g<1>{value}", updated, replacement_target) if re.search(pattern, updated) else updated.rstrip() + f"\n    {field}: {value}\n"
    atomic_write_if_changed(root / target.path, updated)
    return UpdateResult(
        target.name,
        target.path,
        hermes_inventory_value(text, "hermes_discovery_version"),
        version,
        "updated",
        f"verified custom GitHub wheel; tag commit {commit}; no release-age hold",
    )


def process_hermes_discovery_target(
    target: HermesDiscoveryTarget,
    root: Path,
    now: datetime,
    opener: Callable[[str], bytes] | None = None,
) -> UpdateResult:
    path = root / target.path
    if not path.exists():
        return UpdateResult(target.name, target.path, None, None, "skip", "file not present")
    text = path.read_text(encoding="utf-8")
    custom = hermes_custom_config(text)
    if custom is not None:
        return process_custom_hermes_discovery_target(target, root, now, text, *custom, opener)
    patterns = {
        "version": r'(?m)^(\s*hermes_discovery_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        "tag": r'(?m)^(\s*hermes_discovery_tag:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        "commit": r"(?m)^(\s*hermes_discovery_commit:\s*)([0-9a-f]+)\s*$",
        "checksum": r"(?m)^(\s*hermes_discovery_wheel_sha256:\s*)([0-9a-f]+)\s*$",
    }
    matches = {name: re.search(pattern, text) for name, pattern in patterns.items()}
    if any(match is None for match in matches.values()):
        return UpdateResult(target.name, target.path, None, None, "skip", "incomplete operator pin group (hermes)")
    current = matches["version"].group(2)  # type: ignore[union-attr]
    expected = (
        target.managed_version,
        target.managed_tag,
        target.managed_commit,
        target.managed_wheel_sha256,
    )
    actual = tuple(matches[name].group(2) for name in ("version", "tag", "commit", "checksum"))  # type: ignore[union-attr]
    if actual != expected:
        return UpdateResult(target.name, target.path, current, None, "skip", "custom operator pin group (hermes)")

    release, held = hermes_releases(target, now, opener)
    resolved = resolve_hermes_release(target, release, root, opener)
    if (resolved[0], release.version, resolved[1], resolved[2]) == expected:
        held_detail = (
            f"; {held.version} remains inside the strict {OCI_MIN_AGE_HOURS}h hold"
            if held is not None
            else ""
        )
        return UpdateResult(target.name, target.path, current, current, "current", f"verified PyPI provenance and lock{held_detail}")

    confirmed_release, _confirmed_held = hermes_releases(target, now, opener)
    confirmed = resolve_hermes_release(target, confirmed_release, root, opener)
    if (
        release_identity(confirmed_release) != release_identity(release)
        or confirmed != resolved
    ):
        raise UpdateError(f"{target.name}: release, provenance, or wheel changed during re-resolution")
    if path.read_text(encoding="utf-8") != text:
        raise UpdateError(f"{target.name}: pin file changed during resolution")
    replacements = {
        "version": resolved[0],
        "tag": release.version,
        "commit": resolved[1],
        "checksum": resolved[2],
    }
    updated = text
    replacement_target = Target(target.name, target.path, "", "", target.release_url)
    for name in ("version", "tag", "commit", "checksum"):
        updated = replace_once(patterns[name], rf"\g<1>{replacements[name]}\g<3>" if name in {"version", "tag"} else rf"\g<1>{replacements[name]}", updated, replacement_target)
    atomic_write_text(path, updated)
    return UpdateResult(
        target.name,
        target.path,
        current,
        resolved[0],
        "updated",
        f"official PyPI wheel and provenance; tag commit {resolved[1]}; strict {OCI_MIN_AGE_HOURS}h hold",
    )


def fetch_json_value(
    url: str,
    opener: Callable[[str], bytes] | None = None,
) -> object:
    try:
        return json.loads(fetch_url(url, opener).decode("utf-8"))
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid JSON from {url}: {error}") from error


def github_commit_time(payload: object, context: str) -> datetime:
    if not isinstance(payload, dict):
        raise UpdateError(f"{context}: unexpected commit payload")
    commit = payload.get("commit")
    if not isinstance(commit, dict):
        raise UpdateError(f"{context}: commit metadata is missing")
    committer = commit.get("committer")
    if not isinstance(committer, dict) or not isinstance(committer.get("date"), str):
        raise UpdateError(f"{context}: committer timestamp is missing")
    return parse_timestamp(committer["date"])


def resolve_tag_pin(
    target: TagPinTarget,
    opener: Callable[[str], bytes] | None = None,
) -> tuple[str, str, datetime]:
    payload = fetch_json_value(target.tags_url, opener)
    if not isinstance(payload, list):
        raise UpdateError(f"{target.name}: unexpected tags payload")
    candidates: list[tuple[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        match = re.fullmatch(r"v?(\d+[.]\d+[.]\d+)", item["name"])
        commit = item.get("commit")
        if match is None or not isinstance(commit, dict) or not isinstance(commit.get("sha"), str):
            continue
        candidates.append((match.group(1), commit["sha"]))
    if not candidates:
        raise UpdateError(f"{target.name}: no semantic version tags found")
    version, commit = max(candidates, key=lambda item: natural_tag_key(item[0]))
    published = github_commit_time(
        fetch_json_value(target.commit_url_template.format(commit=commit), opener),
        target.name,
    )
    return version, commit, published


def process_tag_pin_target(
    target: TagPinTarget,
    root: Path,
    now: datetime,
    opener: Callable[[str], bytes] | None = None,
) -> UpdateResult:
    path = root / target.path
    if not path.exists():
        return UpdateResult(target.name, target.path, None, None, "skip", "file not present")
    text = path.read_text(encoding="utf-8")
    match = re.search(target.pattern, text)
    if match is None:
        return UpdateResult(target.name, target.path, None, None, "skip", "version pin not present")
    current = match.group(2)
    if current != target.managed_version:
        return UpdateResult(target.name, target.path, current, None, "skip", "custom operator pin")
    version, commit, published = resolve_tag_pin(target, opener)
    if version == current:
        return UpdateResult(target.name, target.path, current, version, "current", "latest semantic tag")
    age = now - published
    if age < timedelta(hours=OCI_MIN_AGE_HOURS):
        return UpdateResult(target.name, target.path, current, version, "hold", f"tag commit age {age}; strict {OCI_MIN_AGE_HOURS}h hold")
    confirmed = resolve_tag_pin(target, opener)
    if confirmed != (version, commit, published):
        raise UpdateError(f"{target.name}: tag changed during re-resolution")
    if path.read_text(encoding="utf-8") != text:
        raise UpdateError(f"{target.name}: pin file changed during resolution")
    replacement_target = Target(target.name, target.path, "", "", target.tags_url)
    updated = replace_once(
        target.pattern,
        target.replacement.format(version=version),
        text,
        replacement_target,
    )
    atomic_write_text(path, updated)
    return UpdateResult(target.name, target.path, current, version, "updated", f"verified tag commit; strict {OCI_MIN_AGE_HOURS}h hold")


def resolve_go_toolchain(
    target: GoToolchainTarget,
    opener: Callable[[str], bytes] | None = None,
) -> tuple[str, str, str, datetime]:
    payload = fetch_json_value(target.releases_url, opener)
    if not isinstance(payload, list):
        raise UpdateError(f"{target.name}: unexpected release payload")
    release = next(
        (item for item in payload if isinstance(item, dict) and item.get("stable") is True),
        None,
    )
    if not isinstance(release, dict) or not isinstance(release.get("version"), str):
        raise UpdateError(f"{target.name}: no stable release found")
    version = release["version"].removeprefix("go")
    files = release.get("files")
    if not isinstance(files, list):
        raise UpdateError(f"{target.name}: release files are missing")
    checksums: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        arch = item.get("arch")
        if (
            item.get("os") == "linux"
            and item.get("kind") == "archive"
            and arch in {"amd64", "arm64"}
            and isinstance(item.get("sha256"), str)
        ):
            checksums[str(arch)] = item["sha256"]
    if set(checksums) != {"amd64", "arm64"} or any(
        not re.fullmatch(r"[0-9a-f]{64}", value) for value in checksums.values()
    ):
        raise UpdateError(f"{target.name}: Linux checksums are incomplete")
    published = github_commit_time(
        fetch_json_value(target.commit_url_template.format(version=version), opener),
        target.name,
    )
    return version, checksums["amd64"], checksums["arm64"], published


def process_go_toolchain_target(
    target: GoToolchainTarget,
    root: Path,
    now: datetime,
    opener: Callable[[str], bytes] | None = None,
) -> UpdateResult:
    path = root / target.path
    if not path.exists():
        return UpdateResult(target.name, target.path, None, None, "skip", "file not present")
    text = path.read_text(encoding="utf-8")
    patterns = {
        "version": r'(?m)^(\s*caddy_build_go_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        "amd64": r"(?m)^(\s*caddy_build_go_sha256_amd64:\s*)([0-9a-f]+)\s*$",
        "arm64": r"(?m)^(\s*caddy_build_go_sha256_arm64:\s*)([0-9a-f]+)\s*$",
    }
    matches = {name: re.search(pattern, text) for name, pattern in patterns.items()}
    if any(match is None for match in matches.values()):
        return UpdateResult(target.name, target.path, None, None, "skip", "incomplete Caddy Go pin group")
    current = matches["version"].group(2)  # type: ignore[union-attr]
    actual = tuple(matches[name].group(2) for name in ("version", "amd64", "arm64"))  # type: ignore[union-attr]
    expected = (
        target.managed_version,
        target.managed_sha256_amd64,
        target.managed_sha256_arm64,
    )
    if actual != expected:
        return UpdateResult(target.name, target.path, current, None, "skip", "custom operator pin group (Caddy Go)")
    resolved = resolve_go_toolchain(target, opener)
    if resolved[:3] == actual:
        return UpdateResult(target.name, target.path, current, current, "current", "verified official Go release checksums")
    age = now - resolved[3]
    if age < timedelta(hours=OCI_MIN_AGE_HOURS):
        return UpdateResult(target.name, target.path, current, resolved[0], "hold", f"tag commit age {age}; strict {OCI_MIN_AGE_HOURS}h hold")
    confirmed = resolve_go_toolchain(target, opener)
    if confirmed != resolved:
        raise UpdateError(f"{target.name}: release changed during re-resolution")
    if path.read_text(encoding="utf-8") != text:
        raise UpdateError(f"{target.name}: pin file changed during resolution")
    updated = text
    replacements = {"version": resolved[0], "amd64": resolved[1], "arm64": resolved[2]}
    replacement_target = Target(target.name, target.path, "", "", target.releases_url)
    for name in ("version", "amd64", "arm64"):
        suffix = r"\g<3>" if name == "version" else ""
        updated = replace_once(
            patterns[name],
            rf"\g<1>{replacements[name]}{suffix}",
            updated,
            replacement_target,
        )
    atomic_write_text(path, updated)
    return UpdateResult(target.name, target.path, current, resolved[0], "updated", f"official Go checksums; strict {OCI_MIN_AGE_HOURS}h hold")


def run(
    root: Path,
    min_age_hours: int,
    opener: Callable[[str], bytes] | None = None,
) -> list[UpdateResult]:
    now = datetime.now(timezone.utc)
    min_age = timedelta(hours=min_age_hours)
    results = [process_target(target, root, now, min_age, opener) for target in TARGETS]
    if opener is None:
        results.append(process_tag_pin_target(CADDY_CLOUDFLARE_TAG, root, now))
        results.append(process_go_toolchain_target(CADDY_GO_TOOLCHAIN, root, now))
        groups = dict.fromkeys(target.group for target in OCI_TARGETS)
        for group in groups:
            results.extend(process_oci_group(group, root, now, fetch_oci_registry))
        results.append(process_discovery_target(TECHNITIUM_DISCOVERY, root, now))
        results.append(process_hermes_discovery_target(HERMES_DISCOVERY, root, now))
    return results


def print_results(results: list[UpdateResult]) -> None:
    for result in results:
        if result.status == "updated":
            print(f"UPDATED {result.name}: {result.current} -> {result.latest} ({result.path})")
        elif result.status == "hold":
            print(f"HOLD    {result.name}: {result.current} -> {result.latest}; {result.detail}")
        elif result.status == "current":
            print(f"CURRENT {result.name}: {result.current}")
        else:
            print(f"SKIP    {result.name}: {result.detail} ({result.path})")


UNMANAGED = (
    "Debian non-security package upgrades remain operator-reviewed; security updates are automatic and never reboot hosts.",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--min-age-hours", type=int, default=DEFAULT_MIN_AGE_HOURS)
    args = parser.parse_args(argv)

    try:
        results = run(args.root, args.min_age_hours)
    except UpdateError as error:
        print(error, file=sys.stderr)
        return 1

    print_results(results)
    print("\nUnmanaged by just update:")
    for item in UNMANAGED:
        print(f"- {item}")
    print(
        "\nNext steps: review the diff, then run `just validate`, `just plan`, "
        "and only apply after approval."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

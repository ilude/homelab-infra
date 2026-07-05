#!/usr/bin/env python3
"""Update pinned tool and service versions after a release-age hold period."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

DEFAULT_MIN_AGE_HOURS = 48
USER_AGENT = "homelab-infra-update/1.0"


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


@dataclass(frozen=True)
class UpdateResult:
    name: str
    path: Path
    current: str | None
    latest: str | None
    status: str
    detail: str


TARGETS = (
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
        release_url="https://code.forgejo.org/api/v1/repos/forgejo/forgejo/releases/latest",
    ),
    Target(
        name="Forgejo runner",
        path=Path("values/ansible/inventory/local.yml"),
        pattern=r'(?m)^(\s*forgejo_runner_version:\s*["\']?)([^"\'\s]+)(["\']?\s*)$',
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://code.forgejo.org/api/v1/repos/forgejo/runner/releases/latest",
    ),
    Target(
        name="Docker Compose plugin",
        path=Path("infra/ansible/roles/forgejo_runner/tasks/main.yml"),
        pattern=r"(version=\"{{ forgejo_runner_compose_version \| default\(')([^']+)('\) }}\";)",
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/docker/compose/releases/latest",
    ),
    Target(
        name="just",
        path=Path("infra/ansible/roles/forgejo_runner/tasks/main.yml"),
        pattern=r"(version=\"{{ forgejo_runner_just_version \| default\(')([^']+)('\) }}\";)",
        replacement=r"\g<1>{version}\g<3>",
        release_url="https://api.github.com/repos/casey/just/releases/latest",
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


def fetch_url(url: str, opener: Callable[[str], bytes] | None = None) -> bytes:
    if opener is not None:
        return opener(url)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
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


def checksum_for_release(
    target: Target,
    release: Release,
    opener: Callable[[str], bytes] | None,
) -> str | None:
    if not target.checksum_asset_template or not target.checksum_file_template:
        return None
    asset_name = target.checksum_asset_template.format(version=release.version)
    file_name = target.checksum_file_template.format(version=release.version)
    checksum_url = release_asset_url(release, asset_name)
    checksum_text = fetch_url(checksum_url, opener).decode("utf-8")
    for line in checksum_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].lstrip("*") == file_name:
            return fields[0]
    raise UpdateError(f"{asset_name} does not include checksum for {file_name}")


def replace_version(target: Target, text: str, release: Release, checksum: str | None) -> str:
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

    checksum = checksum_for_release(target, release, opener)
    updated = replace_version(target, text, release, checksum)
    (root / target.path).write_text(updated, encoding="utf-8", newline="\n")
    return UpdateResult(
        target.name,
        target.path,
        current,
        release.version,
        "updated",
        f"release age {age}; {release.url}",
    )


def run(
    root: Path,
    min_age_hours: int,
    opener: Callable[[str], bytes] | None = None,
) -> list[UpdateResult]:
    now = datetime.now(timezone.utc)
    min_age = timedelta(hours=min_age_hours)
    return [process_target(target, root, now, min_age, opener) for target in TARGETS]


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
    "Technitium: installed by upstream install script only when missing; "
    "no pinned upgrade target yet.",
    "Tailscale: installed only when missing; package upgrade policy is not defined yet.",
    "Caddy: apt/custom xcaddy rebuild upgrade policy is not defined yet.",
    "Debian LXC OS packages: required packages are installed during playbooks, "
    "but full OS upgrades are not managed.",
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

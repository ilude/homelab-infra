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


@dataclass(frozen=True)
class Target:
    name: str
    path: Path
    pattern: str
    replacement: str
    release_url: str
    strip_prefix: str = "v"


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
    ),
    Target(
        name="TFLint",
        path=Path("tools/Dockerfile"),
        pattern=r"(?m)^(ARG TFLINT_VERSION=)([^\s]+)$",
        replacement=r"\g<1>{version}",
        release_url="https://api.github.com/repos/terraform-linters/tflint/releases/latest",
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


def fetch_release(url: str, opener: Callable[[str], bytes] | None = None) -> dict[str, object]:
    if opener is not None:
        raw = opener(url)
    else:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.URLError as error:
            raise UpdateError(f"failed to fetch {url}: {error}") from error
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


def replace_version(target: Target, text: str, version: str) -> str:
    replacement = target.replacement.format(version=version)
    updated, count = re.subn(target.pattern, replacement, text, count=1)
    if count != 1:
        raise UpdateError(
            f"{target.name}: expected one version match in {target.path}, found {count}"
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

    updated = replace_version(target, text, release.version)
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

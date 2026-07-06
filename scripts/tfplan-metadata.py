#!/usr/bin/env python3
"""Create and verify metadata for a saved OpenTofu plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_MAX_AGE_HOURS = 24
INPUT_GLOBS = (
    "infra/opentofu/**/*.tf",
    "infra/opentofu/.terraform.lock.hcl",
    "infra/ansible/scripts/apply-technitium-dns.py",
    "infra/ansible/**/*",
    "scripts/*.py",
    "ansible.cfg",
    "values/terraform.tfvars",
    "values/dns-records.local.json",
    "values/ansible/inventory/local.yml",
    "values/.env",
    "settings.example.json",
    "settings.local.json",
)


class MetadataError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matching_inputs(repo: Path) -> dict[str, str]:
    paths: set[Path] = set()
    for pattern in INPUT_GLOBS:
        for path in repo.glob(pattern):
            if path.is_file():
                paths.add(path)
    return {
        path.relative_to(repo).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda item: item.as_posix())
    }


def git_commit(repo: Path) -> str | None:
    env_commit = os.environ.get("INFRA_GIT_COMMIT")
    if env_commit:
        return env_commit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def create_metadata(plan: Path, metadata: Path, repo: Path, max_age_hours: int) -> None:
    if not plan.is_file():
        raise MetadataError(f"Missing plan file: {plan}")
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=max_age_hours)).isoformat(),
        "git_commit": git_commit(repo),
        "plan": {
            "path": plan.as_posix(),
            "sha256": sha256_file(plan),
        },
        "inputs": matching_inputs(repo),
    }
    metadata.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_metadata(metadata: Path) -> dict[str, Any]:
    if not metadata.is_file():
        raise MetadataError("Saved tfplan metadata is missing. Run `just plan` again.")
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.") from error
    if data.get("schema_version") != SCHEMA_VERSION:
        raise MetadataError("Saved tfplan metadata is unsupported. Run `just plan` again.")
    return data


def verify_metadata(plan: Path, metadata: Path, repo: Path) -> None:
    if not plan.is_file():
        raise MetadataError("Saved tfplan is missing. Run `just plan` again.")
    data = load_metadata(metadata)

    try:
        expires_at = datetime.fromisoformat(data["expires_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.") from error
    if datetime.now(timezone.utc) > expires_at:
        raise MetadataError("Saved tfplan is expired. Run `just plan` again.")

    expected_plan_hash = data.get("plan", {}).get("sha256")
    if expected_plan_hash != sha256_file(plan):
        raise MetadataError("Saved tfplan changed. Run `just plan` again.")

    expected_inputs = data.get("inputs")
    if not isinstance(expected_inputs, dict):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    current_inputs = matching_inputs(repo)
    if expected_inputs != current_inputs:
        raise MetadataError("Saved tfplan inputs changed. Run `just plan` again.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--plan", type=Path, required=True)
    create.add_argument("--metadata", type=Path, required=True)
    create.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--metadata", type=Path, required=True)

    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        if args.command == "create":
            create_metadata(args.plan, args.metadata, repo, args.max_age_hours)
        elif args.command == "verify":
            verify_metadata(args.plan, args.metadata, repo)
    except MetadataError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

SCHEMA_VERSION = 2
DEFAULT_MAX_AGE_HOURS = 24
INPUT_GLOBS = (
    "infra/opentofu/**/*.tf",
    "infra/opentofu/.terraform.lock.hcl",
    "infra/ansible/scripts/apply-technitium-dns.py",
    "infra/ansible/**/*",
    "scripts/*.py",
    "scripts/*.sh",
    "justfile",
    "compose.yaml",
    "tools/**/*",
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


def load_plan_json(plan: Path, repo: Path) -> dict[str, Any]:
    tofu_dir = repo / "infra" / "opentofu"
    plan_path = plan if plan.is_absolute() else repo / plan
    if tofu_dir.is_dir():
        command = [
            "tofu",
            "-chdir=infra/opentofu",
            "show",
            "-json",
            os.path.relpath(plan_path, tofu_dir),
        ]
    else:
        command = ["tofu", "show", "-json", plan.as_posix()]
    result = subprocess.run(
        command,
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise MetadataError(f"cannot inspect saved tfplan: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MetadataError("cannot parse saved tfplan JSON") from error
    if not isinstance(data, dict):
        raise MetadataError("saved tfplan JSON must be an object")
    return data


def summarize_plan(plan_json: dict[str, Any]) -> dict[str, Any]:
    counts = {"create": 0, "update": 0, "replace": 0, "delete": 0, "read": 0, "no_op": 0}
    destructive_changes: list[dict[str, str]] = []
    for change in plan_json.get("resource_changes", []):
        if not isinstance(change, dict):
            continue
        actions = change.get("change", {}).get("actions", [])
        if not isinstance(actions, list):
            continue
        address = str(change.get("address", "unknown"))
        if "delete" in actions and "create" in actions:
            counts["replace"] += 1
            destructive_changes.append({"address": address, "actions": "/".join(actions)})
        elif actions == ["delete"]:
            counts["delete"] += 1
            destructive_changes.append({"address": address, "actions": "delete"})
        elif actions == ["create"]:
            counts["create"] += 1
        elif actions == ["update"]:
            counts["update"] += 1
        elif actions == ["read"]:
            counts["read"] += 1
        elif actions == ["no-op"]:
            counts["no_op"] += 1
        elif "delete" in actions:
            destructive_changes.append({"address": address, "actions": "/".join(actions)})
    return {
        "resource_changes": counts,
        "destructive": bool(destructive_changes),
        "destructive_changes": destructive_changes,
    }


def format_plan_summary(summary: dict[str, Any]) -> str:
    counts = summary.get("resource_changes", {})
    lines = [
        "OpenTofu plan summary:",
        f"  create: {counts.get('create', 0)}",
        f"  update: {counts.get('update', 0)}",
        f"  replace: {counts.get('replace', 0)}",
        f"  delete: {counts.get('delete', 0)}",
    ]
    destructive_changes = summary.get("destructive_changes", [])
    if destructive_changes:
        lines.append("Destructive changes:")
        for item in destructive_changes[:20]:
            lines.append(f"  - {item.get('address', 'unknown')}: {item.get('actions', 'delete')}")
        remaining = len(destructive_changes) - 20
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")
        lines.append("Apply is gated. Set INFRA_ALLOW_DESTROY=1 only after review.")
    else:
        lines.append("Destructive changes: none")
    return "\n".join(lines)


def create_metadata(
    plan: Path,
    metadata: Path,
    repo: Path,
    max_age_hours: int,
    plan_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not plan.is_file():
        raise MetadataError(f"Missing plan file: {plan}")
    now = datetime.now(timezone.utc)
    summary = summarize_plan(plan_json if plan_json is not None else load_plan_json(plan, repo))
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=max_age_hours)).isoformat(),
        "git_commit": git_commit(repo),
        "plan": {
            "path": plan.as_posix(),
            "sha256": sha256_file(plan),
        },
        "summary": summary,
        "inputs": matching_inputs(repo),
    }
    metadata.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def validate_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    counts = summary.get("resource_changes")
    if not isinstance(counts, dict):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    for key in ("create", "update", "replace", "delete"):
        if not isinstance(counts.get(key), int):
            raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    if not isinstance(summary.get("destructive"), bool):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    if not isinstance(summary.get("destructive_changes"), list):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    return summary


def load_metadata(metadata: Path) -> dict[str, Any]:
    if not metadata.is_file():
        raise MetadataError("Saved tfplan metadata is missing. Run `just plan` again.")
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.") from error
    if data.get("schema_version") != SCHEMA_VERSION:
        raise MetadataError("Saved tfplan metadata is unsupported. Run `just plan` again.")
    if not isinstance(data.get("plan", {}).get("sha256"), str):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    if not isinstance(data.get("inputs"), dict):
        raise MetadataError("Saved tfplan metadata is invalid. Run `just plan` again.")
    data["summary"] = validate_summary(data.get("summary"))
    return data


def verify_metadata(plan: Path, metadata: Path, repo: Path, allow_destroy: bool = False) -> None:
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

    expected_inputs = data["inputs"]
    current_inputs = matching_inputs(repo)
    if expected_inputs != current_inputs:
        raise MetadataError("Saved tfplan inputs changed. Run `just plan` again.")

    expected_commit = data.get("git_commit")
    current_commit = git_commit(repo)
    if expected_commit and current_commit and expected_commit != current_commit:
        raise MetadataError("Saved tfplan git commit changed. Run `just plan` again.")

    summary = data["summary"]
    if summary.get("destructive") and not allow_destroy:
        raise MetadataError(
            "Saved tfplan contains destructive changes. Review `just plan` output, then rerun "
            "with `INFRA_ALLOW_DESTROY=1 just apply` only if the deletes/replacements are intended."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--plan", type=Path, required=True)
    create.add_argument("--metadata", type=Path, required=True)
    create.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)
    create.add_argument("--print-summary", action="store_true")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--metadata", type=Path, required=True)
    verify.add_argument("--allow-destroy", action="store_true")

    summary = subparsers.add_parser("summary")
    summary.add_argument("--metadata", type=Path, required=True)

    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        if args.command == "create":
            data = create_metadata(args.plan, args.metadata, repo, args.max_age_hours)
            if args.print_summary:
                print(format_plan_summary(data["summary"]))
        elif args.command == "verify":
            verify_metadata(args.plan, args.metadata, repo, args.allow_destroy)
        elif args.command == "summary":
            print(format_plan_summary(load_metadata(args.metadata)["summary"]))
    except MetadataError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Roll out one immutable Onclave core image with BWS-backed rollback."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
INVENTORY_FAMILY = "HOMELAB_ANSIBLE_INVENTORY"
PIN_KEYS = (
    "onclave_source_git_sha",
    "onclave_app_definition_url",
    "onclave_app_definition_sha256",
    "onclave_backup_script_sha256",
    "onclave_restore_script_sha256",
    "onclave_core_image_tag",
    "onclave_core_image_digest",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_URL_RE = re.compile(
    r"^(https://raw\.githubusercontent\.com/[^/]+/[^/]+/)"
    r"[0-9a-f]{40}/deploy/app/onclave/compose\.yaml$"
)
Fetch = Callable[[str, Mapping[str, str]], bytes]
CORE_HEALTHCHECK_TESTS = {
    "/health": ["CMD", "wget", "-qO-", "http://127.0.0.1:8000/health"],
    "/live": ["CMD", "wget", "-qO-", "http://127.0.0.1:8000/live"],
}


class RolloutError(RuntimeError):
    pass


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RolloutError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fetch_url(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(4 * 1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as error:
        raise RolloutError(f"download failed for {url.split('?')[0]}") from error
    if len(body) > 4 * 1024 * 1024:
        raise RolloutError("download exceeded the 4 MiB rollout limit")
    return body


def derive_digest_from_response(repository: str, tag: str) -> str:
    if not repository.startswith("ghcr.io/"):
        raise RolloutError("Onclave core image repository must be on GHCR")
    image_path = repository.removeprefix("ghcr.io/")
    token_url = "https://ghcr.io/token?" + urllib.parse.urlencode(
        {"scope": f"repository:{image_path}:pull", "service": "ghcr.io"}
    )
    try:
        with urllib.request.urlopen(token_url, timeout=30) as response:
            token_payload = json.loads(response.read(64 * 1024))
        token = token_payload.get("token")
        if not isinstance(token, str) or not token:
            raise RolloutError("GHCR returned no anonymous pull token")
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{image_path}/manifests/{tag}",
            headers={
                "Accept": "application/vnd.oci.image.index.v1+json, "
                "application/vnd.docker.distribution.manifest.list.v2+json, "
                "application/vnd.oci.image.manifest.v1+json, "
                "application/vnd.docker.distribution.manifest.v2+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "homelab-infra-onclave-core-rollout/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = response.headers.get("Docker-Content-Digest", "")
            response.read(1024)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RolloutError("GHCR manifest lookup failed") from error
    if not DIGEST_RE.fullmatch(digest):
        raise RolloutError("GHCR returned no immutable manifest digest")
    return digest


def replace_pin(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^([ \t]*{re.escape(key)}:[ \t]*)[^\r\n]+$")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RolloutError(f"inventory must contain exactly one {key} pin")
    return pattern.sub(lambda match: match.group(1) + value, text, count=1)


def update_inventory_pins(text: str, updates: Mapping[str, str]) -> str:
    if set(updates) != set(PIN_KEYS):
        raise RolloutError("rollout attempted to change an unapproved pin set")
    updated = text
    for key in PIN_KEYS:
        updated = replace_pin(updated, key, updates[key])
    return updated


def inventory_vars(inventory_text: str, parser) -> dict[str, object]:
    data = parser(inventory_text, INVENTORY_FAMILY)
    try:
        variables = data["all"]["vars"]
    except (KeyError, TypeError) as error:
        raise RolloutError("Onclave inventory has no all.vars mapping") from error
    if not isinstance(variables, dict):
        raise RolloutError("Onclave inventory all.vars is not a mapping")
    missing = [key for key in (*PIN_KEYS, "onclave_core_image_repository") if key not in variables]
    if missing:
        raise RolloutError("Onclave inventory is missing managed pins")
    return variables


def pin_values(inventory_text: str, parser) -> dict[str, str]:
    variables = inventory_vars(inventory_text, parser)
    return {key: str(variables[key]) for key in PIN_KEYS}


def assert_only_pins_changed(before: str, after: str, parser) -> None:
    before_data = parser(before, INVENTORY_FAMILY)
    after_data = parser(after, INVENTORY_FAMILY)
    before_vars = before_data.get("all", {}).get("vars", {})
    after_vars = after_data.get("all", {}).get("vars", {})
    if not isinstance(before_vars, dict) or not isinstance(after_vars, dict):
        raise RolloutError("Onclave inventory all.vars is not a mapping")
    if set(before_vars) != set(after_vars):
        raise RolloutError("rollout changed the inventory variable set")
    for key in set(before_vars) - set(PIN_KEYS):
        if before_vars[key] != after_vars[key]:
            raise RolloutError(f"rollout changed unrelated inventory key {key}")


def checksum(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def type_sensitive_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        if len(left) != len(right):
            return False
        unmatched = list(right.items())
        for left_key, left_value in left.items():
            match = next(
                (
                    index
                    for index, (right_key, _right_value) in enumerate(unmatched)
                    if type_sensitive_equal(left_key, right_key)
                ),
                None,
            )
            if match is None:
                return False
            _right_key, right_value = unmatched.pop(match)
            if not type_sensitive_equal(left_value, right_value):
                return False
        return True
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            type_sensitive_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return left == right


def core_health_path(compose: object) -> str:
    try:
        test = compose["services"]["onclave-core"]["healthcheck"]["test"]  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise RolloutError("Onclave app definition has no core healthcheck command") from error
    for path, expected in CORE_HEALTHCHECK_TESTS.items():
        if test == expected:
            return path
    raise RolloutError("Onclave core healthcheck command is not a supported exact contract")


def compatible_artifact_transition(
    previous: Mapping[str, bytes],
    desired: Mapping[str, bytes],
    parse_yaml,
) -> tuple[str, str]:
    required_artifacts = {"compose.yaml", "backup-postgres.sh", "restore-postgres.sh"}
    if not required_artifacts.issubset(previous) or not required_artifacts.issubset(desired):
        raise RolloutError("core-only rollout is missing a required app/helper contract")
    for helper in ("backup-postgres.sh", "restore-postgres.sh"):
        if previous[helper] != desired[helper]:
            raise RolloutError(
                "core-only rollout requires unchanged app/helper contracts; changed: " + helper
            )

    try:
        previous_compose = parse_yaml(previous["compose.yaml"].decode("utf-8"), "previous compose")
        desired_compose = parse_yaml(desired["compose.yaml"].decode("utf-8"), "desired compose")
    except (KeyError, UnicodeDecodeError) as error:
        raise RolloutError("Onclave app definition is missing or is not UTF-8 YAML") from error
    except Exception as error:
        raise RolloutError("Onclave app definition is not valid YAML") from error
    previous_path = core_health_path(previous_compose)
    desired_path = core_health_path(desired_compose)
    if type_sensitive_equal(previous_compose, desired_compose):
        return previous_path, desired_path

    normalized_desired = copy.deepcopy(desired_compose)
    normalized_desired["services"]["onclave-core"]["healthcheck"]["test"] = (  # type: ignore[index]
        CORE_HEALTHCHECK_TESTS[previous_path]
    )
    if (
        previous_path != "/health"
        or desired_path != "/live"
        or not type_sensitive_equal(normalized_desired, previous_compose)
    ):
        raise RolloutError(
            "core-only rollout requires unchanged app/helper contracts except the exact "
            "one-way onclave-core healthcheck /health to /live transition; use the reviewed "
            "Onclave role for environment, topology, or dependency changes"
        )
    return previous_path, desired_path


def source_urls(current_url: str, source_sha: str) -> dict[str, str]:
    match = SOURCE_URL_RE.fullmatch(current_url)
    if not match:
        raise RolloutError("current Onclave app URL is not a pinned GitHub raw URL")
    base = f"{match.group(1)}{source_sha}/deploy/app/onclave/"
    return {
        "onclave_app_definition_url": base + "compose.yaml",
        "backup-postgres.sh": base + "backup-postgres.sh",
        "restore-postgres.sh": base + "restore-postgres.sh",
    }


def acquire_rollout_lock(record_dir: Path):
    import fcntl

    lock_path = record_dir / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        raise RolloutError("another Onclave core rollout is already running") from error
    return handle


def record_path(record_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return record_dir / f"onclave-core-{stamp}.json"


def write_record(
    path: Path,
    status: str,
    previous: Mapping[str, str],
    desired: Mapping[str, str],
    contract: Mapping[str, object],
    operation: Mapping[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": status,
        "previous": dict(previous),
        "desired": dict(desired),
        "contract": dict(contract),
    }
    if operation is not None:
        payload["operation"] = dict(operation)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_playbook(
    mode: str,
    values_dir: Path,
    pins: Mapping[str, str],
    health_path: str,
    compatible_installed_health_paths: Sequence[str],
    compatible_installed_revisions: Sequence[str],
) -> dict[str, object]:
    if health_path not in CORE_HEALTHCHECK_TESTS:
        raise RolloutError("refusing unsupported core healthcheck path")
    if not compatible_installed_health_paths or any(
        path not in CORE_HEALTHCHECK_TESTS for path in compatible_installed_health_paths
    ):
        raise RolloutError("refusing unsupported installed core healthcheck path")
    if not compatible_installed_revisions or any(
        not SHA_RE.fullmatch(revision) for revision in compatible_installed_revisions
    ):
        raise RolloutError("refusing unsupported installed core revision")
    result_path = values_dir / f".onclave-core-rollout-{mode}.json"
    result_path.unlink(missing_ok=True)
    extra = {
        "onclave_core_rollout_mode": mode,
        "onclave_core_rollout_expected_sha": pins["onclave_source_git_sha"],
        "onclave_core_rollout_image_repository": pins["onclave_core_image_repository"],
        "onclave_core_rollout_image_tag": pins["onclave_core_image_tag"],
        "onclave_core_rollout_image_digest": pins["onclave_core_image_digest"],
        "onclave_core_rollout_health_path": health_path,
        "onclave_core_rollout_compatible_installed_health_paths": list(
            compatible_installed_health_paths
        ),
        "onclave_core_rollout_compatible_installed_revisions": list(compatible_installed_revisions),
        "onclave_core_rollout_result_path": str(result_path),
    }
    command = [
        "ansible-playbook",
        "-i",
        str(values_dir / "ansible" / "inventory" / "local.yml"),
        "-i",
        "infra/ansible/inventory/tfvars.py",
        "infra/ansible/playbooks/onclave-core-rollout.yml",
        "-e",
        json.dumps(extra, separators=(",", ":")),
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        result_path.unlink(missing_ok=True)
        raise RolloutError(f"Onclave core playbook failed in {mode} mode")
    try:
        evidence = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RolloutError(f"Onclave core playbook returned no valid {mode} evidence") from error
    finally:
        result_path.unlink(missing_ok=True)
    if not isinstance(evidence, dict):
        raise RolloutError(f"Onclave core playbook returned invalid {mode} evidence")
    return evidence


def update_bws_inventory(
    expected_pins: Mapping[str, str],
    replacement_pins: Mapping[str, str],
    bws,
) -> tuple[str, str]:
    settings = REPO / "settings.local.json"
    locator = bws.load_locator(settings)
    records = bws.list_bws_records_with_ids(locator, os.environ.get("BITWARDEN_ACCESS_KEY", ""))
    record = records.get(INVENTORY_FAMILY)
    if record is None:
        raise RolloutError(f"BWS is missing {INVENTORY_FAMILY}")
    secret_id, current = record
    manifest = bws.load_manifest()
    family = next(family for family in manifest.families if family.key == INVENTORY_FAMILY)
    current_text = bws.decode_family(family, current)

    def parse(text: str, key: str):
        return bws.parse_yaml(text, key)

    if pin_values(current_text, parse) != dict(expected_pins):
        raise RolloutError("BWS Onclave pins changed during rollout; refusing overwrite")
    replacement_text = update_inventory_pins(current_text, replacement_pins)
    assert_only_pins_changed(current_text, replacement_text, parse)
    replacement = bws.encode_family(family, replacement_text)
    bws.edit_bws_secret(
        locator,
        os.environ.get("BITWARDEN_ACCESS_KEY", ""),
        secret_id,
        INVENTORY_FAMILY,
        replacement,
    )
    return current, replacement


def restore_bws_inventory(old: str, desired: str, bws) -> None:
    settings = REPO / "settings.local.json"
    locator = bws.load_locator(settings)
    records = bws.list_bws_records_with_ids(locator, os.environ.get("BITWARDEN_ACCESS_KEY", ""))
    record = records.get(INVENTORY_FAMILY)
    if record is None:
        raise RolloutError(f"BWS is missing {INVENTORY_FAMILY}")
    secret_id, current = record
    if current == old:
        return
    if current != desired:
        raise RolloutError("BWS inventory changed after pin update; refusing rollback overwrite")
    bws.edit_bws_secret(
        locator,
        os.environ.get("BITWARDEN_ACCESS_KEY", ""),
        secret_id,
        INVENTORY_FAMILY,
        old,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--core-digest")
    parser.add_argument("--record-dir", type=Path, default=Path(".tmp/onclave-core-rollout"))
    args = parser.parse_args(argv)
    lock_handle = acquire_rollout_lock(args.record_dir)
    if not SHA_RE.fullmatch(args.source_sha):
        lock_handle.close()
        parser.error("--source-sha must be a 40-character lowercase commit SHA")
    if args.core_digest and not DIGEST_RE.fullmatch(args.core_digest):
        lock_handle.close()
        parser.error("--core-digest must be sha256:<64 lowercase hex characters>")

    values_dir = Path(os.environ.get("VALUES_DIR", ""))
    if not values_dir.is_dir():
        raise RolloutError("run-infra did not provide a BWS snapshot VALUES_DIR")
    inventory_path = values_dir / "ansible" / "inventory" / "local.yml"
    inventory_before = inventory_path.read_text(encoding="utf-8")
    bws = load_module("onclave_core_bws_snapshot", REPO / "scripts" / "bws-snapshot.py")

    def parser_yaml(text: str, key: str):
        return bws.parse_yaml(text, key)

    previous = pin_values(inventory_before, parser_yaml)
    variables = inventory_vars(inventory_before, parser_yaml)
    repository = str(variables["onclave_core_image_repository"])
    resolved_digest = derive_digest_from_response(repository, args.source_sha)
    if args.core_digest is not None and args.core_digest != resolved_digest:
        raise RolloutError("provided core digest does not match the source SHA tag")
    digest = resolved_digest
    urls = source_urls(previous["onclave_app_definition_url"], args.source_sha)
    headers = {"User-Agent": "homelab-infra-onclave-core-rollout/1.0"}
    compose = fetch_url(urls["onclave_app_definition_url"], headers)
    backup = fetch_url(urls["backup-postgres.sh"], headers)
    restore = fetch_url(urls["restore-postgres.sh"], headers)
    if b"onclave-core" not in compose or not backup or not restore:
        raise RolloutError("Onclave source artifacts do not contain the required core/helper files")
    previous_urls = source_urls(
        previous["onclave_app_definition_url"], previous["onclave_source_git_sha"]
    )
    previous_artifacts = {
        "compose.yaml": fetch_url(previous_urls["onclave_app_definition_url"], headers),
        "backup-postgres.sh": fetch_url(previous_urls["backup-postgres.sh"], headers),
        "restore-postgres.sh": fetch_url(previous_urls["restore-postgres.sh"], headers),
    }
    desired_artifacts = {
        "compose.yaml": compose,
        "backup-postgres.sh": backup,
        "restore-postgres.sh": restore,
    }
    previous_health_path, desired_health_path = compatible_artifact_transition(
        previous_artifacts,
        desired_artifacts,
        bws.parse_yaml,
    )
    contract: dict[str, object] = {
        "previous_health_path": previous_health_path,
        "desired_health_path": desired_health_path,
        "compose_exception": (
            "none"
            if previous_health_path == desired_health_path
            else "exact_one_way_health_to_live"
        ),
    }
    desired = dict(previous)
    desired.update(
        {
            "onclave_source_git_sha": args.source_sha,
            "onclave_app_definition_url": urls["onclave_app_definition_url"],
            "onclave_app_definition_sha256": checksum(compose),
            "onclave_backup_script_sha256": checksum(backup),
            "onclave_restore_script_sha256": checksum(restore),
            "onclave_core_image_tag": args.source_sha,
            "onclave_core_image_digest": digest,
        }
    )
    inventory_after = update_inventory_pins(inventory_before, desired)
    assert_only_pins_changed(inventory_before, inventory_after, parser_yaml)
    if desired == previous:
        print("Onclave core pins already match; no deployment performed.")
        return 0

    record = record_path(args.record_dir)
    write_record(record, "planned", previous, desired, contract)
    inventory_path.write_text(inventory_after, encoding="utf-8")
    old_encoded = ""
    new_encoded = ""
    bws_updated = False
    deployment_started = False
    try:
        old_encoded, new_encoded = update_bws_inventory(previous, desired, bws)
        bws_updated = True
        desired_playbook_pins = dict(desired)
        desired_playbook_pins["onclave_core_image_repository"] = repository
        deployment_started = True
        desired_evidence = run_playbook(
            "desired",
            values_dir,
            desired_playbook_pins,
            desired_health_path,
            [previous_health_path],
            [previous["onclave_source_git_sha"]],
        )
    except Exception as error:
        rollback_error = None
        if bws_updated:
            try:
                restore_bws_inventory(old_encoded, new_encoded, bws)
            except Exception as restore_error:
                # Report both boundaries without hiding the first failure.
                rollback_error = restore_error
        inventory_path.write_text(inventory_before, encoding="utf-8")
        if deployment_started:
            try:
                old_playbook_pins = dict(previous)
                old_playbook_pins["onclave_core_image_repository"] = repository
                rollback_evidence = run_playbook(
                    "rollback",
                    values_dir,
                    old_playbook_pins,
                    previous_health_path,
                    [previous_health_path, desired_health_path],
                    [previous["onclave_source_git_sha"], desired["onclave_source_git_sha"]],
                )
            except Exception as redeploy_error:
                rollback_error = rollback_error or redeploy_error
        rollback_status = "rolled_back" if rollback_error is None else "rollback-failed"
        rollback_operation = (
            {"rollback": rollback_evidence}
            if deployment_started and rollback_error is None
            else None
        )
        write_record(
            record,
            rollback_status,
            previous,
            desired,
            contract,
            rollback_operation,
        )
        detail = f"Onclave core rollout failed and rollback was attempted: {error}"
        if rollback_error is not None:
            detail += f"; rollback failure: {rollback_error}"
        raise RolloutError(detail) from error

    write_record(
        record,
        "succeeded",
        previous,
        desired,
        contract,
        {"desired": desired_evidence},
    )
    print(f"Onclave core rollout succeeded; previous pins recorded at {record}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as error:
        print(f"Onclave core rollout failed: {error}", file=sys.stderr)
        raise SystemExit(1)

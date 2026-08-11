#!/usr/bin/env python3
"""Resolve validated homelab configuration snapshots from BWS."""

from __future__ import annotations

import argparse
import base64
import gzip
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import settings  # noqa: E402

try:
    import hcl2
except ImportError:  # pragma: no cover - exercised by local focused tests
    hcl2 = None

ENV_PARSER_SPEC = importlib.util.spec_from_file_location(
    "bws_snapshot_parse_env", SCRIPTS / "parse-env.py"
)
assert ENV_PARSER_SPEC and ENV_PARSER_SPEC.loader
parse_env_script = importlib.util.module_from_spec(ENV_PARSER_SPEC)
ENV_PARSER_SPEC.loader.exec_module(parse_env_script)

DEFAULT_MANIFEST = REPO / "config" / "bws-routing.json"
DEFAULT_SETTINGS = Path("settings.local.json")
FAMILY_KEYS = (
    "HOMELAB_ENV",
    "HOMELAB_TERRAFORM_TFVARS",
    "HOMELAB_ANSIBLE_INVENTORY",
    "HOMELAB_DNS_RECORDS",
    "HOMELAB_SETTINGS",
)
RUNTIME_KEYS = (
    "SEAWEEDFS_S3_ACCESS_KEY",
    "SEAWEEDFS_S3_SECRET_KEY",
    "HOMELAB_TOFU_STATE_PASSPHRASE",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
)
RUNTIME_PROFILES = {
    "config": (),
    "backend": RUNTIME_KEYS[:3],
    "seaweedfs": RUNTIME_KEYS[:2],
    "onclave": RUNTIME_KEYS[3:],
    "all": RUNTIME_KEYS,
}
PLACEHOLDER_RE = re.compile(r"(?:REPLACE(?:_WITH)?_[A-Z0-9_]+|CHANGEME|TODO)")
Runner = Callable[[Sequence[str], Mapping[str, str]], subprocess.CompletedProcess[str]]


class BwsSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class Locator:
    project_id: str
    api_server: str


@dataclass(frozen=True)
class Family:
    key: str
    path: PurePosixPath
    format: str
    encoding: str


@dataclass(frozen=True)
class RoutingManifest:
    families: tuple[Family, ...]
    runtime_keys: tuple[str, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BwsSnapshotError("JSON contains duplicate keys")
        result[key] = value
    return result


def parse_json(text: str, key: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, BwsSnapshotError) as error:
        raise BwsSnapshotError(f"{key} is not valid JSON") from error


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in mapping:
                raise BwsSnapshotError("YAML contains duplicate keys")
        except TypeError as error:
            raise BwsSnapshotError("YAML mapping keys must be scalar") from error
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def parse_yaml(text: str, key: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, BwsSnapshotError) as error:
        raise BwsSnapshotError(f"{key} is not valid YAML") from error


def require_text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip() or PLACEHOLDER_RE.search(value):
        raise BwsSnapshotError(f"{key} is missing, empty, or a placeholder")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST) -> RoutingManifest:
    try:
        data = parse_json(path.read_text(encoding="utf-8"), "routing manifest")
    except OSError as error:
        raise BwsSnapshotError("routing manifest cannot be read") from error
    if not isinstance(data, dict) or set(data) != {"families", "runtime_keys"}:
        raise BwsSnapshotError("routing manifest has an invalid schema")
    raw_families = data["families"]
    if not isinstance(raw_families, dict) or tuple(raw_families) != FAMILY_KEYS:
        raise BwsSnapshotError("routing manifest has invalid family keys")
    families: list[Family] = []
    expected_paths = (
        "values/.env",
        "values/terraform.tfvars",
        "values/ansible/inventory/local.yml",
        "values/dns-records.local.json",
        "settings.local.json",
    )
    expected_formats = ("dotenv", "hcl", "yaml", "json", "settings")
    for key, expected_path, expected_format in zip(
        FAMILY_KEYS, expected_paths, expected_formats
    ):
        item = raw_families[key]
        if not isinstance(item, dict) or set(item) != {"path", "format", "encoding"}:
            raise BwsSnapshotError("routing manifest has an invalid family entry")
        expected_encoding = (
            "gzip-base64" if key == "HOMELAB_ANSIBLE_INVENTORY" else "text"
        )
        if (
            item["path"] != expected_path
            or item["format"] != expected_format
            or item["encoding"] != expected_encoding
        ):
            raise BwsSnapshotError("routing manifest has an invalid family route")
        relative_path = PurePosixPath(item["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise BwsSnapshotError("routing manifest has an unsafe output path")
        families.append(Family(key, relative_path, expected_format, expected_encoding))
    runtime_keys = data["runtime_keys"]
    if not isinstance(runtime_keys, list) or tuple(runtime_keys) != RUNTIME_KEYS:
        raise BwsSnapshotError("routing manifest has invalid runtime keys")
    return RoutingManifest(tuple(families), tuple(runtime_keys))


def load_locator(path: Path) -> Locator:
    try:
        data = parse_json(path.read_text(encoding="utf-8"), "settings")
    except OSError as error:
        raise BwsSnapshotError("BWS settings cannot be read") from error
    if not isinstance(data, dict) or not isinstance(data.get("bws"), dict):
        raise BwsSnapshotError("settings.bws is required")
    bws = data["bws"]
    if set(bws) != {"project_id", "api_server"}:
        raise BwsSnapshotError("settings.bws has an invalid schema")
    project_id = require_text(bws["project_id"], "settings.bws.project_id")
    api_server = require_text(bws["api_server"], "settings.bws.api_server").rstrip("/")
    parsed = urlparse(api_server)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BwsSnapshotError("settings.bws.api_server is invalid")
    return Locator(project_id, api_server)


def bws_environment(locator: Locator, access_key: str) -> dict[str, str]:
    if not access_key:
        raise BwsSnapshotError("BITWARDEN_ACCESS_KEY is missing")
    return {
        **os.environ,
        "BWS_ACCESS_TOKEN": access_key,
        "BWS_SERVER_URL": locator.api_server.removesuffix("/api"),
    }


def subprocess_runner(
    command: Sequence[str], environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env=dict(environment),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def list_bws_secrets(
    locator: Locator, access_key: str, runner: Runner = subprocess_runner
) -> dict[str, str]:
    result = runner(
        ("bws", "secret", "list", locator.project_id, "--output", "json"),
        bws_environment(locator, access_key),
    )
    if result.returncode != 0:
        raise BwsSnapshotError("BWS secret listing failed")
    try:
        records = parse_json(result.stdout, "BWS response")
    except BwsSnapshotError as error:
        raise BwsSnapshotError("BWS returned an invalid secret list") from error
    if not isinstance(records, list):
        raise BwsSnapshotError("BWS returned an invalid secret list")
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise BwsSnapshotError("BWS returned an invalid secret list")
        name = record.get("key")
        value = record.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise BwsSnapshotError("BWS returned an invalid secret list")
        if name in values:
            duplicates.add(name)
        values[name] = value
    if duplicates:
        raise BwsSnapshotError(
            "BWS has duplicate secret keys: " + ", ".join(sorted(duplicates))
        )
    return values


def list_bws_records_with_ids(
    locator: Locator, access_key: str, runner: Runner = subprocess_runner
) -> dict[str, tuple[str, str]]:
    result = runner(
        ("bws", "secret", "list", locator.project_id, "--output", "json"),
        bws_environment(locator, access_key),
    )
    if result.returncode != 0:
        raise BwsSnapshotError("BWS secret listing failed")
    records = parse_json(result.stdout, "BWS response")
    if not isinstance(records, list):
        raise BwsSnapshotError("BWS returned an invalid secret list")
    values: dict[str, tuple[str, str]] = {}
    duplicates: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise BwsSnapshotError("BWS returned an invalid secret list")
        name = record.get("key")
        value = record.get("value")
        secret_id = record.get("id")
        if not all(isinstance(item, str) and item for item in (name, secret_id)):
            raise BwsSnapshotError("BWS returned an invalid secret list")
        if not isinstance(value, str):
            raise BwsSnapshotError("BWS returned an invalid secret list")
        if name in values:
            duplicates.add(name)
        values[name] = (secret_id, value)
    if duplicates:
        raise BwsSnapshotError(
            "BWS has duplicate secret keys: " + ", ".join(sorted(duplicates))
        )
    return values


def resolve_required(values: Mapping[str, str], keys: Sequence[str]) -> dict[str, str]:
    missing = [key for key in keys if key not in values]
    empty = [key for key in keys if key in values and not values[key].strip()]
    placeholders = [
        key for key in keys if key in values and PLACEHOLDER_RE.search(values[key])
    ]
    if missing or empty or placeholders:
        details: list[str] = []
        if missing:
            details.append("missing keys: " + ", ".join(missing))
        if empty:
            details.append("empty keys: " + ", ".join(empty))
        if placeholders:
            details.append("placeholder keys: " + ", ".join(placeholders))
        raise BwsSnapshotError("BWS secrets are invalid: " + "; ".join(details))
    return {key: values[key] for key in keys}


def validate_dotenv(text: str, key: str) -> None:
    with tempfile.TemporaryDirectory(prefix="bws-snapshot-env-") as directory:
        path = Path(directory) / ".env"
        path.write_text(text, encoding="utf-8")
        try:
            parse_env_script.parse_env(path)
        except parse_env_script.EnvError as error:
            raise BwsSnapshotError(f"{key} is not valid dotenv") from error


def validate_hcl(text: str, key: str) -> None:
    if hcl2 is None:
        raise BwsSnapshotError("python-hcl2 is required for HCL validation")
    try:
        hcl2.loads(text)
    except Exception as error:
        raise BwsSnapshotError(f"{key} is not valid HCL") from error


def validate_settings(text: str, key: str) -> None:
    data = parse_json(text, key)
    if not isinstance(data, dict):
        raise BwsSnapshotError(f"{key} must be a JSON object")
    validator_data = dict(data)
    validator_data.pop("bws", None)
    with tempfile.TemporaryDirectory(prefix="bws-snapshot-settings-") as directory:
        path = Path(directory) / "settings.local.json"
        path.write_text(json.dumps(validator_data), encoding="utf-8")
        try:
            settings.load_settings(path)
        except settings.SettingsError as error:
            raise BwsSnapshotError(f"{key} is not valid settings") from error


def encode_family(family: Family, text: str) -> str:
    if family.encoding == "text":
        return text
    if family.encoding == "gzip-base64":
        compressed = gzip.compress(text.encode("utf-8"), mtime=0)
        return base64.b64encode(compressed).decode("ascii")
    raise BwsSnapshotError("routing manifest has an unknown family encoding")


def decode_family(family: Family, value: str) -> str:
    if family.encoding == "text":
        return value
    if family.encoding == "gzip-base64":
        try:
            compressed = base64.b64decode(value, validate=True)
            return gzip.decompress(compressed).decode("utf-8")
        except (ValueError, OSError, UnicodeDecodeError) as error:
            raise BwsSnapshotError(f"{family.key} has invalid encoding") from error
    raise BwsSnapshotError("routing manifest has an unknown family encoding")


def validate_family(family: Family, text: str) -> Any:
    require_text(text, family.key)
    if family.format == "dotenv":
        validate_dotenv(text, family.key)
        return None
    if family.format == "hcl":
        validate_hcl(text, family.key)
        return None
    if family.format == "yaml":
        return parse_yaml(text, family.key)
    if family.format == "json":
        return parse_json(text, family.key)
    if family.format == "settings":
        validate_settings(text, family.key)
        return parse_json(text, family.key)
    raise BwsSnapshotError("routing manifest has an unknown family format")


def validate_families(
    manifest: RoutingManifest, values: Mapping[str, str]
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for family in manifest.families:
        parsed[family.key] = validate_family(family, values[family.key])
    return parsed


def inventory_backend_values(inventory: Any) -> dict[str, str]:
    if not isinstance(inventory, dict):
        raise BwsSnapshotError("HOMELAB_ANSIBLE_INVENTORY must contain an object")
    all_group = inventory.get("all")
    if not isinstance(all_group, dict) or not isinstance(all_group.get("vars"), dict):
        raise BwsSnapshotError("HOMELAB_ANSIBLE_INVENTORY must contain all.vars")
    variables = all_group["vars"]
    names = {
        "endpoint": "seaweedfs_s3_endpoint",
        "bucket": "seaweedfs_s3_bucket",
        "key": "seaweedfs_s3_key",
        "region": "seaweedfs_s3_region",
    }
    resolved: dict[str, str] = {}
    for output_name, variable_name in names.items():
        value = variables.get(variable_name)
        if (
            not isinstance(value, str)
            or not value.strip()
            or PLACEHOLDER_RE.search(value)
        ):
            raise BwsSnapshotError(
                "HOMELAB_ANSIBLE_INVENTORY is missing required SeaweedFS vars"
            )
        resolved[output_name] = value
    endpoint = urlparse(resolved["endpoint"])
    if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
        raise BwsSnapshotError(
            "HOMELAB_ANSIBLE_INVENTORY has an invalid SeaweedFS endpoint"
        )
    return resolved


def backend_hcl(inventory: Any) -> str:
    values = inventory_backend_values(inventory)
    return "\n".join(
        (
            f"bucket = {json.dumps(values['bucket'])}",
            f"key = {json.dumps(values['key'])}",
            f"region = {json.dumps(values['region'])}",
            "endpoints = {",
            f"  s3 = {json.dumps(values['endpoint'])}",
            "}",
            "use_path_style = true",
            "use_lockfile = true",
            "skip_credentials_validation = true",
            "skip_metadata_api_check = true",
            "skip_region_validation = true",
            "skip_requesting_account_id = true",
            "skip_s3_checksum = true",
            "",
        )
    )


def tofu_encryption(passphrase: str) -> str:
    if "\x00" in passphrase or "\n" in passphrase or "\r" in passphrase:
        raise BwsSnapshotError("HOMELAB_TOFU_STATE_PASSPHRASE is invalid")
    quoted = json.dumps(passphrase)
    return "\n".join(
        (
            'key_provider "pbkdf2" "state" {',
            f"  passphrase = {quoted}",
            "}",
            'method "aes_gcm" "state" {',
            "  keys = key_provider.pbkdf2.state",
            "}",
            "state {",
            "  method = method.aes_gcm.state",
            "  enforced = true",
            "}",
            "plan {",
            "  method = method.aes_gcm.state",
            "  enforced = true",
            "}",
        )
    )


def docker_env_value(value: str, key: str) -> str:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise BwsSnapshotError(f"{key} cannot be used in a Docker env file")
    return value.replace("$", "$$")


def runtime_env(output: Path, runtime: Mapping[str, str]) -> str:
    output = output.resolve()
    values: dict[str, str] = dict(runtime)
    if "SEAWEEDFS_S3_ACCESS_KEY" in runtime:
        values.update(
            {
                "AWS_ACCESS_KEY_ID": runtime["SEAWEEDFS_S3_ACCESS_KEY"],
                "AWS_SECRET_ACCESS_KEY": runtime["SEAWEEDFS_S3_SECRET_KEY"],
                "AWS_ACCESS_KEY": runtime["SEAWEEDFS_S3_ACCESS_KEY"],
                "AWS_SECRET_KEY": runtime["SEAWEEDFS_S3_SECRET_KEY"],
            }
        )
    if "HOMELAB_TOFU_STATE_PASSPHRASE" in runtime:
        encryption = tofu_encryption(runtime["HOMELAB_TOFU_STATE_PASSPHRASE"])
        values["TF_ENCRYPTION_B64"] = base64.b64encode(
            encryption.encode("utf-8")
        ).decode("ascii")
    values.update(
        {
            "VALUES_DIR": str(output / "values"),
            "INFRA_SETTINGS_FILE": str(output / "settings.local.json"),
            "ANSIBLE_TFVARS_FILE": str(output / "values" / "terraform.tfvars"),
            "DNS_RECORDS_FILE": str(output / "values" / "dns-records.local.json"),
            "INFRA_BACKEND_CONFIG": str(output / "backend.hcl"),
        }
    )
    return (
        "\n".join(
            f"{key}={docker_env_value(value, key)}" for key, value in values.items()
        )
        + "\n"
    )


def write_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def render_snapshot(
    output: Path,
    manifest: RoutingManifest,
    values: Mapping[str, str],
    runtime_keys: Sequence[str] = RUNTIME_KEYS,
) -> None:
    required = resolve_required(values, FAMILY_KEYS + tuple(runtime_keys))
    decoded = {
        family.key: decode_family(family, required[family.key])
        for family in manifest.families
    }
    parsed = validate_families(manifest, decoded)
    if output.exists():
        raise BwsSnapshotError("snapshot output already exists")
    try:
        output.mkdir(mode=0o700, parents=True)
        output.chmod(0o700)
        for family in manifest.families:
            write_private_file(output.joinpath(*family.path.parts), decoded[family.key])
        write_private_file(
            output / "backend.hcl", backend_hcl(parsed["HOMELAB_ANSIBLE_INVENTORY"])
        )
        runtime = {key: required[key] for key in runtime_keys}
        write_private_file(output / "runtime.env", runtime_env(output, runtime))
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def read_source_values(root: Path, manifest: RoutingManifest) -> dict[str, str]:
    raw_values: dict[str, str] = {}
    for family in manifest.families:
        path = root.joinpath(*family.path.parts)
        try:
            raw_values[family.key] = path.read_text(encoding="utf-8")
        except OSError as error:
            raise BwsSnapshotError(
                f"{family.key} source file cannot be read"
            ) from error
    validate_families(manifest, raw_values)
    return {
        family.key: encode_family(family, raw_values[family.key])
        for family in manifest.families
    }


def compare_source_values(
    source: Mapping[str, str], existing: Mapping[str, str], manifest: RoutingManifest
) -> dict[str, str]:
    return {
        family.key: (
            "missing"
            if family.key not in existing
            else "match"
            if existing[family.key] == source[family.key]
            else "conflict"
        )
        for family in manifest.families
    }


def create_bws_secret(
    locator: Locator,
    access_key: str,
    key: str,
    value: str,
    runner: Runner = subprocess_runner,
) -> None:
    result = runner(
        ("bws", "secret", "create", key, value, locator.project_id),
        bws_environment(locator, access_key),
    )
    if result.returncode != 0:
        raise BwsSnapshotError(f"BWS could not create {key}")


def command_render(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    locator = load_locator(args.settings)
    values = list_bws_secrets(
        locator, os.environ.get("BITWARDEN_ACCESS_KEY", ""), args.runner
    )
    render_snapshot(
        args.output, manifest, values, RUNTIME_PROFILES[args.runtime_profile]
    )
    print("BWS snapshot rendered")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    source = read_source_values(args.source_root, manifest)
    locator = load_locator(args.settings)
    existing = list_bws_secrets(
        locator, os.environ.get("BITWARDEN_ACCESS_KEY", ""), args.runner
    )
    statuses = compare_source_values(source, existing, manifest)
    for key, status in statuses.items():
        print(f"{key}: {status}")
    return 0 if all(status == "match" for status in statuses.values()) else 1


def edit_bws_secret(
    locator: Locator,
    access_key: str,
    secret_id: str,
    key: str,
    value: str,
    runner: Runner = subprocess_runner,
) -> None:
    result = runner(
        ("bws", "secret", "edit", secret_id, "--value", value, "--output", "none"),
        bws_environment(locator, access_key),
    )
    if result.returncode != 0:
        raise BwsSnapshotError(f"BWS could not update {key}")


def command_sync(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    source = read_source_values(args.source_root, manifest)
    locator = load_locator(args.settings)
    access_key = os.environ.get("BITWARDEN_ACCESS_KEY", "")
    records = list_bws_records_with_ids(locator, access_key, args.runner)
    missing = [family.key for family in manifest.families if family.key not in records]
    if missing:
        raise BwsSnapshotError(
            "BWS is missing required family keys: " + ", ".join(missing)
        )
    for family in manifest.families:
        secret_id, current = records[family.key]
        if current == source[family.key]:
            print(f"{family.key}: match")
            continue
        edit_bws_secret(
            locator,
            access_key,
            secret_id,
            family.key,
            source[family.key],
            args.runner,
        )
        print(f"{family.key}: updated")
    return 0


def command_seed(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    source = read_source_values(args.source_root, manifest)
    locator = load_locator(args.settings)
    access_key = os.environ.get("BITWARDEN_ACCESS_KEY", "")
    existing = list_bws_secrets(locator, access_key, args.runner)
    statuses = compare_source_values(source, existing, manifest)
    conflicts = [key for key, status in statuses.items() if status == "conflict"]
    if conflicts:
        for key, status in statuses.items():
            print(f"{key}: {status}")
        return 1
    for key, status in statuses.items():
        if status == "missing":
            create_bws_secret(locator, access_key, key, source[key], args.runner)
            statuses[key] = "created"
    for key, status in statuses.items():
        print(f"{key}: {status}")
    return 0


def main(argv: Optional[list[str]] = None, runner: Runner = subprocess_runner) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render")
    render.add_argument("--output", type=Path, required=True)
    render.add_argument(
        "--runtime-profile", choices=tuple(RUNTIME_PROFILES), default="all"
    )
    seed = subparsers.add_parser("seed")
    seed.add_argument("--source-root", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--source-root", type=Path, required=True)
    sync = subparsers.add_parser("sync")
    sync.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args(argv)
    args.runner = runner
    try:
        if args.command == "render":
            return command_render(args)
        if args.command == "seed":
            return command_seed(args)
        if args.command == "sync":
            return command_sync(args)
        return command_verify(args)
    except BwsSnapshotError as error:
        print(f"BWS snapshot failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

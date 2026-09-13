#!/usr/bin/env python3
"""Create and restore-test a deterministic private SeaweedFS object backup."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError


class BackupError(RuntimeError):
    pass


def s3(endpoint: str, region: str) -> Any:
    access = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not access or not secret:
        raise BackupError("SeaweedFS credentials are missing from the environment")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def list_entries(client: Any, bucket: str) -> list[str]:
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        keys.extend(str(item["Key"]) for item in page.get("Contents", []))
    return sorted(keys)


def read_object(client: Any, bucket: str, key: str) -> tuple[bytes, dict[str, Any]]:
    response = client.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read()
    return content, {
        "key": key,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content_type": str(response.get("ContentType") or "application/octet-stream"),
        "metadata": dict(response.get("Metadata") or {}),
    }


def require_quiescence(marker: str | None) -> None:
    if not marker or not Path(marker).is_file():
        raise BackupError(
            "an orchestration-owned quiescence marker is required for the final corpus backup"
        )


def validate_restore_bucket(bucket: str) -> None:
    if bucket == "menos" or not bucket.startswith("menos-restore-test-"):
        raise BackupError(
            "restore-test requires an isolated menos-restore-test-* bucket"
        )


def backup(
    client: Any, bucket: str, output: Path, quiesced_marker: str | None = None
) -> dict[str, Any]:
    require_quiescence(quiesced_marker)
    if output.exists():
        raise BackupError(f"refusing to overwrite existing backup artifact: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    objects: list[tuple[str, bytes]] = []
    for index, key in enumerate(list_entries(client, bucket)):
        content, entry = read_object(client, bucket, key)
        entry["archive_name"] = f"objects/{index:08d}"
        entries.append(entry)
        objects.append((entry["archive_name"], content))
    manifest = {
        "schema_version": 1,
        "kind": "seaweedfs-application-objects",
        "bucket": bucket,
        "objects": entries,
        "summary": {
            "objects": len(entries),
            "bytes": sum(int(entry["bytes"]) for entry in entries),
            "sha256": hashlib.sha256(
                "".join(f"{e['key']}\0{e['bytes']}\0{e['sha256']}\n" for e in entries).encode()
            ).hexdigest(),
        },
    }
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            raw = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo("MANIFEST.json")
            info.size = len(raw)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(raw))
            for name, content in objects:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(content))
        temporary.replace(output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    try:
        output.chmod(0o600)
    except OSError:
        pass
    return manifest["summary"]


def restore_test(client: Any, archive_path: Path, bucket: str, cleanup: bool) -> dict[str, Any]:
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest_member = archive.getmember("MANIFEST.json")
        manifest = json.loads(archive.extractfile(manifest_member).read())  # type: ignore[union-attr]
        if manifest.get("kind") != "seaweedfs-application-objects":
            raise BackupError("archive is not a SeaweedFS application-object backup")
        try:
            client.head_bucket(Bucket=bucket)
            if list_entries(client, bucket):
                raise BackupError("restore-test bucket must be empty")
        except ClientError:
            client.create_bucket(Bucket=bucket)
        for entry in manifest["objects"]:
            member = archive.getmember(entry["archive_name"])
            content = archive.extractfile(member).read()  # type: ignore[union-attr]
            if hashlib.sha256(content).hexdigest() != entry["sha256"] or len(content) != entry["bytes"]:
                raise BackupError("backup object digest validation failed")
            client.put_object(
                Bucket=bucket,
                Key=entry["key"],
                Body=content,
                ContentType=entry["content_type"],
                Metadata=entry.get("metadata") or {},
            )
        actual: list[dict[str, Any]] = []
        for key in list_entries(client, bucket):
            content, entry = read_object(client, bucket, key)
            del content
            actual.append(entry)
        expected = [
            {key: entry[key] for key in ("key", "bytes", "sha256", "content_type", "metadata")}
            for entry in manifest["objects"]
        ]
        if actual != expected:
            raise BackupError("restored object corpus does not match the backup manifest")
        if cleanup:
            for key in list_entries(client, bucket):
                client.delete_object(Bucket=bucket, Key=key)
        return manifest["summary"]


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("command", choices=("backup", "restore-test"))
    command.add_argument("--endpoint", required=True)
    command.add_argument("--region", default="us-east-1")
    command.add_argument("--bucket", default="menos")
    command.add_argument("--output", type=Path)
    command.add_argument("--archive", type=Path)
    command.add_argument("--restore-bucket", default="")
    command.add_argument("--keep-restore-bucket", action="store_true")
    command.add_argument(
        "--quiesced-marker",
        help="private marker created by the orchestration after stopping Onclave writes",
    )
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        client = s3(args.endpoint, args.region)
        if args.command == "backup":
            if args.output is None:
                raise BackupError("--output is required for backup")
            print(
                json.dumps(
                    backup(client, args.bucket, args.output, args.quiesced_marker),
                    sort_keys=True,
                )
            )
        else:
            if args.archive is None:
                raise BackupError("--archive is required for restore-test")
            restore_bucket = args.restore_bucket or f"menos-restore-test-{secrets.token_hex(6)}"
            validate_restore_bucket(restore_bucket)
            print(json.dumps(restore_test(client, args.archive, restore_bucket, not args.keep_restore_bucket), sort_keys=True))
        return 0
    except (BackupError, BotoCoreError, ClientError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"SeaweedFS object backup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

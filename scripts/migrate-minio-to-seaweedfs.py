#!/usr/bin/env python3
"""Resumable copy and verify an S3 object corpus without changing the source.

The source and destination credentials are read from environment variables.  The
final phase is deliberately fail-closed: callers must create a private
quiescence marker owned by the cutover orchestration before taking the final
source inventory.  Output contains counts and digests, never object contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError


class MigrationError(RuntimeError):
    pass


def client(endpoint: str, region: str, access_env: str, secret_env: str) -> Any:
    access = os.environ.get(access_env, "")
    secret = os.environ.get(secret_env, "")
    if not access or not secret:
        raise MigrationError(f"credentials are missing from {access_env}/{secret_env}")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 10, "mode": "standard"},
            s3={"addressing_style": "path"},
        ),
    )


def objects(s3: Any, bucket: str) -> Iterable[dict[str, Any]]:
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        yield from page.get("Contents", [])


def object_digest(s3: Any, bucket: str, key: str) -> tuple[int, str, str, dict[str, str]]:
    response = s3.get_object(Bucket=bucket, Key=key)
    digest = hashlib.sha256()
    size = 0
    with response["Body"] as body:
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return (
        size,
        digest.hexdigest(),
        str(response.get("ContentType") or "application/octet-stream"),
        dict(response.get("Metadata") or {}),
    )


def inventory(s3: Any, bucket: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for listed in objects(s3, bucket):
        key = str(listed["Key"])
        size, digest, content_type, metadata = object_digest(s3, bucket, key)
        result.append(
            {
                "key": key,
                "bytes": size,
                "sha256": digest,
                "content_type": content_type,
                "metadata": metadata,
            }
        )
    return sorted(result, key=lambda item: item["key"])


def summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = "".join(
        f"{item['key']}\0{item['bytes']}\0{item['sha256']}\n" for item in entries
    ).encode("utf-8")
    return {
        "objects": len(entries),
        "bytes": sum(int(item["bytes"]) for item in entries),
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def has_object_parity(source: list[dict[str, Any]], destination: list[dict[str, Any]]) -> bool:
    """Compare the preserved migration contract, not backend-inferred MIME types."""
    return summary(source) == summary(destination)


def write_artifact(
    path: Path, source: list[dict[str, Any]], destination: list[dict[str, Any]] | None = None
) -> None:
    payload = {
        "schema_version": 1,
        "source": {**summary(source), "objects": source},
    }
    if destination is not None:
        payload["destination"] = {**summary(destination), "objects": destination}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def copy_one(
    source: Any, destination: Any, source_bucket: str, destination_bucket: str, key: str
) -> bool:
    size, digest, content_type, metadata = object_digest(source, source_bucket, key)
    try:
        (
            destination_size,
            destination_digest,
            destination_content_type,
            destination_metadata,
        ) = object_digest(destination, destination_bucket, key)
    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise
        destination_size, destination_digest = -1, ""
        destination_content_type, destination_metadata = "", {}
    if (
        destination_size == size
        and destination_digest == digest
        and destination_content_type == content_type
        and destination_metadata == metadata
    ):
        return False

    response = source.get_object(Bucket=source_bucket, Key=key)
    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as body:
        while True:
            chunk = response["Body"].read(1024 * 1024)
            if not chunk:
                break
            body.write(chunk)
        body.seek(0)
        destination.put_object(
            Bucket=destination_bucket,
            Key=key,
            Body=body,
            ContentLength=size,
            ContentType=content_type,
            Metadata=metadata,
        )
    return True


def copy_corpus(source: Any, destination: Any, source_bucket: str, destination_bucket: str) -> int:
    changed = 0
    for item in objects(source, source_bucket):
        if copy_one(source, destination, source_bucket, destination_bucket, str(item["Key"])):
            changed += 1
    return changed


def require_quiescence(marker: str | None) -> None:
    if marker and Path(marker).is_file():
        return
    raise MigrationError(
        "final migration requires a private quiescence marker created by orchestration"
    )


def require_fresh_artifact(path: Path | None) -> Path:
    if path is None:
        raise MigrationError("final migration requires a new --artifact path")
    if path.exists():
        raise MigrationError(f"refusing to overwrite existing parity artifact: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "copy", "parity", "finalize"))
    parser.add_argument("--source-endpoint", required=True)
    parser.add_argument("--destination-endpoint", required=True)
    parser.add_argument("--source-bucket", default="menos")
    parser.add_argument("--destination-bucket", default="menos")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--source-access-key-env", default="MINIO_ACCESS_KEY")
    parser.add_argument("--source-secret-key-env", default="MINIO_SECRET_KEY")
    parser.add_argument("--destination-access-key-env", default="AWS_ACCESS_KEY_ID")
    parser.add_argument("--destination-secret-key-env", default="AWS_SECRET_ACCESS_KEY")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--quiesced-marker")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = client(
            args.source_endpoint,
            args.region,
            args.source_access_key_env,
            args.source_secret_key_env,
        )
        destination = None
        if args.command != "inventory":
            destination = client(
                args.destination_endpoint,
                args.region,
                args.destination_access_key_env,
                args.destination_secret_key_env,
            )
        if args.command in {"inventory", "parity", "finalize"}:
            if args.command == "finalize":
                require_quiescence(args.quiesced_marker)
                require_fresh_artifact(args.artifact)
            source_inventory = inventory(source, args.source_bucket)
        else:
            source_inventory = []

        if args.command == "inventory":
            if args.artifact:
                write_artifact(args.artifact, source_inventory)
            print(json.dumps(summary(source_inventory), sort_keys=True))
            return 0

        if args.command in {"copy", "finalize"}:
            assert destination is not None
            changed = copy_corpus(source, destination, args.source_bucket, args.destination_bucket)
            if args.command == "copy":
                source_inventory = inventory(source, args.source_bucket)
            destination_inventory = inventory(destination, args.destination_bucket)
            if args.artifact:
                write_artifact(args.artifact, source_inventory, destination_inventory)
            if args.command == "copy":
                print(
                    json.dumps(
                        {"copied": changed, **summary(destination_inventory)}, sort_keys=True
                    )
                )
                return 0
        elif args.command == "parity":
            assert destination is not None
            destination_inventory = inventory(destination, args.destination_bucket)
        else:
            assert destination is not None
            destination_inventory = inventory(destination, args.destination_bucket)

        if args.artifact:
            write_artifact(args.artifact, source_inventory, destination_inventory)
        if not has_object_parity(source_inventory, destination_inventory):
            raise MigrationError(
                "source and destination object parity failed; see the private artifact"
            )
        print(json.dumps({"parity": "ok", **summary(source_inventory)}, sort_keys=True))
        return 0
    except (MigrationError, BotoCoreError, ClientError) as error:
        print(f"SeaweedFS migration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

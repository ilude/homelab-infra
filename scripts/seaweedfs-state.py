#!/usr/bin/env python3
"""Configure and verify the dedicated SeaweedFS OpenTofu state bucket."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class StateBucketError(RuntimeError):
    pass


def s3_client(endpoint: str, region: str) -> Any:
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not access_key or not secret_key:
        raise StateBucketError("SeaweedFS S3 credentials are missing")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def ensure_bucket(client: Any, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as error:
        if error_code(error) not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        client.create_bucket(Bucket=bucket)
    client.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )


def lifecycle_rules(
    state_key: str, state_noncurrent_days: int, lock_noncurrent_days: int
) -> list[dict[str, Any]]:
    return [
        {
            "ID": "retain-noncurrent-state",
            "Status": "Enabled",
            "Filter": {"Prefix": state_key},
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": state_noncurrent_days,
            },
        },
        {
            "ID": "expire-noncurrent-locks",
            "Status": "Enabled",
            "Filter": {"Prefix": f"{state_key}.tflock"},
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": lock_noncurrent_days,
            },
            "Expiration": {"ExpiredObjectDeleteMarker": True},
        },
    ]


def normalize_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for rule in rules:
        cleaned.append(
            {
                key: value
                for key, value in rule.items()
                if key not in {"ResponseMetadata"}
            }
        )
    return sorted(cleaned, key=lambda rule: str(rule.get("ID", "")))


def verify_versioning_and_lifecycle(
    client: Any, bucket: str, expected_rules: list[dict[str, Any]]
) -> None:
    versioning = client.get_bucket_versioning(Bucket=bucket)
    if versioning.get("Status") != "Enabled":
        raise StateBucketError("state bucket versioning is not enabled")
    lifecycle = client.get_bucket_lifecycle_configuration(Bucket=bucket)
    actual = normalize_rules(lifecycle.get("Rules", []))
    expected = normalize_rules(expected_rules)
    if actual != expected:
        raise StateBucketError("state bucket lifecycle does not match")


def verify_s3_semantics(client: Any, bucket: str) -> None:
    key = f"checks/state-backend-{secrets.token_hex(8)}"
    versions: list[str] = []
    try:
        first = client.put_object(Bucket=bucket, Key=key, Body=b"first")
        second = client.put_object(Bucket=bucket, Key=key, Body=b"second")
        versions.extend(str(result.get("VersionId", "")) for result in (first, second))
        if not all(versions) or len(set(versions)) != 2:
            raise StateBucketError("SeaweedFS did not retain distinct object versions")
        old = client.get_object(Bucket=bucket, Key=key, VersionId=versions[0])
        if old["Body"].read() != b"first":
            raise StateBucketError("SeaweedFS old-version retrieval failed")
        try:
            client.put_object(
                Bucket=bucket, Key=key, Body=b"unexpected", IfNoneMatch="*"
            )
        except ClientError as error:
            if error_code(error) not in {"PreconditionFailed", "412"}:
                raise
        else:
            raise StateBucketError("SeaweedFS accepted a conflicting conditional write")
    finally:
        try:
            listed = client.list_object_versions(Bucket=bucket, Prefix=key)
            for version in listed.get("Versions", []):
                client.delete_object(
                    Bucket=bucket,
                    Key=str(version["Key"]),
                    VersionId=str(version["VersionId"]),
                )
            for marker in listed.get("DeleteMarkers", []):
                client.delete_object(
                    Bucket=bucket,
                    Key=str(marker["Key"]),
                    VersionId=str(marker["VersionId"]),
                )
        except ClientError:
            pass


def ensure(args: argparse.Namespace) -> None:
    if args.state_noncurrent_days <= args.lock_noncurrent_days:
        raise StateBucketError("state history must outlive lock history")
    client = s3_client(args.endpoint, args.region)
    rules = lifecycle_rules(
        args.state_key, args.state_noncurrent_days, args.lock_noncurrent_days
    )
    ensure_bucket(client, args.bucket)
    client.put_bucket_lifecycle_configuration(
        Bucket=args.bucket,
        LifecycleConfiguration={"Rules": rules},
    )
    verify_versioning_and_lifecycle(client, args.bucket, rules)
    verify_s3_semantics(client, args.bucket)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ensure", "verify"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--state-key", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--state-noncurrent-days", type=int, required=True)
    parser.add_argument("--lock-noncurrent-days", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "ensure":
            ensure(args)
        else:
            client = s3_client(args.endpoint, args.region)
            rules = lifecycle_rules(
                args.state_key,
                args.state_noncurrent_days,
                args.lock_noncurrent_days,
            )
            verify_versioning_and_lifecycle(client, args.bucket, rules)
            verify_s3_semantics(client, args.bucket)
    except (StateBucketError, ClientError) as error:
        print(f"SeaweedFS state bucket check failed: {error}", file=sys.stderr)
        return 1
    print("SeaweedFS state bucket check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

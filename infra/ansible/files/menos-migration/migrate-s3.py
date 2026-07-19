#!/usr/bin/env python3
"""Copy and verify one S3 bucket using environment-only credentials."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def client(prefix: str) -> Any:
    from minio import Minio

    return Minio(
        required(f"{prefix}_S3_ENDPOINT"),
        access_key=required(f"{prefix}_S3_ACCESS_KEY"),
        secret_key=required(f"{prefix}_S3_SECRET_KEY"),
        secure=False,
        region=os.environ.get(f"{prefix}_S3_REGION", "us-east-1"),
    )


def wait_for_bucket(source: Any, bucket: str) -> None:
    for _attempt in range(60):
        try:
            if source.bucket_exists(bucket):
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("source S3 bucket did not become ready")


def inventory(storage: Any, bucket: str) -> list[tuple[str, int]]:
    return sorted(
        (str(item.object_name), int(item.size or 0))
        for item in storage.list_objects(bucket, recursive=True)
    )


def key_hash(items: list[tuple[str, int]]) -> str:
    keys = "".join(f"{key}\n" for key, _size in items)
    return hashlib.sha256(keys.encode()).hexdigest()


def verify_expected(items: list[tuple[str, int]]) -> None:
    expected_count = int(required("EXPECTED_S3_OBJECT_COUNT"))
    expected_bytes = int(required("EXPECTED_S3_TOTAL_BYTES"))
    expected_hash = required("EXPECTED_S3_KEY_LIST_SHA256")
    if len(items) != expected_count:
        raise RuntimeError(
            f"source object count mismatch: {len(items)} != {expected_count}"
        )
    total_bytes = sum(size for _key, size in items)
    if total_bytes != expected_bytes:
        raise RuntimeError(
            f"source byte count mismatch: {total_bytes} != {expected_bytes}"
        )
    if key_hash(items) != expected_hash:
        raise RuntimeError("source key-list checksum mismatch")


def copy_objects(
    source: Any, destination: Any, bucket: str, items: list[tuple[str, int]]
) -> None:
    from minio.error import S3Error

    if not destination.bucket_exists(bucket):
        destination.make_bucket(bucket)
    for index, (key, size) in enumerate(items, 1):
        try:
            existing = destination.stat_object(bucket, key)
            if int(existing.size or 0) == size:
                continue
        except S3Error:
            pass
        response = source.get_object(bucket, key)
        try:
            destination.put_object(bucket, key, response, size)
        finally:
            response.close()
            response.release_conn()
        if index % 250 == 0:
            print(f"copied_or_verified={index}", flush=True)


def main() -> None:
    bucket = required("S3_BUCKET")
    source = client("SOURCE")
    destination = client("DEST")
    wait_for_bucket(source, bucket)
    source_items = inventory(source, bucket)
    verify_expected(source_items)
    copy_objects(source, destination, bucket, source_items)
    destination_items = inventory(destination, bucket)
    if destination_items != source_items:
        raise RuntimeError("destination object inventory does not match source")
    verify_expected(destination_items)
    print(f"s3_objects_verified={len(destination_items)}")
    print(f"s3_bytes_verified={sum(size for _key, size in destination_items)}")


if __name__ == "__main__":
    main()

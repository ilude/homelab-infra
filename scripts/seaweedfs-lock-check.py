#!/usr/bin/env python3
"""Prove two-client OpenTofu lock contention against the SeaweedFS backend."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def s3_client(endpoint: str, region: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def wait_for_lock(
    client: Any, bucket: str, lock_key: str, process: subprocess.Popen[bytes]
) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("first OpenTofu client exited before acquiring the lock")
        try:
            client.head_object(Bucket=bucket, Key=lock_key)
            return
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        time.sleep(0.5)
    raise RuntimeError("first OpenTofu client did not create a lock in time")


def cleanup_versions(client: Any, bucket: str, prefixes: tuple[str, ...]) -> None:
    for prefix in prefixes:
        listed = client.list_object_versions(Bucket=bucket, Prefix=prefix)
        for collection in ("Versions", "DeleteMarkers"):
            for item in listed.get(collection, []):
                client.delete_object(
                    Bucket=bucket,
                    Key=str(item["Key"]),
                    VersionId=str(item["VersionId"]),
                )


def run_check(args: argparse.Namespace) -> None:
    root = Path(tempfile.mkdtemp(prefix="tofu-lock-check-"))
    client_a = root / "client-a"
    client_b = root / "client-b"
    client_a.mkdir()
    configuration = """terraform {
  backend \"s3\" {}
}

resource \"terraform_data\" \"hold_lock\" {
  provisioner \"local-exec\" {
    command = \"sleep 15\"
  }
}
"""
    (client_a / "main.tf").write_text(configuration, encoding="utf-8")
    shutil.copytree(client_a, client_b, dirs_exist_ok=True)
    backend_args = [
        f"-backend-config={args.backend_config}",
        f"-backend-config=key={args.check_key}",
    ]
    environment = dict(os.environ)
    process: subprocess.Popen[bytes] | None = None
    s3 = s3_client(args.endpoint, args.region)
    try:
        for directory in (client_a, client_b):
            initialized = subprocess.run(
                ["tofu", "init", "-input=false", *backend_args],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if initialized.returncode != 0:
                detail = (initialized.stdout + initialized.stderr)[-2000:]
                for private_value in (
                    args.endpoint,
                    environment.get("AWS_ACCESS_KEY_ID", ""),
                    environment.get("AWS_SECRET_ACCESS_KEY", ""),
                ):
                    if private_value:
                        detail = detail.replace(private_value, "<redacted>")
                raise RuntimeError(
                    "OpenTofu lock-check initialization failed: " + detail.strip()
                )
        process = subprocess.Popen(
            ["tofu", "apply", "-auto-approve", "-input=false", "-lock-timeout=0s"],
            cwd=client_a,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_lock(s3, args.bucket, f"{args.check_key}.tflock", process)
        contender = subprocess.run(
            ["tofu", "plan", "-input=false", "-lock-timeout=0s"],
            cwd=client_b,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = contender.stdout + contender.stderr
        if contender.returncode == 0 or "state lock" not in combined.lower():
            raise RuntimeError(
                "second OpenTofu client was not rejected by the state lock"
            )
        if process.wait(timeout=60) != 0:
            raise RuntimeError("first OpenTofu client failed")
        process = None
        try:
            s3.head_object(Bucket=args.bucket, Key=f"{args.check_key}.tflock")
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            raise RuntimeError("OpenTofu lock object remained after completion")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        cleanup_versions(
            s3,
            args.bucket,
            (args.check_key, f"{args.check_key}.tflock"),
        )
        shutil.rmtree(root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--check-key", default="checks/lock-contention.tfstate")
    args = parser.parse_args(argv)
    try:
        run_check(args)
    except (RuntimeError, ClientError, subprocess.TimeoutExpired) as error:
        print(f"SeaweedFS lock check failed: {error}", file=sys.stderr)
        return 1
    print("SeaweedFS two-client lock contention check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

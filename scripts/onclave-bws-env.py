#!/usr/bin/env python3
"""Render Onclave BWS secrets as Docker environment records."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import yaml

KEYS = ("RABBITMQ_DEFAULT_USER", "RABBITMQ_DEFAULT_PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.inventory.read_text(encoding="utf-8"))["all"]["vars"]
    token = os.environ.get("BITWARDEN_ACCESS_KEY", "")
    if not token:
        raise RuntimeError("BITWARDEN_ACCESS_KEY is missing")
    server = str(config["onclave_bws_api_server"]).rstrip("/")
    environment = os.environ | {
        "BWS_ACCESS_TOKEN": token,
        "BWS_SERVER_URL": server.removesuffix("/api"),
    }
    result = subprocess.run(
        [
            "bws",
            "secret",
            "list",
            str(config["onclave_bws_project_id"]),
            "--output",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("BWS could not resolve the Onclave project")
    values = {item["key"]: item["value"] for item in json.loads(result.stdout)}
    for key in KEYS:
        value = str(values.get(key, ""))
        if not value or "\n" in value or "\r" in value:
            raise RuntimeError(f"BWS secret {key} is missing or invalid")
        print(f"{key}={value.replace('$', '$$')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

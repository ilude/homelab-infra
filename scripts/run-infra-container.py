#!/usr/bin/env python3
"""Render a BWS snapshot and execute one command inside the tooling container."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_runtime_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            raise RuntimeError("BWS runtime environment is malformed")
        key, value = line.split("=", 1)
        if key in values:
            raise RuntimeError("BWS runtime environment contains duplicate keys")
        values[key] = value.replace("$$", "$")
    return values


def snapshot_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument(
        "--runtime-profile",
        choices=("config", "backend", "seaweedfs", "onclave", "all"),
        default="config",
    )
    parser.add_argument("--writeback", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    snapshot_root = Path(tempfile.mkdtemp(prefix="homelab-bws-"))
    snapshot = snapshot_root / "snapshot"
    rendered = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "bws-snapshot.py"),
            "--settings",
            str(args.settings),
            "render",
            "--output",
            str(snapshot),
            "--runtime-profile",
            args.runtime_profile,
        ],
        check=False,
    )
    if rendered.returncode != 0:
        return rendered.returncode

    parse_env = load_module("run_infra_parse_env", REPO / "scripts" / "parse-env.py")
    environment = dict(os.environ)
    environment.update(parse_env.parse_env(snapshot / "values" / ".env"))
    environment.update(load_runtime_env(snapshot / "runtime.env"))
    encryption_b64 = environment.pop("TF_ENCRYPTION_B64", "")
    if encryption_b64:
        environment["TF_ENCRYPTION"] = base64.b64decode(
            encryption_b64, validate=True
        ).decode("utf-8")
    environment["INFRA_CONFIG_SNAPSHOT_SHA256"] = snapshot_hash(
        [
            snapshot / "values" / ".env",
            snapshot / "values" / "terraform.tfvars",
            snapshot / "values" / "ansible" / "inventory" / "local.yml",
            snapshot / "values" / "dns-records.local.json",
            snapshot / "settings.local.json",
        ]
    )
    if not args.writeback:
        os.execvpe(command[0], command, environment)
        return 127

    completed = subprocess.run(command, env=environment, check=False)
    if completed.returncode != 0:
        return completed.returncode
    synced = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "bws-snapshot.py"),
            "--settings",
            str(args.settings),
            "sync",
            "--source-root",
            str(snapshot),
        ],
        env=environment,
        check=False,
    )
    return synced.returncode


if __name__ == "__main__":
    raise SystemExit(main())

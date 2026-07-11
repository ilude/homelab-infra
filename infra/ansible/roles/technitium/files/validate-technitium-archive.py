#!/usr/bin/env python3
"""Validate a Technitium portable archive before Ansible extracts it."""
from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import PurePosixPath

REQUIRED_FILES = {
    "DnsServerApp.dll",
    "DnsServerApp.runtimeconfig.json",
    "dohwww/index.html",
    "start.sh",
    "systemd.service",
    "www/index.html",
}


def validate_archive(path: str) -> None:
    members: dict[str, tarfile.TarInfo] = {}
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            member_path = PurePosixPath(member.name)
            if (
                not member.name
                or member_path.is_absolute()
                or any(part in {"", ".", ".."} for part in member_path.parts)
            ):
                raise ValueError(f"unsafe archive path: {member.name!r}")
            if member.name in members:
                raise ValueError(f"duplicate archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive member type: {member.name}")
            members[member.name] = member

        missing = sorted(
            name for name in REQUIRED_FILES if name not in members or not members[name].isfile()
        )
        if missing:
            raise ValueError(f"archive is missing required files: {', '.join(missing)}")

        runtime_member = archive.getmember("DnsServerApp.runtimeconfig.json")
        runtime_file = archive.extractfile(runtime_member)
        if runtime_file is None:
            raise ValueError("could not read DnsServerApp.runtimeconfig.json")
        runtime = json.load(runtime_file)
        frameworks = runtime.get("runtimeOptions", {}).get("frameworks", [])
        required = {"Microsoft.NETCore.App", "Microsoft.AspNetCore.App"}
        actual = {
            framework.get("name")
            for framework in frameworks
            if isinstance(framework, dict)
            and str(framework.get("version", "")).startswith("10.")
        }
        if not required.issubset(actual):
            raise ValueError("archive does not declare the required .NET 10 runtimes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()
    try:
        validate_archive(args.archive)
    except (OSError, tarfile.TarError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

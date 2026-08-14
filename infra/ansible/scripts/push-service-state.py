#!/usr/bin/env python3
"""Atomically stream a service-state archive into an approved remote staging root."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path, PurePosixPath


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--ssh-common-args", default="")
    parser.add_argument("--remote", required=True)
    parser.add_argument("--allowed-remote-root", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--become", action="store_true")
    return parser.parse_args()


def validate_remote_archive(remote: str, allowed_root: str) -> None:
    remote_path = PurePosixPath(remote)
    allowed_root_path = PurePosixPath(allowed_root)
    path_parts = (*remote.split("/"), *allowed_root.split("/"))
    if (
        not remote_path.is_absolute()
        or not allowed_root_path.is_absolute()
        or any(part in (".", "..") for part in path_parts)
        or not remote.endswith(".tar.gz")
    ):
        raise ValueError(
            "remote archive must be an absolute .tar.gz path and allowed root must be absolute"
        )
    try:
        remote_path.relative_to(allowed_root_path)
    except ValueError as error:
        raise ValueError(
            "remote archive must be contained by the allowed root"
        ) from error


def remote_upload_command(remote: str) -> list[str]:
    remote_path = PurePosixPath(remote)
    temporary_template = str(remote_path.parent / f".{remote_path.name}.XXXXXX")
    script = """set -eu
temporary=$(mktemp "$1")
cleanup() {
  rm -f "$temporary"
}
trap cleanup EXIT HUP INT TERM
cat > "$temporary"
chmod 600 "$temporary"
mv -f "$temporary" "$2"
trap - EXIT HUP INT TERM
"""
    return ["sh", "-c", script, "sh", temporary_template, remote]


def main() -> int:
    args = parse_args()
    try:
        validate_remote_archive(args.remote, args.allowed_remote_root)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not args.input.is_absolute() or args.input.suffixes[-2:] != [".tar", ".gz"]:
        raise SystemExit("input archive must be an absolute .tar.gz path")
    if not args.input.is_file():
        raise SystemExit(f"input archive does not exist: {args.input}")

    remote_command = remote_upload_command(args.remote)
    if args.become:
        remote_command = ["sudo", "-n", *remote_command]
    command = [
        "ssh",
        *shlex.split(args.ssh_common_args),
        f"{args.user}@{args.host}",
        shlex.join(remote_command),
    ]
    with args.input.open("rb") as input_archive:
        subprocess.run(command, stdin=input_archive, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

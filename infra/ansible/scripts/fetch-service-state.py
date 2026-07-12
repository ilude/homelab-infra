#!/usr/bin/env python3
"""Stream a root-owned service-state archive over the existing SSH trust path."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--ssh-common-args", default="")
    parser.add_argument("--remote", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--become", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.remote.startswith("/tmp/") or not args.remote.endswith(".tar.gz"):
        raise SystemExit("remote archive must be a /tmp/*.tar.gz path")
    if not args.output.is_absolute() or args.output.suffixes[-2:] != [".tar", ".gz"]:
        raise SystemExit("output archive must be an absolute .tar.gz path")

    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    remote_command = ["cat", args.remote]
    if args.become:
        remote_command = ["sudo", "-n", *remote_command]
    command = [
        "ssh",
        *shlex.split(args.ssh_common_args),
        f"{args.user}@{args.host}",
        *remote_command,
    ]

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{args.output.name}.", dir=args.output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            subprocess.run(command, stdout=output, check=True)
        temporary.chmod(0o600)
        temporary.replace(args.output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

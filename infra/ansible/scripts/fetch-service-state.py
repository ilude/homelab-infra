#!/usr/bin/env python3
"""Stream a service-state archive over direct SSH into an atomic private file."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import stat
import subprocess
import tempfile
from pathlib import Path


class TransferError(ValueError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-common-args", default="")
    parser.add_argument("--remote-archive", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--become", action="store_true")
    return parser.parse_args(argv)


def validate_paths(remote_archive: str, output: Path, backup_root: Path) -> tuple[Path, Path]:
    if not remote_archive.startswith("/tmp/") or not remote_archive.endswith(".tar.gz") or "/../" in remote_archive:
        raise TransferError("remote archive must be a generated /tmp/*.tar.gz path")
    root = backup_root.resolve()
    destination = output.resolve(strict=False)
    if destination.parent != root or destination.name.startswith(".") or destination.suffix != ".gz":
        raise TransferError("output must be a non-hidden .gz file directly inside the backup directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return destination, root


def ssh_command(args: argparse.Namespace) -> list[str]:
    command = ["ssh", "-p", str(args.port)]
    if args.ssh_common_args:
        command.extend(shlex.split(args.ssh_common_args))
    command.append(f"{args.user}@{args.host}")
    command.extend(["sudo", "-n", "cat", args.remote_archive] if args.become else ["cat", args.remote_archive])
    return command


def stream_archive(args: argparse.Namespace) -> dict[str, int | str]:
    output, root = validate_paths(args.remote_archive, args.output, args.backup_root)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=root)
    temp_path = Path(temp_name)
    digest = hashlib.sha256()
    size = 0
    process: subprocess.Popen[bytes] | None = None
    try:
        os.fchmod(fd, 0o600)
        process = subprocess.Popen(ssh_command(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None
        with os.fdopen(fd, "wb", closefd=True) as handle:
            fd = -1
            while chunk := process.stdout.read(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if process.stderr is not None:
            process.stderr.read()
        returncode = process.wait()
        if returncode != 0:
            raise TransferError(f"direct archive stream failed ({returncode})")
        os.replace(temp_path, output)
        os.chmod(output, stat.S_IRUSR | stat.S_IWUSR)
        return {"sha256": digest.hexdigest(), "bytes": size}
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        if process is not None and process.poll() is None:
            process.kill()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        print(json.dumps(stream_archive(args), sort_keys=True))
    except TransferError as error:
        raise SystemExit(f"service-state transfer failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compress a private device-local service-state archive into retained history."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path


class CompressionError(ValueError):
    """Raised when compression inputs are not private device backup artifacts."""


def private_backup_root(path: Path) -> Path:
    if not path.is_absolute():
        raise CompressionError("backup root must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise CompressionError("backup root must be a directory")
    resolved.chmod(0o700)
    return resolved


def direct_child(root: Path, path: Path, *, suffix: str) -> Path:
    if not path.is_absolute():
        raise CompressionError("backup artifact must be an absolute path")
    resolved = path.resolve(strict=True)
    if resolved.parent != root or not resolved.name.endswith(suffix):
        raise CompressionError("backup artifact must be a direct child of the backup root")
    if not resolved.is_file():
        raise CompressionError("backup artifact must be a regular file")
    return resolved


def history_path(root: Path, name: str) -> Path:
    path = Path(name)
    if path.name != name or not name.endswith(".tar.gz"):
        raise CompressionError("history name must be a .tar.gz basename")
    return root / name


def atomic_link(temporary: Path, destination: Path) -> None:
    try:
        os.link(temporary, destination)
    except FileExistsError as error:
        raise CompressionError(f"refusing to replace existing archive: {destination}") from error
    temporary.unlink()


def write_sidecar(path: Path, digest: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"{digest}  {path.name.removesuffix('.sha256')}\n")
            handle.flush()
            os.fsync(handle.fileno())
        atomic_link(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def retain_histories(root: Path, retention: int) -> None:
    histories = sorted(
        root.glob("*.tar.gz"), key=lambda path: (path.stat().st_mtime_ns, path.name)
    )
    for archive in histories[:-retention]:
        archive.unlink()
        archive.with_name(f"{archive.name}.sha256").unlink(missing_ok=True)


def compress_pending_archive(
    backup_root: Path,
    pending: Path,
    history_name: str,
    retention: int,
) -> Path:
    if retention < 1:
        raise CompressionError("retention must be at least one")
    root = private_backup_root(backup_root)
    pending_path = direct_child(root, pending, suffix=".tar")
    history = history_path(root, history_name)
    sidecar = history.with_name(f"{history.name}.sha256")
    if history.exists() or sidecar.exists():
        raise CompressionError(f"refusing to replace existing archive: {history}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{history.name}.", dir=root
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with pending_path.open("rb") as source, os.fdopen(descriptor, "wb") as output:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=output, compresslevel=1, mtime=0
            ) as compressed:
                shutil.copyfileobj(source, compressed, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        atomic_link(temporary, history)
        write_sidecar(sidecar, sha256(history))
        retain_histories(root, retention)
        pending_path.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return history


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", required=True, type=Path)
    parser.add_argument("--pending", required=True, type=Path)
    parser.add_argument("--history-name", required=True)
    parser.add_argument("--retention", required=True, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        compress_pending_archive(
            args.backup_root,
            args.pending,
            args.history_name,
            args.retention,
        )
    except (CompressionError, OSError) as error:
        print(f"service-state compression failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

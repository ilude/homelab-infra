#!/usr/bin/env python3
"""Compress a private device-local service-state archive into retained history."""

from __future__ import annotations

import argparse
import fcntl
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


def valid_history_pairs(root: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for sidecar in root.glob("*.tar.gz.sha256"):
        archive = root / sidecar.name.removesuffix(".sha256")
        if not archive.is_file():
            continue
        fields = sidecar.read_text(encoding="ascii").split()
        if (
            len(fields) != 2
            or fields[1] != archive.name
            or len(fields[0]) != 64
            or sha256(archive) != fields[0]
        ):
            continue
        pairs.append((archive, sidecar))
    return pairs


def retain_histories(root: Path, retention: int) -> None:
    pairs = sorted(
        valid_history_pairs(root),
        key=lambda pair: (pair[0].stat().st_mtime_ns, pair[0].name),
    )
    for archive, sidecar in pairs[:-retention]:
        archive.unlink()
        sidecar.unlink()


def compress_pending_archive(
    backup_root: Path,
    pending: Path,
    history_name: str,
    retention: int,
) -> Path:
    if retention < 1:
        raise CompressionError("retention must be at least one")
    root = private_backup_root(backup_root)
    lock_path = root / ".compression.lock"
    with lock_path.open("a+b") as lock_handle:
        os.fchmod(lock_handle.fileno(), 0o600)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        pending_path = direct_child(root, pending, suffix=".tar")
        history = history_path(root, history_name)
        sidecar = history.with_name(f"{history.name}.sha256")
        if history.exists() != sidecar.exists():
            history.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
        if history.exists():
            raise CompressionError(f"refusing to replace existing archive: {history}")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{history.name}.", dir=root
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with pending_path.open("rb") as source, os.fdopen(
                descriptor, "wb"
            ) as output:
                with gzip.GzipFile(
                    filename="", mode="wb", fileobj=output, compresslevel=1, mtime=0
                ) as compressed:
                    shutil.copyfileobj(source, compressed, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            digest = sha256(temporary)
            atomic_link(temporary, history)
            try:
                write_sidecar(sidecar, digest)
            except BaseException:
                history.unlink(missing_ok=True)
                raise
            pending_path.unlink()
            pending_path.with_name(f"{pending_path.name}.sha256").unlink(
                missing_ok=True
            )
            retain_histories(root, retention)
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

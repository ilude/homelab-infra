#!/usr/bin/env python3
"""Perform a non-mutating, mount-aware service-state restore capacity preflight."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

RESERVE_BYTES = 64 * 1024 * 1024
STATE_MULTIPLIER = 3


def existing_parent(path: Path) -> Path:
    current = path.resolve(strict=False)
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def allocated_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_blocks * 512
    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        for name in [*directories, *files]:
            entry = Path(root) / name
            try:
                total += entry.lstat().st_blocks * 512
            except FileNotFoundError:
                continue
    return total


def filesystem_key(path: Path) -> tuple[int, Path, int]:
    resolved = existing_parent(path)
    stats = os.statvfs(resolved)
    device = resolved.stat().st_dev
    return device, resolved, stats.f_bavail * stats.f_frsize


def preflight(archive_bytes: int, temporary_dir: Path, state_paths: list[Path], reserve_bytes: int = RESERVE_BYTES) -> list[dict[str, int | str | bool]]:
    if archive_bytes < 0 or reserve_bytes < 0:
        raise ValueError("archive and reserve sizes must be non-negative")
    demands: dict[int, dict[str, int | str]] = {}
    for path in [temporary_dir, *state_paths]:
        device, mount_path, available = filesystem_key(path)
        entry = demands.setdefault(device, {"filesystem": str(mount_path), "available_bytes": available, "state_bytes": 0})
        if path != temporary_dir:
            entry["state_bytes"] = int(entry["state_bytes"]) + allocated_bytes(path)
    results: list[dict[str, int | str | bool]] = []
    for entry in demands.values():
        required = archive_bytes + STATE_MULTIPLIER * int(entry["state_bytes"]) + reserve_bytes
        available = int(entry["available_bytes"])
        results.append({
            "filesystem": str(entry["filesystem"]),
            "available_bytes": available,
            "required_bytes": required,
            "deficit_bytes": max(0, required - available),
            "ok": available >= required,
        })
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-bytes", type=int, required=True)
    parser.add_argument("--temporary-dir", type=Path, default=Path("/tmp"))
    parser.add_argument("--state-path", type=Path, action="append", default=[])
    parser.add_argument("--state-paths-json", default="")
    parser.add_argument("--reserve-bytes", type=int, default=RESERVE_BYTES)
    args = parser.parse_args(argv)
    state_paths = args.state_path
    if args.state_paths_json:
        decoded = json.loads(args.state_paths_json)
        if not isinstance(decoded, list) or not all(isinstance(path, str) for path in decoded):
            raise ValueError("state paths JSON must be an array of strings")
        state_paths.extend(Path(path) for path in decoded)
    results = preflight(args.archive_bytes, args.temporary_dir, state_paths, args.reserve_bytes)
    print(json.dumps({"formula": "archive + 3*state + reserve", "filesystems": results}, sort_keys=True))
    return 0 if all(result["ok"] for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

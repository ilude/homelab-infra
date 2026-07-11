#!/usr/bin/env python3
"""Validate a managed service-state tar archive before restore."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import PurePosixPath


class ArchiveValidationError(ValueError):
    """Raised when an archive is unsafe or does not match the restore target."""


def normalized_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ArchiveValidationError(f"unsafe archive member path: {name!r}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if not parts:
        raise ArchiveValidationError(f"empty archive member path: {name!r}")
    return PurePosixPath(*parts)


def is_within(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path == root or root in path.parents


def resolve_link(member_path: PurePosixPath, linkname: str, *, hardlink: bool) -> PurePosixPath:
    link = PurePosixPath(linkname)
    if link.is_absolute():
        raise ArchiveValidationError(f"absolute link target is not allowed: {linkname!r}")
    base = PurePosixPath() if hardlink else member_path.parent
    parts: list[str] = []
    for part in (base / link).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ArchiveValidationError(f"link target escapes archive root: {linkname!r}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ArchiveValidationError(f"empty link target: {linkname!r}")
    return PurePosixPath(*parts)


def validate_archive(archive: str, target: str, managed_paths: list[str]) -> None:
    if any(not path.startswith("/") for path in managed_paths):
        raise ArchiveValidationError("managed paths must be absolute")
    roots = [normalized_member_path(path.lstrip("/")) for path in managed_paths]
    if len(roots) != len(set(roots)):
        raise ArchiveValidationError("managed paths must be unique")
    overlaps = any(
        left in right.parents or right in left.parents
        for index, left in enumerate(roots)
        for right in roots[index + 1 :]
    )
    if overlaps:
        raise ArchiveValidationError("managed paths must not overlap")
    manifest: dict[str, object] | None = None
    represented_paths: set[str] = set()

    try:
        with tarfile.open(archive, mode="r:gz") as handle:
            members = handle.getmembers()
            for member in members:
                if member.name in (".", "./"):
                    if not member.isdir():
                        raise ArchiveValidationError("archive root member must be a directory")
                    continue
                path = normalized_member_path(member.name)
                if path == PurePosixPath("MANIFEST.json"):
                    if not member.isfile() or manifest is not None:
                        raise ArchiveValidationError("MANIFEST.json must be one regular file")
                    extracted = handle.extractfile(member)
                    if extracted is None:
                        raise ArchiveValidationError("cannot read MANIFEST.json")
                    try:
                        manifest = json.loads(extracted.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ArchiveValidationError(f"invalid MANIFEST.json: {error}") from error
                    if not isinstance(manifest, dict):
                        raise ArchiveValidationError("MANIFEST.json must contain an object")
                    continue

                matching_roots = [root for root in roots if is_within(path, root)]
                if len(matching_roots) != 1:
                    raise ArchiveValidationError(f"member is outside managed paths: {member.name!r}")
                root = matching_roots[0]
                represented_paths.add("/" + str(root))

                if member.issym() or member.islnk():
                    resolved = resolve_link(path, member.linkname, hardlink=member.islnk())
                    if not is_within(resolved, root):
                        raise ArchiveValidationError(
                            f"link target escapes managed path: {member.name!r} -> {member.linkname!r}"
                        )
                elif not (member.isfile() or member.isdir()):
                    raise ArchiveValidationError(f"unsupported archive member: {member.name!r}")
    except (tarfile.TarError, OSError) as error:
        raise ArchiveValidationError(f"cannot read archive: {error}") from error

    if not represented_paths:
        raise ArchiveValidationError("archive contains no configured managed paths")

    if manifest is None:
        if target != "hermes":
            raise ArchiveValidationError("manifestless archives are supported only for legacy Hermes backups")
        return

    manifest_target = manifest.get("target", manifest.get("service"))
    if manifest_target != target:
        raise ArchiveValidationError(
            f"archive target {manifest_target!r} does not match selected target {target!r}"
        )
    manifest_paths = manifest.get("paths")
    if not isinstance(manifest_paths, list) or not all(isinstance(path, str) for path in manifest_paths):
        raise ArchiveValidationError("manifest paths must be a list of strings")
    configured = set(managed_paths)
    declared_paths = set(manifest_paths)
    if not declared_paths.issubset(configured):
        raise ArchiveValidationError("manifest contains paths outside the selected target catalog")
    if declared_paths != represented_paths:
        raise ArchiveValidationError("manifest paths do not match paths represented in the archive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--path", action="append", dest="paths")
    parser.add_argument("--paths-json")
    args = parser.parse_args()
    if args.paths_json:
        decoded = json.loads(args.paths_json)
        if not isinstance(decoded, list) or not all(isinstance(path, str) for path in decoded):
            parser.error("--paths-json must be a JSON list of strings")
        args.paths = decoded
    if not args.paths:
        parser.error("at least one managed path is required")
    return args


def main() -> int:
    args = parse_args()
    try:
        validate_archive(args.archive, args.target, args.paths)
    except ArchiveValidationError as error:
        print(f"service-state archive validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Shared dotenv-style file helpers for repo workflow scripts."""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_LINE_RE = re.compile(
    r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>=)(?P<value>.*)$"
)


class EnvFileError(ValueError):
    pass


@dataclass
class EnvEntry:
    index: int
    key: str
    value: str


def parse_scalar(raw_value: str) -> str:
    try:
        parts = shlex.split(raw_value, posix=True, comments=False)
    except ValueError as error:
        raise EnvFileError(f"invalid quoting: {error}") from error
    if len(parts) != 1:
        raise EnvFileError("expected exactly one scalar value")
    if "\x00" in parts[0]:
        raise EnvFileError("value contains a NUL byte")
    return parts[0]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_env_lines(
    lines: list[str],
    path: Path,
    *,
    allowed_keys: set[str] | None = None,
    strict_unknown: bool = False,
    skip_unknown: bool = False,
) -> dict[str, EnvEntry]:
    entries: dict[str, EnvEntry] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            if strict_unknown:
                raise EnvFileError(f"{path}:{index + 1}: expected KEY=value or export KEY=value")
            continue
        key = match.group("key")
        if allowed_keys is not None and key not in allowed_keys:
            if strict_unknown:
                raise EnvFileError(f"{path}:{index + 1}: unsupported environment key {key}")
            if skip_unknown:
                continue
        if key in entries:
            raise EnvFileError(f"{path}:{index + 1}: duplicate environment key {key}")
        try:
            value = parse_scalar(match.group("value"))
        except EnvFileError as error:
            raise EnvFileError(f"{path}:{index + 1}: invalid value for {key}: {error}") from error
        entries[key] = EnvEntry(index, key, value)
    return entries


def get_env_value(path: Path, key: str) -> str:
    for line in read_lines(path):
        match = ENV_LINE_RE.match(line)
        if not match or match.group("key") != key:
            continue
        try:
            return parse_scalar(match.group("value"))
        except EnvFileError:
            return ""
    return ""


def set_env_value(path: Path, key: str, value: str) -> bool:
    lines = read_lines(path)
    entries = parse_env_lines(lines, path)
    changed = set_env(lines, entries, key, value)
    if changed:
        write_lines(path, lines)
    return changed


def set_env(lines: list[str], entries: dict[str, EnvEntry], key: str, value: str) -> bool:
    line = f"export {key}={shell_quote(value)}"
    if key in entries:
        if entries[key].value == value:
            return False
        lines[entries[key].index] = line
        entries[key].value = value
        return True
    if lines and lines[-1].strip():
        lines.append("")
    entries[key] = EnvEntry(len(lines), key, value)
    lines.append(line)
    return True


def remove_env(lines: list[str], entries: dict[str, EnvEntry], key: str) -> bool:
    entry = entries.get(key)
    if entry is None:
        return False
    lines[entry.index] = None  # type: ignore[assignment]
    del entries[key]
    for other in entries.values():
        if other.index > entry.index:
            other.index -= 1
    lines[:] = [line for line in lines if line is not None]
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    get = subparsers.add_parser("get")
    get.add_argument("path", type=Path)
    get.add_argument("key")

    set_cmd = subparsers.add_parser("set")
    set_cmd.add_argument("path", type=Path)
    set_cmd.add_argument("key")
    set_cmd.add_argument("value")

    args = parser.parse_args(argv)
    try:
        if args.command == "get":
            print(get_env_value(args.path, args.key))
        elif args.command == "set":
            set_env_value(args.path, args.key, args.value)
    except EnvFileError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

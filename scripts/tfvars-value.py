#!/usr/bin/env python3
"""Read a simple scalar value from a terraform.tfvars-style file."""
from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*(?:#.*)?$")


class TfvarsError(ValueError):
    pass


def load_value(path: Path, key: str) -> str:
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = ASSIGN_RE.match(raw_line)
        if not match:
            continue
        found_key, raw_value = match.groups()
        if found_key != key:
            continue
        try:
            parts = shlex.split(raw_value, posix=True, comments=False)
        except ValueError as error:
            raise TfvarsError(f"{path}:{line_number}: invalid quoting for {key}: {error}") from error
        if len(parts) != 1:
            raise TfvarsError(f"{path}:{line_number}: {key} must have exactly one scalar value")
        return parts[0]
    raise TfvarsError(f"{path}: missing {key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("key")
    args = parser.parse_args(argv)

    try:
        print(load_value(args.path, args.key))
    except TfvarsError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

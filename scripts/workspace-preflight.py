#!/usr/bin/env python3
"""Check that generated workspace files are writable before plan/apply."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


class PreflightError(RuntimeError):
    pass


def check_directory_writable(path: Path) -> None:
    if not path.is_dir():
        raise PreflightError(f"missing directory: {path}")
    probe = path / ".workspace-preflight.tmp"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise PreflightError(f"directory is not writable: {path}: {error}") from error


def check_file_writable(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise PreflightError(f"path is not a regular file: {path}")
    try:
        with path.open("ab"):
            pass
    except OSError as error:
        raise PreflightError(f"file is not writable: {path}: {error}") from error


def check_glob_writable(root: Path, pattern: str) -> None:
    for path in root.glob(pattern):
        check_file_writable(path)


def check_no_state_lock(values: Path) -> None:
    lock_file = values / ".terraform.tfstate.lock.info"
    if lock_file.exists():
        raise PreflightError(
            f"OpenTofu state lock exists: {lock_file}. Another plan/apply may be running. "
            "Remove it only after confirming no OpenTofu process is active."
        )


def run(root: Path, require_values: bool) -> None:
    repo = root.resolve()
    check_directory_writable(repo)
    check_directory_writable(repo / "infra" / "opentofu")
    check_file_writable(repo / "infra" / "opentofu" / ".terraform.lock.hcl")
    check_glob_writable(repo, "tfplan*")
    check_glob_writable(repo, "*.tfplan*")

    values = repo / "values"
    if require_values or values.exists():
        check_directory_writable(values)
        check_glob_writable(values, "terraform.tfstate*")
        check_glob_writable(values, "*.tfstate*")
        check_file_writable(values / ".terraform.tfstate.lock.info")
        check_no_state_lock(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-values", action="store_true")
    args = parser.parse_args(argv)

    try:
        run(args.root, args.require_values)
    except PreflightError as error:
        print(f"workspace preflight failed: {error}", file=sys.stderr)
        print(
            "Run `just setup` to rebuild/repair the tooling container, then retry. "
            "If the problem remains, fix file ownership or permissions for the path above.",
            file=sys.stderr,
        )
        return 1

    print("workspace preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

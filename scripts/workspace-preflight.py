#!/usr/bin/env python3
"""Check that generated workspace files are writable before plan/apply."""
from __future__ import annotations

import argparse
import subprocess
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


def git_dirty_warning(values: Path) -> str | None:
    if not (values / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(values), "status", "--short"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return f"could not inspect private values git status: {result.stderr.strip()}"
    if result.stdout.strip():
        return "private values repo has uncommitted changes"
    return None


def run(root: Path, require_values: bool) -> list[str]:
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
        warning = git_dirty_warning(values)
        return [warning] if warning else []
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-values", action="store_true")
    args = parser.parse_args(argv)

    try:
        warnings = run(args.root, args.require_values)
    except PreflightError as error:
        print(f"workspace preflight failed: {error}", file=sys.stderr)
        print(
            "Run `just setup` to rebuild/repair the tooling container, then retry. "
            "If the problem remains, fix file ownership or permissions for the path above.",
            file=sys.stderr,
        )
        return 1

    for warning in warnings:
        print(f"workspace preflight warning: {warning}", file=sys.stderr)
    print("workspace preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

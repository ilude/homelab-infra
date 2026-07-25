#!/usr/bin/env python3
"""Plan or perform migration from legacy values files into a site directory."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from values_context import SITE_NAME_RE


class SiteMigrationError(ValueError):
    pass


MIGRATED_FILES = (
    Path(".env"),
    Path("terraform.tfvars"),
    Path("dns-records.local.json"),
    Path("ansible/inventory/local.yml"),
    Path("ansible/known_hosts"),
)


def site_metadata(repo: Path, site: str, site_class: str, lifecycle: str, allow_apply: bool, allow_destroy: bool) -> dict[str, Any]:
    settings_path = repo / "settings.local.json"
    services: list[str] = []
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SiteMigrationError(f"invalid operator settings: {settings_path}") from error
        candidate = raw.get("services", [])
        if isinstance(candidate, list) and all(isinstance(item, str) for item in candidate):
            services = candidate
    return {
        "name": site,
        "class": site_class,
        "lifecycle": lifecycle,
        "allow_apply": allow_apply,
        "allow_destroy": allow_destroy,
        "services": services,
    }


def migration_items(values_root: Path, target: Path) -> list[tuple[Path, Path]]:
    items: list[tuple[Path, Path]] = []
    for relative in MIGRATED_FILES:
        source = values_root / relative
        if source.is_file():
            items.append((source, target / relative))
    for source in sorted(values_root.glob("terraform.tfstate*")):
        if source.is_file():
            items.append((source, target / source.name))
    backups = values_root / "service-backups"
    if backups.is_dir():
        items.append((backups, target / "service-backups"))
    return items


def validate_request(values_root: Path, site: str, metadata: dict[str, Any]) -> tuple[Path, list[tuple[Path, Path]]]:
    if not SITE_NAME_RE.fullmatch(site) or ".." in site:
        raise SiteMigrationError("site must be a simple site identifier")
    if not values_root.is_dir():
        raise SiteMigrationError(f"values root does not exist: {values_root}")
    if (values_root / ".terraform.tfstate.lock.info").exists():
        raise SiteMigrationError("values root has an active Terraform state lock")
    target = values_root / "sites" / site
    if target.exists():
        raise SiteMigrationError(f"site target already exists: {target}")
    items = migration_items(values_root, target)
    if not items:
        raise SiteMigrationError("no legacy values files were found to migrate")
    if not isinstance(metadata.get("services"), list):
        raise SiteMigrationError("site services must be a list")
    return target, items


def remove_services_from_root_settings(repo: Path) -> None:
    path = repo / "settings.local.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("services", None)
    content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.migration-", delete=False, encoding="utf-8") as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def rollback_migration(
    target: Path,
    moved: list[tuple[Path, Path]],
    settings_path: Path,
    original_settings: bytes | None,
) -> None:
    if original_settings is None:
        settings_path.unlink(missing_ok=True)
    else:
        settings_path.write_bytes(original_settings)
    for source, destination in reversed(moved):
        if destination.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
    if target.exists():
        shutil.rmtree(target)


def migrate(
    values_root: Path,
    repo: Path,
    site: str,
    site_class: str,
    lifecycle: str,
    allow_apply: bool,
    allow_destroy: bool,
    apply: bool,
) -> list[str]:
    metadata = site_metadata(repo, site, site_class, lifecycle, allow_apply, allow_destroy)
    target, items = validate_request(values_root, site, metadata)
    settings_path = repo / "settings.local.json"
    original_settings = settings_path.read_bytes() if settings_path.is_file() else None
    actions = [f"create {target}/site.json"]
    actions.extend(f"move {source} -> {destination}" for source, destination in items)
    if (repo / "settings.local.json").is_file():
        actions.append("remove services from settings.local.json")
    if not apply:
        return actions

    target.mkdir(parents=True)
    moved: list[tuple[Path, Path]] = []
    try:
        (target / "site.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for source, destination in items:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
        remove_services_from_root_settings(repo)
    except Exception as error:
        try:
            rollback_migration(target, moved, settings_path, original_settings)
        except Exception as rollback_error:
            raise SiteMigrationError(
                "site migration and rollback both failed; restore from the private values backup before retrying"
            ) from rollback_error
        raise SiteMigrationError("site migration failed and was rolled back") from error
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    parser.add_argument("--site", required=True)
    parser.add_argument("--class", dest="site_class", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--allow-destroy", action="store_true")
    parser.add_argument("--apply", action="store_true", help="perform the migration; default is dry-run")
    args = parser.parse_args(argv)

    disposable_site = args.site == "dev" or args.site.endswith("-dev")
    site_class = args.site_class or ("development" if disposable_site else "production")
    lifecycle = args.lifecycle or ("disposable" if disposable_site else "persistent")
    # Migrating an existing production values tree must not silently disable
    # normal applies; destruction remains opt-in for persistent sites.
    allow_apply = True
    allow_destroy = args.allow_destroy or disposable_site
    try:
        actions = migrate(
            args.values_dir,
            Path.cwd(),
            args.site,
            site_class,
            lifecycle,
            allow_apply,
            allow_destroy,
            args.apply,
        )
    except (OSError, SiteMigrationError, json.JSONDecodeError) as error:
        print(f"site migration failed: {error}", file=sys.stderr)
        return 1
    print("site migration plan:" if not args.apply else "site migration applied:")
    for action in actions:
        print(f"- {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan or perform migration from legacy values files into a site directory."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
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
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    actions = [f"create {target}/site.json"]
    actions.extend(f"move {source} -> {destination}" for source, destination in items)
    if (repo / "settings.local.json").is_file():
        actions.append("remove services from settings.local.json")
    if not apply:
        return actions

    target.mkdir(parents=True)
    try:
        (target / "site.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for source, destination in items:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        remove_services_from_root_settings(repo)
    except Exception:
        raise SiteMigrationError("site migration was interrupted; restore from the private values backup before retrying")
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    parser.add_argument("--site", required=True)
    parser.add_argument("--class", dest="site_class", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--allow-apply", action="store_true")
    parser.add_argument("--allow-destroy", action="store_true")
    parser.add_argument("--apply", action="store_true", help="perform the migration; default is dry-run")
    args = parser.parse_args(argv)

    site_class = args.site_class or ("development" if args.site == "dev" else "production")
    lifecycle = args.lifecycle or ("disposable" if args.site == "dev" else "persistent")
    allow_apply = args.allow_apply or args.site == "dev"
    allow_destroy = args.allow_destroy or args.site == "dev"
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

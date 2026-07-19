#!/usr/bin/env python3
"""Import legacy Menos credentials and public authorization keys into values."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import parse_env_lines, read_lines, set_env, write_lines

ENV_MAPPING = {
    "MENOS_SURREALDB_PASSWORD": "SURREALDB_PASSWORD",
    "MENOS_S3_ACCESS_KEY": "MINIO_ACCESS_KEY",
    "MENOS_S3_SECRET_KEY": "MINIO_SECRET_KEY",
    "MENOS_SEARXNG_SECRET": "SEARXNG_SECRET",
    "MENOS_WEBSHARE_PROXY_USERNAME": "WEBSHARE_PROXY_USERNAME",
    "MENOS_WEBSHARE_PROXY_PASSWORD": "WEBSHARE_PROXY_PASSWORD",
    "MENOS_YOUTUBE_API_KEY": "YOUTUBE_API_KEY",
    "MENOS_OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
    "MENOS_ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
}
AUTHORIZED_KEY_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?$")
EMPTY_AUTHORIZED_KEYS_RE = re.compile(r"^    menos_authorized_keys: \[\]\n", re.MULTILINE)


def import_values(source_env: Path, authorized_keys: Path, values_dir: Path) -> tuple[int, int]:
    destination_env = values_dir / ".env"
    inventory = values_dir / "ansible" / "inventory" / "local.yml"
    for path in (source_env, authorized_keys, destination_env, inventory):
        if not path.exists():
            raise ValueError(f"required file does not exist: {path}")

    source_lines = read_lines(source_env)
    source_entries = parse_env_lines(source_lines, source_env)
    missing = sorted(source for source in ENV_MAPPING.values() if source not in source_entries)
    if missing:
        raise ValueError(f"legacy env is missing required keys: {', '.join(missing)}")

    destination_lines = read_lines(destination_env)
    destination_entries = parse_env_lines(destination_lines, destination_env)
    changed = 0
    for target, source in ENV_MAPPING.items():
        changed += int(
            set_env(destination_lines, destination_entries, target, source_entries[source].value)
        )
    write_lines(destination_env, destination_lines)

    public_keys = [
        line.strip()
        for line in authorized_keys.read_text(encoding="utf-8").splitlines()
        if AUTHORIZED_KEY_RE.fullmatch(line.strip())
    ]
    if not public_keys:
        raise ValueError(f"no ssh-ed25519 public authorization keys found in {authorized_keys}")

    inventory_text = inventory.read_text(encoding="utf-8")
    replacement = "    menos_authorized_keys:\n" + "".join(
        f"      - {json.dumps(key)}\n" for key in public_keys
    )
    updated, count = EMPTY_AUTHORIZED_KEYS_RE.subn(replacement, inventory_text, count=1)
    if count == 0 and "    menos_authorized_keys:\n" not in inventory_text:
        raise ValueError(f"menos_authorized_keys is missing from {inventory}")
    if count:
        inventory.write_text(updated, encoding="utf-8")

    return changed, len(public_keys)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-env", type=Path, required=True)
    parser.add_argument("--authorized-keys", type=Path, required=True)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    args = parser.parse_args(argv)
    try:
        changed, key_count = import_values(
            args.source_env, args.authorized_keys, args.values_dir
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"imported {changed} Menos credential values and {key_count} public authorization keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

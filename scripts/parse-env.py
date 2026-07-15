#!/usr/bin/env python3
"""Parse values/.env as data and emit sanitized environment records."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import EnvFileError, parse_env_lines, shell_quote

PROXMOX_KEYS = {
    "PROXMOX_VE_ENDPOINT",
    "PROXMOX_VE_API_TOKEN",
    "PROXMOX_VE_USERNAME",
    "PROXMOX_VE_PASSWORD",
    "PVE_HOST",
    "SECONDARY_PVE_HOST",
}

CADDY_KEYS = {
    "CF_API_EMAIL",
    "CF_DNS_API_TOKEN",
}

TERRAFORM_KEYS = {
    "TF_VAR_lxc_root_password",
    "TF_VAR_lxc_ssh_public_keys",
    "TF_VAR_secondary_proxmox_api_token",
    "TF_VAR_secondary_proxmox_endpoint",
}

TECHNITIUM_DNS_KEYS = {
    "TECHNITIUM_API_URL",
    "TECHNITIUM_API_TOKEN",
    "DNS_RECORDS_FILE",
}

TECHNITIUM_BOOTSTRAP_KEYS = {
    "TECHNITIUM_ADMIN_USER",
    "TECHNITIUM_ADMIN_PASSWORD",
    "TECHNITIUM_ADMIN_PASS",
}

FORGEJO_KEYS = {
    "FORGEJO_RUNNER_REGISTRATION_SECRET",
}

TAILSCALE_KEYS = {
    "TAILSCALE_AUTH_KEY",
}

INFISICAL_KEYS = {
    "INFISICAL_ENCRYPTION_KEY",
    "INFISICAL_AUTH_SECRET",
    "INFISICAL_POSTGRES_PASSWORD",
}

HERMES_KEYS = {
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
    "HERMES_WEB_SEARXNG_URL",
}

SEARXNG_KEYS = {
    "SEARXNG_SECRET_KEY",
}

EDGEROUTER_KEYS = {
    "EDGEROUTER_ADDR",
    "EDGEROUTER_USER",
}

ALLOWED_KEYS = (
    PROXMOX_KEYS
    | CADDY_KEYS
    | TERRAFORM_KEYS
    | TECHNITIUM_DNS_KEYS
    | TECHNITIUM_BOOTSTRAP_KEYS
    | FORGEJO_KEYS
    | TAILSCALE_KEYS
    | INFISICAL_KEYS
    | HERMES_KEYS
    | SEARXNG_KEYS
    | EDGEROUTER_KEYS
)


class EnvError(ValueError):
    pass


def docker_env_file_value(value: str) -> str:
    return value.replace("$", "$$")


def parse_env(path: Path) -> dict[str, str]:
    try:
        entries = parse_env_lines(
            path.read_text(encoding="utf-8").splitlines(),
            path,
            allowed_keys=set(ALLOWED_KEYS),
            strict_unknown=True,
        )
    except EnvFileError as error:
        raise EnvError(str(error)) from error
    return {key: entry.value for key, entry in entries.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keys", action="store_true", help="print parsed keys, one per line")
    parser.add_argument(
        "--env-file",
        action="store_true",
        help="print KEY=value lines for docker compose --env-from-file",
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    try:
        values = parse_env(args.path)
    except EnvError as error:
        print(error, file=sys.stderr)
        return 1

    if args.keys:
        for key in values:
            print(key)
    elif args.env_file:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                print(
                    f"{key} contains a newline and cannot be used in an env file",
                    file=sys.stderr,
                )
                return 1
            print(f"{key}={docker_env_file_value(value)}")
    else:
        for key, value in values.items():
            print(f"export {key}={shell_quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

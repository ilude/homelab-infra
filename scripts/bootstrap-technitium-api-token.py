#!/usr/bin/env python3
"""Create a Technitium DNS API token for automation when values/.env lacks one."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import EnvEntry, parse_env_lines, read_lines, set_env, write_lines
from values_context import from_environment

PLACEHOLDER_PREFIXES = ("REPLACE", "CHANGE_ME", "TODO")
DEFAULT_TOKEN_NAME = "homelab-infra"  # public-safety: allow-secret


class BootstrapError(ValueError):
    pass


class TechnitiumBootstrapClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def call(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        token: str | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        data = urllib.parse.urlencode(params or {}).encode()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{self.api_url}{path}", data=data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
        result = json.loads(body)
        if result.get("status") != "ok":
            raise BootstrapError(str(result))
        return result

    def wait_for_status(self, retries: int, delay: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(retries):
            try:
                return self.call("/status", timeout=10)
            except BootstrapError as error:
                if "invalid-token" in str(error).lower():
                    return {"status": "ok", "hasDefaultCredentials": False}
                last_error = error
                time.sleep(delay)
            except Exception as error:  # noqa: BLE001 - report the final connection/API failure.
                last_error = error
                time.sleep(delay)
        raise BootstrapError(f"Technitium API did not become ready: {last_error}")


def is_placeholder(value: str) -> bool:
    stripped = value.strip().strip('"\'')
    return not stripped or any(stripped.upper().startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def env_value(entries: Mapping[str, EnvEntry], key: str) -> str:
    entry = entries.get(key)
    return entry.value if entry else ""


def validate_existing_token(client: TechnitiumBootstrapClient, token: str) -> bool:
    if is_placeholder(token):
        return False
    try:
        client.call("/user/session/get", token=token)
    except Exception:  # noqa: BLE001 - invalid/expired token should trigger regeneration.
        return False
    return True


def login(client: TechnitiumBootstrapClient, user: str, password: str) -> str:
    result = client.call("/user/login", {"user": user, "pass": password, "includeInfo": "true"})
    token = str(result.get("token", ""))
    if not token:
        raise BootstrapError("Technitium login did not return a session token")
    return token


def create_api_token(client: TechnitiumBootstrapClient, session_token: str, token_name: str) -> str:
    result = client.call("/user/createToken", {"tokenName": token_name}, token=session_token)
    token = str(result.get("token", ""))
    if not token:
        raise BootstrapError("Technitium createToken did not return an API token")
    return token


def ensure_admin_password(
    client: TechnitiumBootstrapClient,
    status: Mapping[str, Any],
    env_file: Path,
    env_lines: list[str],
    entries: dict[str, EnvEntry],
    user: str,
) -> str:
    configured = env_value(entries, "TECHNITIUM_ADMIN_PASSWORD") or env_value(entries, "TECHNITIUM_ADMIN_PASS")
    if not is_placeholder(configured):
        return configured

    if not bool(status.get("hasDefaultCredentials")):
        raise BootstrapError(
            "TECHNITIUM_ADMIN_PASSWORD is required because Technitium default credentials are not active"
        )

    new_password = secrets.token_urlsafe(32)
    session_token = login(client, user, "admin")
    client.call("/user/changePassword", {"pass": "admin", "newPass": new_password}, token=session_token)
    set_env(env_lines, entries, "TECHNITIUM_ADMIN_PASSWORD", new_password)
    write_lines(env_file, env_lines)
    print("Generated and stored Technitium admin password.")
    return new_password


def bootstrap(env_file: Path, retries: int, delay: int, token_name: str) -> bool:
    env_lines = read_lines(env_file)
    entries = parse_env_lines(env_lines, env_file)
    api_url = env_value(entries, "TECHNITIUM_API_URL")
    if is_placeholder(api_url):
        raise BootstrapError("TECHNITIUM_API_URL must be set before bootstrapping Technitium API token")

    client = TechnitiumBootstrapClient(api_url)
    status = client.wait_for_status(retries, delay)

    existing_token = env_value(entries, "TECHNITIUM_API_TOKEN")
    if validate_existing_token(client, existing_token):
        print("Technitium API token already works.")
        return False

    user = env_value(entries, "TECHNITIUM_ADMIN_USER") or "admin"
    admin_password = ensure_admin_password(client, status, env_file, env_lines, entries, user)
    try:
        session_token = login(client, user, admin_password)
    except BootstrapError:
        if not bool(status.get("hasDefaultCredentials")):
            raise
        new_password = secrets.token_urlsafe(32)
        default_session_token = login(client, user, "admin")
        client.call("/user/changePassword", {"pass": "admin", "newPass": new_password}, token=default_session_token)
        set_env(env_lines, entries, "TECHNITIUM_ADMIN_PASSWORD", new_password)
        write_lines(env_file, env_lines)
        print("Replaced stale Technitium admin password from default credentials.")
        session_token = login(client, user, new_password)
    api_token = create_api_token(client, session_token, token_name)
    set_env(env_lines, entries, "TECHNITIUM_API_TOKEN", api_token)
    write_lines(env_file, env_lines)
    print("Generated and stored Technitium API token.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--retries", type=int, default=20)
    parser.add_argument("--delay", type=int, default=6)
    parser.add_argument("--token-name", default=DEFAULT_TOKEN_NAME)
    args = parser.parse_args(argv)

    try:
        env_file = args.env_file or from_environment().path(".env")
        bootstrap(env_file, args.retries, args.delay, args.token_name)
    except BootstrapError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

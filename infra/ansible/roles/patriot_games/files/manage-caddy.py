#!/usr/bin/env python3
"""Validate then update a managed block without replacing a file-mounted inode."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

BEGIN = "# BEGIN HOMELAB PATRIOT GAMES"
END = "# END HOMELAB PATRIOT GAMES"


def managed_config(original: str, snippet: str) -> str:
    block = f"{BEGIN}\n{snippet.rstrip()}\n{END}\n"
    if BEGIN in original or END in original:
        pattern = re.compile(rf"^{re.escape(BEGIN)}\n.*?^{re.escape(END)}\n?", re.M | re.S)
        if original.count(BEGIN) != 1 or original.count(END) != 1 or not pattern.search(original):
            raise ValueError("malformed managed Caddy block")
        return pattern.sub(lambda _: block, original)
    return original + ("" if original.endswith("\n") else "\n") + "\n" + block


def scope_legacy_dns(original: str, legacy_site: str) -> str:
    """Move the legacy global DNS provider into its existing wildcard site."""
    directive = "acme_dns cloudflare {$CF_DNS_API_TOKEN}"
    global_dns = re.compile(rf"^[ \t]*{re.escape(directive)}[ \t]*\n", re.M)
    header = re.compile(rf"^{re.escape(legacy_site)}[ \t]*\{{[ \t]*\n", re.M)
    headers = list(header.finditer(original))
    if len(headers) != 1:
        raise ValueError("expected exactly one configured legacy wildcard site")
    scoped = "    tls {\n        dns cloudflare {$CF_DNS_API_TOKEN}\n    }\n"
    globals_found = list(global_dns.finditer(original))
    if not globals_found:
        if not original[headers[0].end():].startswith(scoped):
            raise ValueError("legacy DNS provider is neither global nor scoped as expected")
        return original
    if len(globals_found) != 1:
        raise ValueError("expected exactly one legacy global DNS provider")
    legacy_body = original[headers[0].end():].split("\n}", 1)[0]
    if re.search(r"^[ \t]*tls(?:[ \t]|$)", legacy_body, re.M):
        raise ValueError("legacy site already has TLS configuration; review before migration")
    without_global = global_dns.sub("", original, count=1)
    return header.sub(lambda match: match.group() + scoped, without_global, count=1)


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("snippet", type=Path)
    parser.add_argument("container")
    parser.add_argument("--legacy-site", required=True)
    args = parser.parse_args()
    original = args.config.read_text()
    candidate = managed_config(
        scope_legacy_dns(original, args.legacy_site), args.snippet.read_text()
    )
    container_path = "/tmp/homelab-patriot.Caddyfile"
    with tempfile.TemporaryDirectory() as directory:
        staged = Path(directory) / "Caddyfile"
        staged.write_text(candidate)
        staged.chmod(0o600)
        run(["docker", "cp", str(staged), f"{args.container}:{container_path}"])
        try:
            run(["docker", "exec", args.container, "caddy", "validate", "--adapter", "caddyfile", "--config", container_path])
            if candidate != original:
                # r+ intentionally preserves the inode held by Docker's single-file bind.
                with args.config.open("r+") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(candidate)
                    stream.truncate()
                    stream.flush()
                    os.fsync(stream.fileno())
            # Also reload on an unchanged retry after an interrupted earlier deployment.
            run(["docker", "exec", args.container, "caddy", "reload", "--adapter", "caddyfile", "--config", "/etc/caddy/Caddyfile"])
        finally:
            run(["docker", "exec", args.container, "rm", "-f", container_path])
    print("changed" if candidate != original else "unchanged")


if __name__ == "__main__":
    main()

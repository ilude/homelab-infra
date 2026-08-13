#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_TIMEOUT_SECONDS = 10
_SSH_ED25519 = b"ssh-ed25519"


class ValidationError(Exception):
    pass


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise ValidationError("redirect rejected")


def _ssh_string(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def _load_signing_key(path: str) -> tuple[Ed25519PrivateKey, str]:
    expanded = Path(path).expanduser()
    try:
        private_key = serialization.load_ssh_private_key(
            expanded.read_bytes(), password=None
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValidationError("signing key unavailable") from error
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValidationError("signing key is not Ed25519")
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_blob = _ssh_string(_SSH_ED25519) + _ssh_string(public_key)
    key_id = f"SHA256:{hashlib.sha256(public_blob).hexdigest()[:16]}"
    return private_key, key_id


def _base_url(value: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValidationError("invalid HTTPS base URL")
    try:
        parsed.port
    except ValueError as error:
        raise ValidationError("invalid HTTPS base URL") from error
    return parsed


def _signed_headers(
    private_key: Ed25519PrivateKey,
    key_id: str,
    method: str,
    path: str,
    authority: str,
    body: bytes | None,
    created: int,
) -> dict[str, str]:
    components = ['"@method"', '"@path"', '"@authority"']
    lines = [
        f'"@method": {method}',
        f'"@path": {path}',
        f'"@authority": {authority}',
    ]
    headers: dict[str, str] = {}
    if body:
        digest = base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")
        headers["Content-Digest"] = f"sha-256=:{digest}:"
        components.append('"content-digest"')
        lines.append(f'"content-digest": {headers["Content-Digest"]}')
    params = (
        f'({" ".join(components)});keyid="{key_id}";alg="ed25519";created={created}'
    )
    lines.append(f'"@signature-params": {params}')
    signature = private_key.sign("\n".join(lines).encode("utf-8"))
    headers["Signature-Input"] = f"sig1={params}"
    headers["Signature"] = f"sig1=:{base64.b64encode(signature).decode('ascii')}:"
    return headers


def _json_object(value: Any, check: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{check} response contract failed")
    return value


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _request_json(
    opener: Any,
    base: urllib.parse.SplitResult,
    private_key: Ed25519PrivateKey,
    key_id: str,
    method: str,
    path: str,
    body_value: dict[str, Any] | None,
    expected_status: int,
    check: str,
) -> dict[str, Any]:
    body = None
    if body_value is not None:
        body = json.dumps(body_value, separators=(",", ":")).encode("utf-8")
    authority = base.netloc
    headers = _signed_headers(
        private_key,
        key_id,
        method,
        path,
        authority,
        body,
        int(time.time()),
    )
    headers["Accept"] = "application/json"
    if body is not None:
        headers["Content-Type"] = "application/json"
    url = urllib.parse.urlunsplit(("https", authority, path, "", ""))
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            if response.status != expected_status:
                raise ValidationError(f"{check} request failed")
            if response.geturl() != url:
                raise ValidationError("redirect rejected")
            try:
                payload = json.loads(response.read())
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValidationError(f"{check} response contract failed") from error
    except ValidationError:
        raise
    except (OSError, urllib.error.URLError) as error:
        raise ValidationError(f"{check} request failed") from error
    return _json_object(payload, check)


def validate(base_url: str, signing_key_path: str, opener: Any | None = None) -> None:
    base = _base_url(base_url)
    private_key, key_id = _load_signing_key(signing_key_path)
    client = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirects(),
        urllib.request.HTTPSHandler(),
    )

    whoami = _request_json(
        client,
        base,
        private_key,
        key_id,
        "GET",
        "/api/v1/auth/whoami",
        None,
        200,
        "whoami",
    )
    if whoami.get("key_id") != key_id:
        raise ValidationError("whoami response contract failed")

    agents = _request_json(
        client,
        base,
        private_key,
        key_id,
        "POST",
        "/api/v1/agents/rpc",
        {"op": "list_agents"},
        200,
        "agent RPC",
    )
    if agents.get("ok") is not True or not isinstance(agents.get("agents"), list):
        raise ValidationError("agent RPC response contract failed")

    content = _request_json(
        client,
        base,
        private_key,
        key_id,
        "GET",
        "/api/v1/content?limit=1",
        None,
        200,
        "content",
    )
    if not (
        _is_integer(content.get("total"))
        and isinstance(content.get("items"), list)
        and content.get("limit") == 1
        and _is_integer(content.get("offset"))
    ):
        raise ValidationError("content response contract failed")

    search = _request_json(
        client,
        base,
        private_key,
        key_id,
        "POST",
        "/api/v1/search",
        {"query": "deployment validation", "limit": 1},
        200,
        "search",
    )
    results = search.get("results")
    if not (
        search.get("query") == "deployment validation"
        and isinstance(results, list)
        and _is_integer(search.get("total"))
        and search.get("total") == len(results)
    ):
        raise ValidationError("search response contract failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("signing_key_path")
    args = parser.parse_args(argv)
    try:
        validate(args.base_url, args.signing_key_path)
    except Exception:
        print("Onclave API validation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

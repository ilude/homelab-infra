#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
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
_MAX_RESPONSE_BYTES = 1024 * 1024
_SSH_ED25519 = b"ssh-ed25519"
_READINESS_TOKENS = {
    "ok",
    "skipped",
    "error:timeout",
    "error:unavailable",
    "error:missing_credential",
    "error:unauthorized",
    "error:not_configured",
}
_REQUIRED_METRICS = {
    "onclave_transcript_attempts_total": "counter",
    "onclave_transcript_health_transitions_total": "counter",
    "onclave_vault_job_events_total": "counter",
    "onclave_vault_pipeline_stage_events_total": "counter",
    "onclave_vault_provider_requests_total": "counter",
    "onclave_vault_delivery_attempts_total": "counter",
    "onclave_transcript_attempt_duration_seconds": "summary",
    "onclave_vault_pipeline_stage_duration_seconds": "summary",
    "onclave_vault_provider_request_duration_seconds": "summary",
    "onclave_vault_delivery_attempt_duration_seconds": "summary",
}


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
        private_key = serialization.load_ssh_private_key(expanded.read_bytes(), password=None)
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
    params = f'({" ".join(components)});keyid="{key_id}";alg="ed25519";created={created}'
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


def _header(response: Any, name: str) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    value = headers.get(name)
    return value if isinstance(value, str) else ""


def _request_bytes(
    opener: Any,
    base: urllib.parse.SplitResult,
    method: str,
    path: str,
    body_value: dict[str, Any] | None,
    expected_statuses: tuple[int, ...],
    check: str,
    signing: tuple[Ed25519PrivateKey, str] | None = None,
    accept: str = "application/json",
) -> tuple[bytes, str, int]:
    body = None
    if body_value is not None:
        body = json.dumps(body_value, separators=(",", ":")).encode("utf-8")
    authority = base.netloc
    headers: dict[str, str] = {"Accept": accept}
    if signing is not None:
        private_key, key_id = signing
        headers.update(
            _signed_headers(
                private_key,
                key_id,
                method,
                path,
                authority,
                body,
                int(time.time()),
            )
        )
    if body is not None:
        headers["Content-Type"] = "application/json"
    url = urllib.parse.urlunsplit(("https", authority, path, "", ""))
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    response: Any
    try:
        try:
            response = opener.open(request, timeout=_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            if error.code not in expected_statuses:
                raise ValidationError(f"{check} request failed") from error
            response = error
        with response:
            status = response.status
            if status not in expected_statuses:
                raise ValidationError(f"{check} request failed")
            if response.geturl() != url:
                raise ValidationError("redirect rejected")
            content_length = _header(response, "Content-Length")
            if content_length.isdigit() and int(content_length) > _MAX_RESPONSE_BYTES:
                raise ValidationError(f"{check} response contract failed")
            payload = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(payload) > _MAX_RESPONSE_BYTES:
                raise ValidationError(f"{check} response contract failed")
            return payload, _header(response, "Content-Type"), status
    except ValidationError:
        raise
    except (OSError, urllib.error.URLError) as error:
        raise ValidationError(f"{check} request failed") from error


def _decode_json(payload: bytes, content_type: str, check: str) -> Any:
    if content_type.split(";", 1)[0].strip().lower() != "application/json":
        raise ValidationError(f"{check} response contract failed")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{check} response contract failed") from error


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
    payload, content_type, _ = _request_bytes(
        opener,
        base,
        method,
        path,
        body_value,
        (expected_status,),
        check,
        (private_key, key_id),
    )
    return _json_object(_decode_json(payload, content_type, check), check)


def _public_json(
    opener: Any,
    base: urllib.parse.SplitResult,
    path: str,
    expected_statuses: tuple[int, ...],
    check: str,
) -> tuple[dict[str, Any], int]:
    payload, content_type, status = _request_bytes(
        opener, base, "GET", path, None, expected_statuses, check
    )
    return _json_object(_decode_json(payload, content_type, check), check), status


def _contains_unsafe_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("_", "")
            if normalized in {"url", "username", "password", "credential", "secret"}:
                return True
            if _contains_unsafe_value(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_unsafe_value(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "://" in lowered or bool(re.search(r"[^\s/@]+:[^\s/@]+@", lowered))
    return False


def _validate_health(health: dict[str, Any], status: int) -> None:
    expected_health = "ok" if status == 200 else "degraded"
    transcript = health.get("transcript")
    broker = health.get("broker")
    if not (
        health.get("status") == expected_health
        and isinstance(health.get("git_sha"), str)
        and bool(health.get("git_sha"))
        and isinstance(health.get("build_date"), str)
        and bool(health.get("build_date"))
        and isinstance(health.get("app_version"), str)
        and bool(health.get("app_version"))
        and isinstance(broker, dict)
        and isinstance(broker.get("connected"), bool)
        and isinstance(broker.get("topologyDeclared"), bool)
        and isinstance(transcript, dict)
        and transcript.get("status") in {"ok", "degraded"}
        and isinstance(transcript.get("degraded"), bool)
        and _is_integer(transcript.get("failureCount"))
        and _is_integer(transcript.get("recoveryCount"))
    ):
        raise ValidationError("health response contract failed")
    recent = transcript.get("recentFailures")
    proxy = transcript.get("proxy")
    if not isinstance(recent, list) or len(recent) > 10:
        raise ValidationError("health response contract failed")
    if not isinstance(proxy, dict) or set(proxy) != {
        "mode",
        "configured",
        "credentialStatus",
        "dispatcherStatus",
        "connectivity",
    }:
        raise ValidationError("health response contract failed")
    if not (
        proxy.get("mode") in {"webshare", "custom", "direct"}
        and isinstance(proxy.get("configured"), bool)
        and proxy.get("credentialStatus") in {"present", "missing", "not_applicable"}
        and proxy.get("dispatcherStatus") in {"owned", "injected", "none"}
        and proxy.get("connectivity") == "not_checked"
    ):
        raise ValidationError("health response contract failed")
    allowed_failure_fields = {
        "videoId",
        "stage",
        "classification",
        "attempts",
        "httpStatus",
        "errorName",
        "errorCode",
        "occurredAt",
    }
    if any(
        not isinstance(item, dict) or not set(item) <= allowed_failure_fields for item in recent
    ):
        raise ValidationError("health response contract failed")
    if _contains_unsafe_value(health):
        raise ValidationError("health response contract failed")


def _validate_ready(ready: dict[str, Any], status: int, strict: bool = True) -> None:
    expected = "ready" if status == 200 else "degraded"
    checks = ready.get("checks")
    if not isinstance(checks, dict) or ready.get("status") != expected:
        raise ValidationError("readiness response contract failed")
    if not {"postgres", "s3", "ollama", "openrouter", "broker"} <= set(checks):
        raise ValidationError("readiness response contract failed")
    if not set(checks) <= {
        "postgres",
        "s3",
        "ollama",
        "openrouter",
        "openai",
        "anthropic",
        "broker",
    }:
        raise ValidationError("readiness response contract failed")
    if any(value not in _READINESS_TOKENS for value in checks.values()):
        raise ValidationError("readiness response contract failed")
    if strict and (
        status != 200
        or checks.get("openrouter") != "ok"
        or any(value not in {"ok", "skipped"} for value in checks.values())
    ):
        raise ValidationError("readiness response contract failed")


def _validate_metrics(content: bytes, content_type: str) -> None:
    normalized = ";".join(part.strip().lower() for part in content_type.split(";"))
    if normalized != "text/plain;version=0.0.4;charset=utf-8":
        raise ValidationError("metrics response contract failed")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError("metrics response contract failed") from error
    for name, metric_type in _REQUIRED_METRICS.items():
        if f"# HELP {name} " not in text or f"# TYPE {name} {metric_type}" not in text:
            raise ValidationError("metrics response contract failed")
    lowered = text.lower()
    if "://" in lowered or any(word in lowered for word in ("password", "credential", "secret")):
        raise ValidationError("metrics response contract failed")


def validate(base_url: str, signing_key_path: str, opener: Any | None = None) -> None:
    base = _base_url(base_url)
    private_key, key_id = _load_signing_key(signing_key_path)
    client = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirects(),
        urllib.request.HTTPSHandler(),
    )

    live, live_status = _public_json(client, base, "/live", (200,), "liveness")
    if live_status != 200 or live != {"status": "ok"}:
        raise ValidationError("liveness response contract failed")

    health, health_status = _public_json(client, base, "/health", (200, 503), "health")
    _validate_health(health, health_status)

    ready, ready_status = _public_json(client, base, "/ready", (200, 503), "readiness")
    _validate_ready(ready, ready_status)

    metrics, metrics_content_type, _ = _request_bytes(
        client,
        base,
        "GET",
        "/metrics",
        None,
        (200,),
        "metrics",
        accept="text/plain",
    )
    _validate_metrics(metrics, metrics_content_type)

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

    _request_bytes(
        client,
        base,
        "GET",
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/deliveries",
        None,
        (404,),
        "job deliveries",
        (private_key, key_id),
    )


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

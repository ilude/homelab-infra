from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check-onclave-api.py"
SPEC = importlib.util.spec_from_file_location("check_onclave_api", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("failed to load check-onclave-api.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class FakeHeaders(dict[str, str]):
    def get(self, key: str, default: str | None = None) -> str | None:
        for name, value in self.items():
            if name.lower() == key.lower():
                return value
        return default


class FakeResponse:
    def __init__(
        self,
        url: str,
        payload: object,
        status: int = 200,
        content_type: str = "application/json",
    ) -> None:
        self.status = status
        self._url = url
        self._payload = (
            payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        )
        self.headers = FakeHeaders(
            {
                "Content-Type": content_type,
                "Content-Length": str(len(self._payload)),
            }
        )

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._payload if size < 0 else self._payload[:size]


class FakeOpener:
    def __init__(
        self,
        responses: list[tuple[object, int, str]],
        redirect_to: str | None = None,
    ) -> None:
        self.responses = responses
        self.redirect_to = redirect_to
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> FakeResponse:
        self.requests.append(request)
        if timeout != 10:
            raise AssertionError("unexpected timeout")
        url = request.full_url
        if self.redirect_to is not None:
            url = self.redirect_to
        payload, status, content_type = self.responses.pop(0)
        return FakeResponse(url, payload, status, content_type)


class OnclaveApiCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.key_path = Path(self.temp_dir.name) / "id_ed25519"
        key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def metrics() -> bytes:
        types = {
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
        return "".join(
            f"# HELP {name} Safe metric.\n# TYPE {name} {metric_type}\n"
            for name, metric_type in types.items()
        ).encode("utf-8")

    @staticmethod
    def health(status: str = "ok") -> dict[str, object]:
        return {
            "status": status,
            "git_sha": "a" * 40,
            "build_date": "2026-09-24T00:00:00Z",
            "app_version": "0.1.0",
            "broker": {"connected": True, "topologyDeclared": True},
            "transcript": {
                "status": status,
                "degraded": status == "degraded",
                "failureCount": 0,
                "recoveryCount": 0,
                "firstFailureAt": None,
                "lastFailureAt": None,
                "lastRecoveryAt": None,
                "lastFailure": None,
                "recentFailures": [],
                "proxy": {
                    "mode": "webshare",
                    "configured": True,
                    "credentialStatus": "present",
                    "dispatcherStatus": "owned",
                    "connectivity": "not_checked",
                },
            },
        }

    @classmethod
    def valid_responses(cls) -> list[tuple[object, int, str]]:
        return [
            ({"status": "ok"}, 200, "application/json"),
            (cls.health(), 200, "application/json; charset=utf-8"),
            (
                {
                    "status": "ready",
                    "checks": {
                        "postgres": "ok",
                        "s3": "ok",
                        "ollama": "skipped",
                        "openrouter": "ok",
                        "broker": "ok",
                    },
                },
                200,
                "application/json",
            ),
            (
                cls.metrics(),
                200,
                "text/plain; version=0.0.4; charset=utf-8",
            ),
            ({"key_id": "SHA256:95b9aca00d322047"}, 200, "application/json"),
            ({"ok": True, "agents": []}, 200, "application/json"),
            (
                {"total": 0, "items": [], "limit": 1, "offset": 0},
                200,
                "application/json",
            ),
            (
                {"query": "deployment validation", "results": [], "total": 0},
                200,
                "application/json",
            ),
            ({"detail": "Job not found"}, 404, "application/json"),
        ]

    def test_fixed_rfc_9421_signing_vector(self) -> None:
        private_key, key_id = CHECK._load_signing_key(str(self.key_path))
        body = b'{"op":"list_agents"}'
        headers = CHECK._signed_headers(
            private_key,
            key_id,
            "POST",
            "/api/v1/agents/rpc",
            "onclave.example.internal",
            body,
            1_700_000_000,
        )
        self.assertEqual(key_id, "SHA256:95b9aca00d322047")
        self.assertEqual(
            headers,
            {
                "Content-Digest": "sha-256=:Nxcku1xn5SqH9YflFsoYJo+8gESSCYEEkPIg0ZX9tyg=:",
                "Signature-Input": (
                    'sig1=("@method" "@path" "@authority" "content-digest");'
                    'keyid="SHA256:95b9aca00d322047";alg="ed25519";'
                    "created=1700000000"
                ),
                "Signature": (
                    "sig1=:H7db4LTkb+SMuH4epfpqP6W3kYF40zW2aCuteaGaTlN52oQk"
                    "ytvZpkVK5jEQvfE9nvQoFsv2QQ/R1S0/cEEsCw==:"
                ),
            },
        )

    def test_rejects_invalid_urls_redirects_and_inherited_proxies(self) -> None:
        for value in (
            "http://onclave.example.internal",
            "https://user@onclave.example.internal",
            "https://onclave.example.internal/base",
            "https://onclave.example.internal?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(CHECK.ValidationError):
                CHECK.validate(value, str(self.key_path), FakeOpener([]))

        redirecting = FakeOpener(
            self.valid_responses(),
            redirect_to="https://redirect.example.internal/live",
        )
        with self.assertRaisesRegex(CHECK.ValidationError, "redirect rejected"):
            CHECK.validate("https://onclave.example.internal", str(self.key_path), redirecting)

        opener = FakeOpener(self.valid_responses())
        with mock.patch.object(CHECK.urllib.request, "build_opener", return_value=opener) as build:
            CHECK.validate("https://onclave.example.internal", str(self.key_path))
        proxy_handlers = [
            handler
            for handler in build.call_args.args
            if isinstance(handler, CHECK.urllib.request.ProxyHandler)
        ]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(proxy_handlers[0].proxies, {})

    def test_validates_public_operational_contracts(self) -> None:
        degraded = self.valid_responses()
        degraded[1] = (self.health("degraded"), 503, "application/json")
        CHECK.validate(
            "https://onclave.example.internal",
            str(self.key_path),
            FakeOpener(degraded),
        )

        cases = (
            (0, ({"status": "degraded"}, 200, "application/json"), "liveness"),
            (
                1,
                (
                    {
                        **self.health(),
                        "transcript": {
                            **self.health()["transcript"],
                            "proxy": {
                                "mode": "webshare",
                                "configured": True,
                                "credentialStatus": "present",
                                "dispatcherStatus": "owned",
                                "connectivity": "not_checked",
                                "url": "https://private.example.invalid",
                            },
                        },
                    },
                    200,
                    "application/json",
                ),
                "health",
            ),
            (
                2,
                (
                    {
                        "status": "ready",
                        "checks": {
                            "postgres": "ok",
                            "s3": "ok",
                            "ollama": "skipped",
                            "broker": "error:unavailable",
                        },
                    },
                    200,
                    "application/json",
                ),
                "readiness",
            ),
            (3, (b"# HELP missing Missing.\n", 200, "text/plain"), "metrics"),
        )
        for index, invalid, check_name in cases:
            with self.subTest(check=check_name):
                responses = self.valid_responses()
                responses[index] = invalid
                with self.assertRaisesRegex(CHECK.ValidationError, check_name):
                    CHECK.validate(
                        "https://onclave.example.internal",
                        str(self.key_path),
                        FakeOpener(responses),
                    )

    def test_requires_configured_openrouter_readiness(self) -> None:
        ready = {
            "status": "ready",
            "checks": {
                "postgres": "ok",
                "s3": "ok",
                "ollama": "skipped",
                "broker": "ok",
            },
        }
        with self.assertRaisesRegex(CHECK.ValidationError, "readiness"):
            CHECK._validate_ready(ready, 200)

        ready["checks"]["openrouter"] = "ok"
        CHECK._validate_ready(ready, 200)

        ready["checks"]["openrouter"] = "skipped"
        with self.assertRaisesRegex(CHECK.ValidationError, "readiness"):
            CHECK._validate_ready(ready, 200)

    def test_rejects_unknown_proxy_enums_without_exposing_canaries(self) -> None:
        cases = {
            "mode": "credential-canary-mode",
            "configured": "credential-canary-configured",
            "credentialStatus": "credential-canary-status",
            "dispatcherStatus": "credential-canary-dispatcher",
            "connectivity": "credential-canary-connectivity",
        }
        for field, canary in cases.items():
            with self.subTest(field=field):
                health = self.health()
                health["transcript"]["proxy"][field] = canary
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                    self.assertRaisesRegex(CHECK.ValidationError, "health") as raised,
                ):
                    CHECK._validate_health(health, 200)
                self.assertNotIn(canary, str(raised.exception))
                self.assertNotIn(canary, stdout.getvalue())
                self.assertNotIn(canary, stderr.getvalue())

        for mode, credential, dispatcher in (
            ("webshare", "present", "owned"),
            ("custom", "missing", "injected"),
            ("direct", "not_applicable", "none"),
        ):
            with self.subTest(mode=mode):
                health = self.health()
                proxy = health["transcript"]["proxy"]
                proxy["mode"] = mode
                proxy["credentialStatus"] = credential
                proxy["dispatcherStatus"] = dispatcher
                CHECK._validate_health(health, 200)

    def test_validates_all_signed_response_contracts(self) -> None:
        cases = (
            (4, {"key_id": "wrong"}, "whoami"),
            (5, {"ok": True, "agents": {}}, "agent RPC"),
            (6, {"total": True, "items": [], "limit": 1, "offset": 0}, "content"),
            (
                7,
                {"query": "deployment validation", "results": [], "total": 1},
                "search",
            ),
        )
        for index, invalid, check_name in cases:
            with self.subTest(check=check_name):
                responses = self.valid_responses()
                _, status, content_type = responses[index]
                responses[index] = (invalid, status, content_type)
                with self.assertRaisesRegex(CHECK.ValidationError, check_name):
                    CHECK.validate(
                        "https://onclave.example.internal",
                        str(self.key_path),
                        FakeOpener(responses),
                    )

        opener = FakeOpener(self.valid_responses())
        CHECK.validate("https://onclave.example.internal", str(self.key_path), opener)
        self.assertEqual(len(opener.requests), 9)
        self.assertEqual(
            [(request.get_method(), request.full_url) for request in opener.requests],
            [
                ("GET", "https://onclave.example.internal/live"),
                ("GET", "https://onclave.example.internal/health"),
                ("GET", "https://onclave.example.internal/ready"),
                ("GET", "https://onclave.example.internal/metrics"),
                ("GET", "https://onclave.example.internal/api/v1/auth/whoami"),
                ("POST", "https://onclave.example.internal/api/v1/agents/rpc"),
                ("GET", "https://onclave.example.internal/api/v1/content?limit=1"),
                ("POST", "https://onclave.example.internal/api/v1/search"),
                (
                    "GET",
                    "https://onclave.example.internal/api/v1/jobs/00000000-0000-0000-0000-000000000000/deliveries",
                ),
            ],
        )
        for request in opener.requests[:4]:
            self.assertIsNone(request.get_header("Signature"))
        for request in opener.requests[4:]:
            self.assertIsNotNone(request.get_header("Signature"))

    def test_rejects_oversized_or_wrong_content_type_responses(self) -> None:
        oversized = self.valid_responses()
        oversized[0] = (b"x" * (CHECK._MAX_RESPONSE_BYTES + 1), 200, "application/json")
        with self.assertRaisesRegex(CHECK.ValidationError, "liveness"):
            CHECK.validate(
                "https://onclave.example.internal",
                str(self.key_path),
                FakeOpener(oversized),
            )

        wrong_type = self.valid_responses()
        wrong_type[0] = ({"status": "ok"}, 200, "text/plain")
        with self.assertRaisesRegex(CHECK.ValidationError, "liveness"):
            CHECK.validate(
                "https://onclave.example.internal",
                str(self.key_path),
                FakeOpener(wrong_type),
            )

    def test_failure_output_is_redacted(self) -> None:
        sensitive_url = "https://private-host.example.internal"
        sensitive_path = "/example/signing-key"
        stderr = io.StringIO()
        with (
            mock.patch.object(
                CHECK, "validate", side_effect=RuntimeError("secret signature response")
            ),
            contextlib.redirect_stderr(stderr),
        ):
            result = CHECK.main([sensitive_url, sensitive_path])
        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "Onclave API validation failed\n")
        self.assertNotIn("private-host", stderr.getvalue())
        self.assertNotIn("signing-key", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

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


class FakeResponse:
    def __init__(self, url: str, payload: object, status: int = 200) -> None:
        self.status = status
        self._url = url
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self) -> bytes:
        return self._payload


class FakeOpener:
    def __init__(self, payloads: list[object], redirect_to: str | None = None) -> None:
        self.payloads = payloads
        self.redirect_to = redirect_to
        self.requests: list[object] = []

    def open(self, request: object, timeout: int) -> FakeResponse:
        self.requests.append(request)
        if timeout != 10:
            raise AssertionError("unexpected timeout")
        url = request.full_url
        if self.redirect_to is not None:
            url = self.redirect_to
        return FakeResponse(url, self.payloads.pop(0))


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
    def valid_payloads() -> list[object]:
        return [
            {"key_id": "SHA256:95b9aca00d322047"},
            {"ok": True, "agents": []},
            {"total": 0, "items": [], "limit": 1, "offset": 0},
            {"query": "deployment validation", "results": [], "total": 0},
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
                "Signature-Input": 'sig1=("@method" "@path" "@authority" "content-digest");keyid="SHA256:95b9aca00d322047";alg="ed25519";created=1700000000',
                "Signature": "sig1=:H7db4LTkb+SMuH4epfpqP6W3kYF40zW2aCuteaGaTlN52oQkytvZpkVK5jEQvfE9nvQoFsv2QQ/R1S0/cEEsCw==:",
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
            self.valid_payloads(),
            redirect_to="https://redirect.example.internal/api/v1/auth/whoami",
        )
        with self.assertRaisesRegex(CHECK.ValidationError, "redirect rejected"):
            CHECK.validate(
                "https://onclave.example.internal", str(self.key_path), redirecting
            )

        opener = FakeOpener(self.valid_payloads())
        with mock.patch.object(
            CHECK.urllib.request, "build_opener", return_value=opener
        ) as build:
            CHECK.validate("https://onclave.example.internal", str(self.key_path))
        proxy_handlers = [
            handler
            for handler in build.call_args.args
            if isinstance(handler, CHECK.urllib.request.ProxyHandler)
        ]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(proxy_handlers[0].proxies, {})

    def test_validates_all_four_response_contracts(self) -> None:
        cases = (
            (0, {"key_id": "wrong"}, "whoami"),
            (1, {"ok": True, "agents": {}}, "agent RPC"),
            (2, {"total": True, "items": [], "limit": 1, "offset": 0}, "content"),
            (
                3,
                {"query": "deployment validation", "results": [], "total": 1},
                "search",
            ),
        )
        for index, invalid, check_name in cases:
            with self.subTest(check=check_name):
                payloads = self.valid_payloads()
                payloads[index] = invalid
                with self.assertRaisesRegex(CHECK.ValidationError, check_name):
                    CHECK.validate(
                        "https://onclave.example.internal",
                        str(self.key_path),
                        FakeOpener(payloads),
                    )

        opener = FakeOpener(self.valid_payloads())
        CHECK.validate("https://onclave.example.internal", str(self.key_path), opener)
        self.assertEqual(len(opener.requests), 4)
        self.assertEqual(
            [(request.get_method(), request.full_url) for request in opener.requests],
            [
                ("GET", "https://onclave.example.internal/api/v1/auth/whoami"),
                ("POST", "https://onclave.example.internal/api/v1/agents/rpc"),
                ("GET", "https://onclave.example.internal/api/v1/content?limit=1"),
                ("POST", "https://onclave.example.internal/api/v1/search"),
            ],
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

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse-env.py"
spec = importlib.util.spec_from_file_location("parse_env_script", SCRIPT)
assert spec and spec.loader
parse_env_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parse_env_script)


class ParseEnvTests(unittest.TestCase):
    def write_env(self, content: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with handle:
            handle.write(content)
        return Path(handle.name)

    def test_accepts_export_and_quotes(self) -> None:
        path = self.write_env('export CF_API_EMAIL="admin@example.internal"\n')
        try:
            values = parse_env_script.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(values["CF_API_EMAIL"], "admin@example.internal")

    def test_duplicate_key_fails(self) -> None:
        path = self.write_env("PVE_HOST=one\nPVE_HOST=two\n")
        try:
            with self.assertRaises(parse_env_script.EnvError):
                parse_env_script.parse_env(path)
        finally:
            path.unlink()

    def test_unknown_key_fails(self) -> None:
        path = self.write_env("PVE_HOST=proxmox.example.internal\nBAD_KEY=value\n")
        try:
            with self.assertRaises(parse_env_script.EnvError):
                parse_env_script.parse_env(path)
        finally:
            path.unlink()

    def test_invalid_quoting_fails(self) -> None:
        path = self.write_env('PVE_HOST="unterminated\n')
        try:
            with self.assertRaises(parse_env_script.EnvError):
                parse_env_script.parse_env(path)
        finally:
            path.unlink()

    def test_unquoted_multi_token_value_fails(self) -> None:
        path = self.write_env("PVE_HOST=one two\n")
        try:
            with self.assertRaises(parse_env_script.EnvError):
                parse_env_script.parse_env(path)
        finally:
            path.unlink()

    def test_tailscale_auth_key_is_allowed(self) -> None:
        path = self.write_env("TAILSCALE_AUTH_KEY=tskey-example-placeholder\n")
        try:
            values = parse_env_script.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(values["TAILSCALE_AUTH_KEY"], "tskey-example-placeholder")

    def test_onclave_rabbitmq_keys_are_allowed(self) -> None:
        path = self.write_env(
            "RABBITMQ_DEFAULT_USER=onclave\nRABBITMQ_DEFAULT_PASS=placeholder-secret\n"
        )
        try:
            values = parse_env_script.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(values["RABBITMQ_DEFAULT_USER"], "onclave")
        self.assertEqual(values["RABBITMQ_DEFAULT_PASS"], "placeholder-secret")

    def test_menos_keys_are_allowed(self) -> None:
        path = self.write_env(
            "MENOS_POSTGRES_PASSWORD=db-secret\n"  # public-safety: allow-secret
            "MENOS_S3_ACCESS_KEY=access-key\n"
            "MENOS_S3_SECRET_KEY=storage-secret\n"  # public-safety: allow-secret
            "MENOS_YOUTUBE_API_KEY=youtube-key\n"  # public-safety: allow-secret
        )
        try:
            values = parse_env_script.parse_env(path)
        finally:
            path.unlink()
        self.assertEqual(values["MENOS_POSTGRES_PASSWORD"], "db-secret")
        self.assertEqual(values["MENOS_S3_ACCESS_KEY"], "access-key")

    def test_keys_mode_prints_only_keys(self) -> None:
        path = self.write_env("PVE_HOST=proxmox.example.internal\n")
        try:
            self.assertEqual(parse_env_script.main(["--keys", str(path)]), 0)
        finally:
            path.unlink()

    def test_env_file_mode_succeeds(self) -> None:
        path = self.write_env("PVE_HOST=proxmox.example.internal\n")
        try:
            self.assertEqual(parse_env_script.main(["--env-file", str(path)]), 0)
        finally:
            path.unlink()

    def test_env_file_mode_escapes_dollar_for_docker_compose(self) -> None:
        path = self.write_env(
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH='scrypt$1$2$3$salt$hash'\n"
        )
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                self.assertEqual(parse_env_script.main(["--env-file", str(path)]), 0)
        finally:
            path.unlink()
        self.assertIn(
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH=scrypt$$1$$2$$3$$salt$$hash",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()

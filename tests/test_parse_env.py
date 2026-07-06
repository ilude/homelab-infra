from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()

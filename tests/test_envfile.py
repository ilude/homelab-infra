from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "envfile.py"
spec = importlib.util.spec_from_file_location("envfile", SCRIPT)
assert spec and spec.loader
envfile = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = envfile
spec.loader.exec_module(envfile)


class EnvfileTests(unittest.TestCase):
    def write_env(self, content: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with handle:
            handle.write(content)
        return Path(handle.name)

    def test_get_env_value_parses_export_and_quotes(self) -> None:
        path = self.write_env("export API_TOKEN='abc # not comment'\n")
        try:
            self.assertEqual(envfile.get_env_value(path, "API_TOKEN"), "abc # not comment")
        finally:
            path.unlink()

    def test_get_env_value_returns_empty_on_invalid_quoting(self) -> None:
        path = self.write_env("export API_TOKEN='unterminated\n")
        try:
            self.assertEqual(envfile.get_env_value(path, "API_TOKEN"), "")
        finally:
            path.unlink()

    def test_set_env_value_preserves_unrelated_lines_and_quotes(self) -> None:
        path = self.write_env("# comment\nexport OLD=value\n")
        try:
            envfile.set_env_value(path, "API_TOKEN", "value with ' quote")
            self.assertEqual(envfile.get_env_value(path, "API_TOKEN"), "value with ' quote")
            text = path.read_text(encoding="utf-8")
            self.assertIn("# comment", text)
            self.assertIn("export OLD=value", text)
        finally:
            path.unlink()

    def test_parse_env_lines_strict_unknown_rejects_bad_line(self) -> None:
        with self.assertRaises(envfile.EnvFileError):
            envfile.parse_env_lines(["not an env line"], Path(".env"), strict_unknown=True)

    def test_parse_env_lines_skip_unknown_ignores_disallowed_keys(self) -> None:
        entries = envfile.parse_env_lines(
            ["KNOWN=value", "UNKNOWN=value"],
            Path(".env"),
            allowed_keys={"KNOWN"},
            skip_unknown=True,
        )
        self.assertEqual(list(entries), ["KNOWN"])


if __name__ == "__main__":
    unittest.main()

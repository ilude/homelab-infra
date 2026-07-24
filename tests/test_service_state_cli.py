from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = ROOT / "scripts" / "service-state.sh"
SITE_CONTEXT_SCRIPT = ROOT / "scripts" / "site-context.sh"


class ServiceStateCliTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> Path:
        scripts = root / "scripts"
        scripts.mkdir()
        script = scripts / "service-state.sh"
        shutil.copy2(SOURCE_SCRIPT, script)
        shutil.copy2(SITE_CONTEXT_SCRIPT, scripts / "site-context.sh")
        (scripts / "python.sh").write_text("#!/usr/bin/env bash\nif [[ \"$1\" == \"-\" ]]; then echo hermes; else echo hermes; fi\n", encoding="utf-8")
        (scripts / "settings.py").write_text("#!/usr/bin/env bash\necho hermes\n", encoding="utf-8")
        (scripts / "run-infra.sh").write_text(
            "#!/usr/bin/env bash\n"
            "printf 'MSYS2_ENV_CONV_EXCL=%s\\n' \"${MSYS2_ENV_CONV_EXCL:-}\" >> \"${CAPTURE_FILE}\"\n"
            "printf '%s\\n' \"$*\" >> \"${CAPTURE_FILE}\"\n",
            encoding="utf-8",
        )
        for path in scripts.iterdir():
            path.chmod(0o755)
        return script

    def test_restore_excludes_container_paths_from_msys_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self.make_fixture(root)
            archive = root / "values" / "service-backups" / "hermes" / "state.tar.gz"
            archive.parent.mkdir(parents=True)
            archive.touch()
            capture = root / "run-infra.txt"
            environment = os.environ | {
                "CAPTURE_FILE": str(capture),
                "MSYS2_ENV_CONV_EXCL": "KEEP",
            }

            result = subprocess.run(
                [str(script), "restore", "hermes", str(archive)],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "MSYS2_ENV_CONV_EXCL=KEEP;SERVICE_STATE_BACKUP_ROOT;SERVICE_STATE_RESTORE_FILE",
                capture.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()

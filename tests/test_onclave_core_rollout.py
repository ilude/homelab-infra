from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[1]
ROLLOUT_PATH = REPO / "scripts" / "onclave-core-rollout.py"
REDACTOR_PATH = REPO / "scripts" / "redact-core-logs.py"
PLAYBOOK_PATH = REPO / "infra" / "ansible" / "playbooks" / "onclave-core-rollout.yml"
FIXTURE = REPO / "tests" / "fixtures" / "site-config" / "ansible" / "inventory" / "local.yml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rollout = load_module("onclave_core_rollout_test_subject", ROLLOUT_PATH)
redactor = load_module("onclave_core_log_redactor_test_subject", REDACTOR_PATH)


class OnclaveCoreRolloutTests(unittest.TestCase):
    def test_pin_update_changes_only_approved_inventory_keys(self) -> None:
        before = FIXTURE.read_text(encoding="utf-8")

        def parsed(text: str, _key: str):
            return yaml.safe_load(text)

        old = rollout.pin_values(before, parsed)
        desired = dict(old)
        desired.update(
            {
                "onclave_source_git_sha": "a" * 40,
                "onclave_app_definition_url": (
                    "https://raw.githubusercontent.com/example/onclave/"
                    + "a" * 40
                    + "/deploy/app/onclave/compose.yaml"
                ),
                "onclave_app_definition_sha256": "b" * 64,
                "onclave_backup_script_sha256": "c" * 64,
                "onclave_restore_script_sha256": "d" * 64,
                "onclave_core_image_tag": "a" * 40,
                "onclave_core_image_digest": "sha256:" + "e" * 64,
            }
        )
        after = rollout.update_inventory_pins(before, desired)
        rollout.assert_only_pins_changed(before, after, parsed)
        self.assertEqual(rollout.pin_values(after, parsed), desired)

    def test_source_urls_replace_only_the_commit_component(self) -> None:
        before = FIXTURE.read_text(encoding="utf-8")
        inventory = yaml.safe_load(before)["all"]["vars"]
        urls = rollout.source_urls(inventory["onclave_app_definition_url"], "a" * 40)
        expected_path = "/" + "a" * 40 + "/deploy/app/onclave/compose.yaml"
        self.assertIn(expected_path, urls["onclave_app_definition_url"])
        self.assertTrue(urls["backup-postgres.sh"].endswith("/backup-postgres.sh"))
        self.assertTrue(urls["restore-postgres.sh"].endswith("/restore-postgres.sh"))

    def test_supplied_digest_must_match_resolved_tag(self) -> None:
        self.assertRegex("sha256:" + "a" * 64, rollout.DIGEST_RE)
        self.assertNotRegex("sha256:" + "A" * 64, rollout.DIGEST_RE)

    @staticmethod
    def parse_yaml(text: str, _key: str):
        return yaml.safe_load(text)

    @staticmethod
    def compose(health_path: str, environment: dict[str, object] | None = None) -> bytes:
        return yaml.safe_dump(
            {
                "name": "onclave",
                "services": {
                    "onclave-core": {
                        "image": "example/core",
                        "environment": environment or {"UNCHANGED": "value"},
                        "depends_on": {"postgres": {"condition": "service_healthy"}},
                        "healthcheck": {
                            "test": [
                                "CMD",
                                "wget",
                                "-qO-",
                                f"http://127.0.0.1:8000{health_path}",
                            ],
                            "interval": "10s",
                        },
                    },
                    "postgres": {"image": "example/postgres"},
                },
            },
            sort_keys=True,
        ).encode()

    @classmethod
    def artifacts(
        cls,
        health_path: str,
        environment: dict[str, object] | None = None,
    ) -> dict[str, bytes]:
        return {
            "compose.yaml": cls.compose(health_path, environment),
            "backup-postgres.sh": b"backup\n",
            "restore-postgres.sh": b"restore\n",
        }

    def test_compose_contract_allows_only_exact_one_way_health_probe_change(self) -> None:
        previous = self.artifacts("/health")
        desired = self.artifacts("/live")
        self.assertEqual(
            rollout.compatible_artifact_transition(previous, desired, self.parse_yaml),
            ("/health", "/live"),
        )
        self.assertEqual(
            rollout.compatible_artifact_transition(desired, desired, self.parse_yaml),
            ("/live", "/live"),
        )

    def test_compose_contract_rejects_rc_environment_change_despite_probe_change(self) -> None:
        previous = self.artifacts("/health")
        desired = self.artifacts(
            "/live",
            {
                "UNCHANGED": "value",
                "ONCLAVE_VAULT_JOB_LEASE_MS": "${ONCLAVE_VAULT_JOB_LEASE_MS:-300000}",
            },
        )
        with self.assertRaisesRegex(rollout.RolloutError, "reviewed Onclave role"):
            rollout.compatible_artifact_transition(previous, desired, self.parse_yaml)

    def test_compose_contract_rejects_type_coercing_nonprobe_leaf_changes(self) -> None:
        for previous_value, desired_value in ((5, 5.0), (True, 1)):
            previous = self.artifacts("/health", {"TYPED_VALUE": previous_value})
            desired = self.artifacts("/live", {"TYPED_VALUE": desired_value})
            with self.subTest(previous=previous_value, desired=desired_value):
                with self.assertRaisesRegex(rollout.RolloutError, "reviewed Onclave role"):
                    rollout.compatible_artifact_transition(
                        previous,
                        desired,
                        self.parse_yaml,
                    )

    def test_compose_contract_rejects_reverse_probe_and_helper_changes(self) -> None:
        with self.assertRaisesRegex(rollout.RolloutError, "one-way"):
            rollout.compatible_artifact_transition(
                self.artifacts("/live"),
                self.artifacts("/health"),
                self.parse_yaml,
            )
        changed_helper = self.artifacts("/live")
        changed_helper["backup-postgres.sh"] = b"changed\n"
        with self.assertRaisesRegex(rollout.RolloutError, "backup-postgres.sh"):
            rollout.compatible_artifact_transition(
                self.artifacts("/live"),
                changed_helper,
                self.parse_yaml,
            )

    def test_rollback_passes_the_recorded_prior_image_health_contract(self) -> None:
        pins = {
            "onclave_source_git_sha": "a" * 40,
            "onclave_core_image_repository": "ghcr.io/example/onclave",
            "onclave_core_image_tag": "a" * 40,
            "onclave_core_image_digest": "sha256:" + "b" * 64,
        }
        observed: dict[str, object] = {}

        def completed(command: list[str], check: bool):
            self.assertFalse(check)
            extra = json.loads(command[-1])
            observed.update(extra)
            Path(str(extra["onclave_core_rollout_result_path"])).write_text(
                json.dumps({"affected_units": ["onclave-core.service"]}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0)

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(rollout.subprocess, "run", side_effect=completed),
        ):
            evidence = rollout.run_playbook(
                "rollback",
                Path(temporary),
                pins,
                "/health",
                ["/health", "/live"],
                ["a" * 40, "c" * 40],
            )
        self.assertEqual(observed["onclave_core_rollout_health_path"], "/health")
        self.assertEqual(
            observed["onclave_core_rollout_compatible_installed_health_paths"],
            ["/health", "/live"],
        )
        self.assertEqual(
            observed["onclave_core_rollout_compatible_installed_revisions"],
            ["a" * 40, "c" * 40],
        )
        self.assertEqual(evidence["affected_units"], ["onclave-core.service"])

    def test_rollback_preflight_tolerates_missing_core_and_refused_http_before_restore(
        self,
    ) -> None:
        source = PLAYBOOK_PATH.read_text(encoding="utf-8")
        marker = "              \"{{ onclave_core_rollout_mode }}\" <<'PY'\n"
        start = source.index(marker) + len(marker)
        end = source.index("\n            PY", start)
        preflight = textwrap.dedent(source[start:end])
        previous_sha = "a" * 40
        failed_sha = "c" * 40

        def command(argv: list[str], **_kwargs):
            if argv[0] == "systemctl":
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="ActiveState=active\nSubState=running\nMainPID=123\nNRestarts=0\n",
                    stderr="",
                )
            if argv[0] == "podman" and argv[-1] == "onclave-core":
                raise subprocess.CalledProcessError(1, argv)
            container = argv[-1]
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": f"id-{container}",
                            "State": {"Status": "running", "ExitCode": 0},
                            "RestartCount": 0,
                        }
                    ]
                ),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            quadlet = root / "onclave-core.container"
            environment = root / "core.env"
            quadlet.write_text(
                'HealthCmd=node -e \'fetch("http://127.0.0.1:8000/live").then(response => '
                "{ if (!response.ok) process.exit(1); }).catch(() => process.exit(1))'\n",
                encoding="utf-8",
            )
            environment.write_text(f"GIT_SHA={failed_sha}\n", encoding="utf-8")
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    ["preflight", str(quadlet), str(environment), "9", "desired"],
                ),
                mock.patch("subprocess.run", side_effect=command),
                mock.patch(
                    "urllib.request.urlopen",
                    side_effect=urllib.error.URLError("connection refused"),
                ),
                self.assertRaises(urllib.error.URLError),
            ):
                exec(compile(preflight, "forward-preflight", "exec"), {})

            output = io.StringIO()
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    ["preflight", str(quadlet), str(environment), "9", "rollback"],
                ),
                mock.patch("subprocess.run", side_effect=command),
                mock.patch(
                    "urllib.request.urlopen",
                    side_effect=urllib.error.URLError("connection refused"),
                ),
                redirect_stdout(output),
            ):
                exec(compile(preflight, "rollback-preflight", "exec"), {})

        evidence = json.loads(output.getvalue())
        self.assertIsNone(evidence["revision"])
        self.assertEqual(evidence["configured_revision"], failed_sha)
        self.assertFalse(evidence["units"]["onclave-core.service"]["runtime_available"])
        self.assertIsNone(evidence["endpoints"]["health"]["http_status"])
        for unit, snapshot in evidence["units"].items():
            if unit != "onclave-core.service":
                self.assertTrue(snapshot["runtime_available"])
        self.assertIn(evidence["health_path"], ["/health", "/live"])
        self.assertIn(evidence["configured_revision"], [previous_sha, failed_sha])

        tasks = yaml.safe_load(source)[-1]["tasks"][0]["block"]
        task_names = [task["name"] for task in tasks]
        self.assertLess(
            task_names.index(
                "Capture pre-rollout revision, endpoint support, units, and restart observations"
            ),
            task_names.index("Persist the selected core image pin"),
        )
        self.assertLess(
            task_names.index("Persist the selected core image pin"),
            task_names.index("Recreate only the native onclave-core service"),
        )

    def test_strict_rc_readiness_requires_configured_openrouter_key(self) -> None:
        source = PLAYBOOK_PATH.read_text(encoding="utf-8")
        marker = "                  \"{{ onclave_core_rollout_quadlet }}\" <<'PY'\n"
        start = source.index(marker) + len(marker)
        end = source.index("\n            PY", start)
        validator = textwrap.dedent(source[start:end])
        expected_sha = "d" * 40
        counters = [
            "onclave_transcript_attempts_total",
            "onclave_transcript_health_transitions_total",
            "onclave_vault_job_events_total",
            "onclave_vault_pipeline_stage_events_total",
            "onclave_vault_provider_requests_total",
            "onclave_vault_delivery_attempts_total",
        ]
        summaries = [
            "onclave_transcript_attempt_duration_seconds",
            "onclave_vault_pipeline_stage_duration_seconds",
            "onclave_vault_provider_request_duration_seconds",
            "onclave_vault_delivery_attempt_duration_seconds",
        ]
        metrics = "\n".join(
            [
                line
                for family in counters
                for line in (f"# HELP {family} help", f"# TYPE {family} counter")
            ]
            + [
                line
                for family in summaries
                for line in (f"# HELP {family} help", f"# TYPE {family} summary")
            ]
        )
        health = {
            "status": "ok",
            "git_sha": expected_sha,
            "build_date": "date",
            "app_version": "version",
            "broker": {"connected": True, "topologyDeclared": True},
            "transcript": {
                "status": "ok",
                "degraded": False,
                "degradedSince": None,
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

        class Response:
            def __init__(self, status: int, content_type: str, body: str):
                self.status = status
                self.headers = {"content-type": content_type}
                self.body = body.encode()

            def read(self, _limit: int) -> bytes:
                return self.body

            def close(self) -> None:
                pass

        def command(argv: list[str], **_kwargs):
            if argv[0] == "systemctl":
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="ActiveState=active\nSubState=running\nMainPID=123\nNRestarts=0\n",
                    stderr="",
                )
            container = argv[-1]
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    [
                        {
                            "Id": f"id-{container}",
                            "State": {"Status": "running", "ExitCode": 0},
                            "RestartCount": 0,
                        }
                    ]
                ),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            quadlet = root / "onclave-core.container"
            environment = root / "core.env"
            quadlet.write_text(
                'HealthCmd=node -e \'fetch("http://127.0.0.1:8000/live").then(response => '
                "{ if (!response.ok) process.exit(1); }).catch(() => process.exit(1))'\n",
                encoding="utf-8",
            )
            environment.write_text(
                "ONCLAVE_VAULT_EMBEDDING_PROVIDER=ollama\n"
                "ONCLAVE_VAULT_UNIFIED_PIPELINE_ENABLED=true\n"
                "ONCLAVE_VAULT_UNIFIED_PIPELINE_PROVIDER=openrouter\n",
                encoding="utf-8",
            )

            def execute(checks: dict[str, str]) -> str:
                def request(url: str, timeout: int):
                    self.assertEqual(timeout, 5)
                    path = "/" + url.rsplit("/", 1)[1]
                    if path == "/live":
                        return Response(200, "application/json", json.dumps({"status": "ok"}))
                    if path == "/health":
                        return Response(200, "application/json", json.dumps(health))
                    if path == "/ready":
                        return Response(
                            200,
                            "application/json",
                            json.dumps({"status": "ready", "checks": checks}),
                        )
                    return Response(
                        200,
                        "text/plain; version=0.0.4; charset=utf-8",
                        metrics,
                    )

                output = io.StringIO()
                with (
                    mock.patch.object(
                        sys,
                        "argv",
                        [
                            "validator",
                            expected_sha,
                            "18080",
                            "/live",
                            str(environment),
                            str(quadlet),
                        ],
                    ),
                    mock.patch("subprocess.run", side_effect=command),
                    mock.patch("urllib.request.urlopen", side_effect=request),
                    redirect_stdout(output),
                ):
                    exec(compile(validator, "strict-rc-validator", "exec"), {})
                return output.getvalue()

            base_checks = {
                "postgres": "ok",
                "s3": "ok",
                "ollama": "ok",
                "broker": "ok",
            }
            with self.assertRaisesRegex(RuntimeError, "configured providers"):
                execute(base_checks)
            accepted = json.loads(execute({**base_checks, "openrouter": "ok"}))
            self.assertEqual(accepted["endpoints"]["ready"]["checks"]["openrouter"], "ok")

    def test_core_rollout_restarts_only_native_core_quadlet(self) -> None:
        plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
        rollout_play = plays[-1]
        source = PLAYBOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("onclave-core.container", source)
        self.assertIn("env/core.env", source)
        self.assertIn("name: onclave-core.service", source)
        self.assertIn("Image={{ onclave_core_rollout_image }}", source)
        self.assertIn("GIT_SHA={{ onclave_core_rollout_expected_sha }}", source)
        self.assertIn("regexp: '^HealthCmd='", source)
        self.assertIn("onclave_core_rollout_health_path", source)
        self.assertIn('"affected_units": [core]', source)
        self.assertIn('"explicit_restart_action_count": 1', source)
        self.assertIn('"systemd_automatic_restarts"', source)
        self.assertIn('"container_automatic_restarts"', source)
        self.assertIn('fetch("/live")', source)
        self.assertIn('fetch("/health")', source)
        self.assertIn('fetch("/ready")', source)
        self.assertIn('fetch("/metrics")', source)
        self.assertIn("onclave_vault_delivery_attempt_duration_seconds", source)
        self.assertNotIn("onclave-onramp.target", source)
        self.assertEqual(rollout_play["hosts"], "onramp_host")

    def test_log_redaction_is_bounded(self) -> None:
        text = (
            "Authorization: Bearer secret-token\n"
            "password=secret-value\n"
            '{"api_key":"json-secret"}\n'
            "amqp://user:uri-secret@broker/onclave\n" + ("x" * 5000 + "\n") * 250
        )
        result = redactor.redact(text)
        self.assertNotIn("secret-token", result)
        self.assertNotIn("secret-value", result)
        self.assertNotIn("json-secret", result)
        self.assertNotIn("uri-secret", result)
        self.assertLessEqual(len(result.splitlines()), redactor.MAX_LINES)
        self.assertTrue(all(len(line) <= redactor.MAX_LINE_LENGTH for line in result.splitlines()))


if __name__ == "__main__":
    unittest.main()

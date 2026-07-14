from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


journal_module = load_module("update_session_script", "update-session.py")
evidence_module = load_module("execution_evidence_script", "validate-execution-evidence.py")


class HostPythonSelectorTests(unittest.TestCase):
    def run_selector(self, platform_name: str, successes: set[str]) -> subprocess.CompletedProcess[str]:
        bash = shutil.which("bash")
        assert bash
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ("uname", "py", "python3.13", "python3.12", "python3.11", "python3", "python"):
                (directory / name).write_text(
                    "#!/bin/sh\n"
                    f"if [ \"$(basename \"$0\")\" = \"uname\" ]; then echo {platform_name}; exit 0; fi\n"
                    "name=$(basename \"$0\")\n"
                    "case \"$name:$1\" in\n"
                    + "".join(
                        f"  {name}:{'-' + value if name == 'py' else '-c'}) exit 0 ;;\n"
                        for name, value in (item.split(":", 1) for item in successes)
                    )
                    + "esac\nexit 1\n",
                    encoding="utf-8",
                )
                (directory / name).chmod(0o755)
            environment = os.environ | {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}
            return subprocess.run([bash, str(ROOT / "scripts" / "host-python.sh"), "-c", "pass"], text=True, capture_output=True, env=environment, check=False)

    def test_windows_py_candidates_and_failures(self) -> None:
        for version in ("3.11", "3.12", "3.13"):
            with self.subTest(version=version):
                result = self.run_selector("MINGW64_NT", {f"py:{version}"})
                self.assertEqual(result.returncode, 0)
        self.assertNotEqual(self.run_selector("MINGW64_NT", {"py:3.10"}).returncode, 0)
        self.assertIn("CPython 3.11 or newer", self.run_selector("MINGW64_NT", set()).stderr)

    def test_posix_versioned_and_generic_candidates(self) -> None:
        self.assertEqual(self.run_selector("Linux", {"python3.12:ok"}).returncode, 0)
        self.assertEqual(self.run_selector("Linux", {"python:ok"}).returncode, 0)
        self.assertNotEqual(self.run_selector("Linux", set()).returncode, 0)


class JournalTests(unittest.TestCase):
    def make_journal(self) -> tuple[tempfile.TemporaryDirectory[str], object]:
        temporary = tempfile.TemporaryDirectory()
        now = dt.datetime(2026, 7, 14, 12, 0, 0, tzinfo=dt.timezone.utc)
        journal = journal_module.Journal.create(
            Path(temporary.name) / "update-runs",
            clock=lambda: now,
            token_source=lambda _size: "deadbeef",
        )
        return temporary, journal

    def test_schema_and_sequence(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            event = journal.read_events()[0]
            self.assertEqual(event["episode_id"], "20260714T120000Z-deadbeef")
            self.assertEqual(event["event_id"], "20260714T120000Z-deadbeef-000001")
            self.assertEqual(event["sequence"], 1)
            self.assertEqual(event["schema_version"], 1)

    def test_interrupted_command_reduction(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            journal.append_event(journal_module.event_template(
                "command_started", status="running", started_at="2026-07-14T12:00:01Z", completed_at=None,
                command_id="command-1", recipe="validate", command_argv=["just", "validate"],
                mutation_boundaries=["episode_files"],
            ))
            reduced = journal_module.reduce_commands(journal.read_events())
            self.assertEqual(reduced[0].status, "incomplete")
            self.assertEqual(reduced[0].failure_code, "interrupted-unknown")

    def test_lock_contention(self) -> None:
        temporary, journal = self.make_journal()
        with temporary, journal.lock():
            with self.assertRaisesRegex(journal_module.JournalError, "inspect"):
                journal.append_event(journal_module.event_template(
                    "episode_started", status="started", started_at="2026-07-14T12:00:00Z", completed_at="2026-07-14T12:00:00Z"
                ))

    def test_stale_lock_fails_closed(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            lock_path = journal.episode_dir / ".lock"
            lock_path.mkdir(mode=0o700)
            (lock_path / "owner.json").write_text('{"pid":1}', encoding="utf-8")
            with self.assertRaises(journal_module.JournalError):
                journal.start()
            self.assertTrue(lock_path.is_dir())
            self.assertTrue((lock_path / "owner.json").exists())

    def test_lock_release_cannot_delete_a_concurrently_reacquired_lock(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            lock = journal.lock()
            lock.__enter__()
            lock_path = journal.episode_dir / ".lock"
            original_rename = journal_module.os.rename

            def reacquire_after_release(source, destination):
                result = original_rename(source, destination)
                if Path(source) == lock_path:
                    lock_path.mkdir(mode=0o700)
                    (lock_path / "owner.json").write_text('{"pid":2}', encoding="utf-8")
                return result

            with mock.patch.object(journal_module.os, "rename", side_effect=reacquire_after_release):
                lock.__exit__(None, None, None)
            self.assertTrue(lock_path.is_dir())
            self.assertEqual((lock_path / "owner.json").read_text(encoding="utf-8"), '{"pid":2}')

    def test_lock_release_retries_transient_windows_access_denial(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            lock = journal.lock()
            lock.__enter__()
            original_rename = journal_module.os.rename
            attempts = 0

            def transient_rename(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("transient access denial")
                return original_rename(source, destination)

            with (
                mock.patch.object(journal_module, "platform_os_name", return_value="nt"),
                mock.patch.object(journal_module.os, "rename", side_effect=transient_rename),
                mock.patch.object(journal_module.time, "sleep") as sleep,
            ):
                lock.__exit__(None, None, None)
            self.assertEqual(attempts, 2)
            sleep.assert_called_once_with(0.02)
            self.assertFalse((journal.episode_dir / ".lock").exists())

    def test_lock_release_denial_exhaustion_and_posix_fail_closed(self) -> None:
        for platform_name, expected_attempts, expected_sleeps in (("nt", 5, 4), ("posix", 1, 0)):
            with self.subTest(platform_name=platform_name):
                temporary, journal = self.make_journal()
                with temporary:
                    lock = journal.lock()
                    lock.__enter__()
                    with (
                        mock.patch.object(journal_module, "platform_os_name", return_value=platform_name),
                        mock.patch.object(journal_module.os, "rename", side_effect=PermissionError("access denied")) as rename,
                        mock.patch.object(journal_module.time, "sleep") as sleep,
                    ):
                        with self.assertRaises(PermissionError):
                            lock.__exit__(None, None, None)
                    self.assertEqual(rename.call_count, expected_attempts)
                    self.assertEqual(sleep.call_count, expected_sleeps)
                    self.assertTrue((journal.episode_dir / ".lock" / "owner.json").is_file())

    def test_torn_tail_is_rejected(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            with (journal.episode_dir / "events.jsonl").open("ab") as handle:
                handle.write(b'{"partial"')
            with self.assertRaisesRegex(journal_module.JournalError, "torn"):
                journal.read_events()

    def test_events_symlink_is_not_followed_during_append(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            external = Path(temporary.name) / "external-events.jsonl"
            external.write_bytes(b"external\n")
            journal.events_path.unlink()
            journal.events_path.symlink_to(external)
            with self.assertRaisesRegex(journal_module.JournalError, "symlink or reparse|safely open"):
                journal.append_event(journal_module.event_template(
                    "command_started", status="running", started_at="2026-07-14T12:00:01Z", completed_at=None,
                    command_id="command-1", recipe="validate", command_argv=["just", "validate"],
                    mutation_boundaries=["episode_files"],
                ))
            self.assertEqual(external.read_bytes(), b"external\n")

    def test_command_id_cannot_be_reused_after_terminal_event(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            for event_type, status, completed_at, exit_code in (
                ("command_started", "running", None, None),
                ("command_completed", "passed", "2026-07-14T12:00:02Z", 0),
            ):
                journal.append_event(journal_module.event_template(
                    event_type, status=status, started_at="2026-07-14T12:00:01Z", completed_at=completed_at,
                    command_id="command-1", recipe="validate", command_argv=["just", "validate"],
                    mutation_boundaries=["episode_files"], exit_code=exit_code,
                ))
            with self.assertRaisesRegex(journal_module.JournalError, "reused"):
                journal.append_event(journal_module.event_template(
                    "command_started", status="running", started_at="2026-07-14T12:00:03Z", completed_at=None,
                    command_id="command-1", recipe="validate", command_argv=["just", "validate"],
                    mutation_boundaries=["episode_files"],
                ))

    def test_child_output_is_terminal_only(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            self.assertNotIn("test-secret-output", (journal.episode_dir / "events.jsonl").read_text(encoding="utf-8"))

    def test_structured_evidence_retains_utility(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            event = journal.read_events()[0]
            self.assertEqual(event["status"], "started")
            self.assertEqual(event["started_at"], "2026-07-14T12:00:00Z")
            self.assertEqual(event["evidence_paths"], [])

    def test_path_boundary(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.start()
            with self.assertRaises(journal_module.JournalError):
                journal.append_event(journal_module.event_template(
                    "command_started", status="running", started_at="2026-07-14T12:00:01Z", completed_at=None,
                    command_id="command-1", recipe="plan", command_argv=["just", "plan"],
                    mutation_boundaries=["episode_files"], evidence_paths=["../outside"],
                ))

    def test_journal_root_ancestor_symlink_is_rejected_before_external_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            external = Path(temporary) / "external"
            repository.mkdir()
            external.mkdir()
            (repository / ".tmp").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(journal_module.JournalError, "symlink or reparse"):
                journal_module.Journal.create(repository / ".tmp" / "update-runs")
            self.assertFalse((external / "update-runs").exists())


class RunnerTests(unittest.TestCase):
    def make_journal(self) -> tuple[tempfile.TemporaryDirectory[str], object]:
        temporary = tempfile.TemporaryDirectory()
        journal = journal_module.Journal.create(
            Path(temporary.name) / "update-runs",
            clock=lambda: dt.datetime(2026, 7, 14, 12, 0, 0, tzinfo=dt.timezone.utc),
            token_source=lambda size: "deadbeef" if size == 4 else "a" * 16,
        )
        journal.start()
        return temporary, journal

    class Process:
        def __init__(self, return_code: int) -> None:
            self.return_code = return_code
            self.pid = os.getpid()
            self.waits = 0

        def wait(self) -> int:
            self.waits += 1
            return self.return_code

        def terminate(self) -> None:
            pass

    def test_host_recipe_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(ROOT / "scripts" / "host-python.sh", scripts / "host-python.sh")
            shutil.copy2(ROOT / "scripts" / "update-session.py", scripts / "update-session.py")
            fake = root / "fake-bin"
            fake.mkdir()
            (fake / "just").write_text(
                "#!/usr/bin/env bash\nprintf '%s|%s\\n' \"$*\" \"$PWD\" >> \"$FAKE_JUST_LOG\"\nprintf '%s\\n' 'test-secret-output'\nprintf '%s\\n' 'test-secret-output' >&2\nexit 37\n",
                encoding="utf-8",
            )
            (fake / "just").chmod(0o755)
            (fake / "just.cmd").write_text(
                "@echo off\r\necho %*|%CD%>>\"%FAKE_JUST_LOG%\"\r\necho test-secret-output\r\necho test-secret-output 1>&2\r\nexit /b 37\r\n",
                encoding="utf-8",
            )
            bash = shutil.which("bash")
            assert bash
            if os.name == "nt":
                shutil.copy2(bash, fake / "just.exe")
                (root / "validate").write_text(
                    "#!/usr/bin/env bash\nprintf '%s|%s\\n' \"$*\" \"$PWD\" >> \"$FAKE_JUST_LOG\"\nprintf '%s\\n' 'test-secret-output'\nprintf '%s\\n' 'test-secret-output' >&2\nexit 37\n",
                    encoding="utf-8",
                )
            log = root / "just.log"
            environment = os.environ | {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "FAKE_JUST_LOG": str(log)}
            start = subprocess.run([bash, str(scripts / "host-python.sh"), str(scripts / "update-session.py"), "start"], cwd=root, text=True, capture_output=True, env=environment, check=False)
            self.assertEqual(start.returncode, 0, start.stderr)
            episode = start.stdout.strip()
            result = subprocess.run([bash, str(scripts / "host-python.sh"), str(scripts / "update-session.py"), "run", "--episode", episode, "validate"], cwd=root, text=True, capture_output=True, env=environment, check=False)
            self.assertEqual(result.returncode, 37, result.stderr)
            self.assertIn("test-secret-output", result.stdout)
            self.assertIn("test-secret-output", result.stderr)
            expected_log = f"|{root.as_posix()}" if os.name == "nt" else f"validate|{root}"
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), [expected_log])
            episode_dir = root / ".tmp" / "update-runs" / episode
            events = [json.loads(line) for line in (episode_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1]["command_argv"], ["just", "validate"])
            self.assertFalse(any(b"test-secret-output" in path.read_bytes() for path in episode_dir.rglob("*") if path.is_file()))
            self.assertEqual(events[-1]["status"], "failed")

    def test_exit_code_parity(self) -> None:
        for code in (0, 1, 125, 126, 127, 128, 255):
            with self.subTest(code=code):
                temporary, journal = self.make_journal()
                with temporary:
                    process = self.Process(code)
                    runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: process)
                    self.assertEqual(runner.run("update"), code)
                    self.assertEqual(process.waits, 1)
                    event = journal.read_events()[-1]
                    self.assertEqual(event["exit_code"], code)
                    self.assertEqual(event["signal"], None)

    def test_forbidden_inputs_spawn_nothing(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            spawned = 0
            def factory(*args, **kwargs):
                nonlocal spawned
                spawned += 1
                return self.Process(0)
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=factory)
            for recipe in ("apply", "validate; rm -rf /", "", "plan extra"):
                with self.subTest(recipe=recipe):
                    with self.assertRaises(journal_module.JournalError):
                        runner.run(recipe)
            self.assertEqual(spawned, 0)
            for arguments in (("run", "--episode", journal.episode_id, "apply"), ("run", "--episode", journal.episode_id, "validate", "extra")):
                with self.assertRaises(SystemExit) as raised:
                    journal_module.main(list(arguments))
                self.assertEqual(raised.exception.code, 2)

    def test_mutation_declarations(self) -> None:
        expected = {
            "update": ["episode_files", "tracked_or_private_pins", "private_artifacts", "tooling_workdirs", "docker_runtime_cache"],
            "validate": ["episode_files", "private_values_migration", "tooling_workdirs", "generated_python_cache", "docker_runtime_cache"],
            "plan": ["episode_files", "private_values_migration", "root_plan_artifacts", "tooling_workdirs", "docker_runtime_cache"],
        }
        for recipe, boundaries in expected.items():
            with self.subTest(recipe=recipe):
                temporary, journal = self.make_journal()
                with temporary:
                    cwd = Path(temporary.name)
                    if recipe == "plan":
                        (cwd / "tfplan").write_bytes(b"plan")
                        (cwd / "tfplan.meta.json").write_bytes(b"metadata")
                    runner = journal_module.RecipeRunner(journal, cwd, process_factory=lambda *args, **kwargs: self.Process(0))
                    self.assertEqual(runner.run(recipe), 0)
                    self.assertEqual(journal.read_events()[-1]["mutation_boundaries"], boundaries)

    def test_plan_artifact_identity(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            cwd = Path(temporary.name)
            (cwd / "tfplan").write_bytes(b"plan contents are not copied")
            (cwd / "tfplan.meta.json").write_bytes(b"metadata")
            runner = journal_module.RecipeRunner(journal, cwd, process_factory=lambda *args, **kwargs: self.Process(0))
            self.assertEqual(runner.run("plan"), 0)
            event = journal.read_events()[-1]
            self.assertEqual(event["evidence_paths"], ["plan-artifacts.json"])
            evidence = json.loads((journal.episode_dir / "plan-artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual([row["path"] for row in evidence], ["tfplan", "tfplan.meta.json"])
            self.assertNotIn("plan contents", (journal.episode_dir / "plan-artifacts.json").read_text(encoding="utf-8"))

    def test_exit_status_truth_table(self) -> None:
        for code in (0, 1, 125, 126, 127, 128, 255):
            with self.subTest(exit_code=code):
                temporary, journal = self.make_journal()
                with temporary:
                    runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(code))
                    self.assertEqual(runner.run("validate"), code)
                    event = journal.read_events()[-1]
                    self.assertEqual(event["event_type"], "command_completed")
                    self.assertEqual(event["exit_code"], code)
                    self.assertEqual(event["status"], "passed" if code == 0 else "failed")
        if os.name == "posix":
            temporary, journal = self.make_journal()
            with temporary:
                runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(-signal.SIGTERM))
                self.assertEqual(runner.run("validate"), 128 + signal.SIGTERM)
                event = journal.read_events()[-1]
                self.assertEqual((event["event_type"], event["signal"]), ("command_interrupted", signal.SIGTERM))

    def test_windows_nonnegative_return_code_contract(self) -> None:
        temporary, journal = self.make_journal()
        with temporary, mock.patch.object(journal_module, "platform_os_name", return_value="nt"):
            code = 0xC000013A
            runner = journal_module.RecipeRunner(
                journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(code),
            )
            self.assertEqual(runner.run("validate"), code)
            event = journal.read_events()[-1]
            self.assertEqual((event["event_type"], event["exit_code"], event["signal"]), ("command_completed", code, None))
            events = journal.read_events()
        with mock.patch.object(journal_module, "platform_os_name", return_value="posix"):
            with self.assertRaisesRegex(journal_module.JournalError, "exit status"):
                journal_module.validate_events(events, journal.episode_id, journal.episode_dir)

    def test_signal_and_journal_failure_precedence(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            spawned = 0
            def no_spawn(*args, **kwargs):
                nonlocal spawned
                spawned += 1
                return self.Process(0)
            journal.append_event = lambda event: (_ for _ in ()).throw(journal_module.JournalError("start write failed"))
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=no_spawn)
            self.assertEqual(runner.run("update"), 125)
            self.assertEqual(spawned, 0)
        temporary, journal = self.make_journal()
        with temporary:
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
            self.assertEqual(runner.run("update"), 127)
            self.assertEqual(journal.read_events()[-1]["failure_code"], "spawn-not-found")
        temporary, journal = self.make_journal()
        with temporary:
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))
            self.assertEqual(runner.run("update"), 126)
            self.assertEqual(journal.read_events()[-1]["failure_code"], "spawn-denied")
        temporary, journal = self.make_journal()
        with temporary:
            original = journal.append_event
            calls = 0
            def fail_terminal(event):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise journal_module.JournalError("terminal append failed")
                original(event)
            journal.append_event = fail_terminal
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(0))
            self.assertEqual(runner.run("update"), 125)
            self.assertEqual(len(journal.read_events()), 2)
        temporary, journal = self.make_journal()
        with temporary:
            def broken_builder(event_type, **kwargs):
                if event_type == "command_completed":
                    raise RuntimeError("terminal construction failed")
                return journal_module.event_template(event_type, **kwargs)
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(0), event_builder=broken_builder)
            self.assertEqual(runner.run("update"), 125)
            self.assertEqual(len(journal.read_events()), 2)
        temporary, journal = self.make_journal()
        with temporary:
            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: self.Process(0))
            self.assertEqual(runner.run("plan"), 125)
            self.assertEqual(len(journal.read_events()), 2)
        if os.name == "posix":
            temporary, journal = self.make_journal()
            with temporary:
                class InterruptedProcess(self.Process):
                    pid = 999999
                    def wait(self):
                        self.waits += 1
                        if self.waits == 1:
                            raise KeyboardInterrupt()
                        return -signal.SIGINT
                process = InterruptedProcess(0)
                runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: process)
                self.assertEqual(runner.run("validate"), 128 + signal.SIGINT)
                self.assertEqual(process.waits, 2)
                self.assertEqual(journal.read_events()[-1]["event_type"], "command_interrupted")
        if os.name == "posix":
            temporary, journal = self.make_journal()
            with temporary:
                class SigtermProcess(self.Process):
                    pid = 999999
                    def wait(self):
                        self.waits += 1
                        if self.waits == 1:
                            handler = signal.getsignal(signal.SIGTERM)
                            handler(signal.SIGTERM, None)
                        return 0
                process = SigtermProcess(0)
                runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=lambda *args, **kwargs: process)
                with mock.patch.object(journal_module.os, "killpg") as killpg:
                    self.assertEqual(runner.run("validate"), 128 + signal.SIGTERM)
                killpg.assert_called_once_with(process.pid, signal.SIGTERM)
                self.assertEqual(process.waits, 2)
                terminals = [event for event in journal.read_events() if event["event_type"].startswith("command_") and event["event_type"] != "command_started"]
                self.assertEqual(len(terminals), 1)
                self.assertEqual((terminals[0]["event_type"], terminals[0]["signal"]), ("command_interrupted", signal.SIGTERM))


class ReflectionTests(unittest.TestCase):
    def make_journal(self) -> tuple[tempfile.TemporaryDirectory[str], object]:
        temporary = tempfile.TemporaryDirectory()
        journal = journal_module.Journal.create(
            Path(temporary.name) / "update-runs",
            clock=lambda: dt.datetime(2026, 7, 14, 12, 0, 0, tzinfo=dt.timezone.utc),
            token_source=lambda size: "deadbeef" if size == 4 else "a" * 16,
        )
        journal.start()
        return temporary, journal

    def run_failure(self, journal: object, code: int = 19) -> None:
        process = RunnerTests.Process(code)
        runner = journal_module.RecipeRunner(
            journal, Path(journal.episode_dir.parent.parent), process_factory=lambda *args, **kwargs: process,
        )
        self.assertEqual(runner.run("validate"), code)

    def test_known_taxonomy(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            self.run_failure(journal)
            self.assertEqual(journal_module.reflect(journal), 0)
            summary = json.loads((journal.episode_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["classifications"], [{"event_id": "20260714T120000Z-deadbeef-000003", "failure_code": "command-failed"}])
            self.assertEqual(summary["recommendations"], [{"event_ids": ["20260714T120000Z-deadbeef-000003"], "kind": "no-action"}])
            self.assertEqual(journal_module.verify(journal), 0)

    def test_unknown_does_not_guess(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            journal.append_event(journal_module.event_template(
                "command_started", status="running", started_at="2026-07-14T12:00:01Z", completed_at=None,
                command_id="command-unknown", recipe="validate", command_argv=["just", "validate"],
                mutation_boundaries=["episode_files"],
            ))
            self.assertEqual(journal_module.reflect(journal), 0)
            failures = (journal.episode_dir / "failures.md").read_text(encoding="utf-8")
            self.assertIn('"interrupted-unknown"', failures)
            self.assertIn('"no-action"', failures)
            self.assertEqual(journal_module.verify(journal), 0)

    def test_failure_episode_contract(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            self.run_failure(journal)
            self.assertEqual(journal_module.reflect(journal), 0)
            for name in ("events.jsonl", "summary.json", "failures.md", "commands.md"):
                self.assertTrue((journal.episode_dir / name).stat().st_size > 0)
            self.assertEqual(journal_module.verify(journal), 0)
            (journal.episode_dir / "commands.md").write_text("tampered\n", encoding="utf-8")
            self.assertEqual(journal_module.verify(journal), 1)

    def test_reflection_holds_one_lock_through_completion_append(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            original_write = journal_module.write_report_files

            def check_interleaving(*args, **kwargs):
                with self.assertRaisesRegex(journal_module.JournalError, "inspect"):
                    journal.append_event(journal_module.event_template(
                        "command_started", status="running", started_at="2026-07-14T12:00:01Z", completed_at=None,
                        command_id="command-interloper", recipe="validate", command_argv=["just", "validate"],
                        mutation_boundaries=["episode_files"],
                    ))
                original_write(*args, **kwargs)

            with mock.patch.object(journal_module, "write_report_files", side_effect=check_interleaving):
                self.assertEqual(journal_module.reflect(journal), 0)
            reflections = [event for event in journal.read_events() if event["event_type"] == "reflection_completed"]
            self.assertEqual(len(reflections), 1)

    def test_summary_must_use_exact_canonical_utf8_bytes(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            self.run_failure(journal)
            self.assertEqual(journal_module.reflect(journal), 0)
            summary_path = journal.episode_dir / "summary.json"
            canonical = summary_path.read_bytes()
            summary = json.loads(canonical)
            variants = (
                json.dumps(dict(reversed(list(summary.items()))), separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n",
                json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=True).encode("utf-8") + b"\n",
                canonical.rstrip(b"\n"),
            )
            for content in variants:
                with self.subTest(content=content):
                    summary_path.write_bytes(content)
                    self.assertEqual(journal_module.verify(journal), 1)
            summary_path.write_bytes(canonical)
            self.assertEqual(journal_module.verify(journal), 0)

    def test_start_reflect_verify_truth_table(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            self.assertEqual(journal_module.verify(journal), 1)
            self.assertEqual(journal_module.reflect(journal), 0)
            self.assertEqual(journal_module.verify(journal), 0)
            with (journal.episode_dir / "events.jsonl").open("ab") as handle:
                handle.write(b'{"torn"')
            self.assertEqual(journal_module.reflect(journal), 1)
            self.assertEqual(journal_module.verify(journal), 1)

        failures = [("construction", None)]
        failures.extend((f"replace-{name}", name) for name in journal_module.REPORT_FILENAMES)
        failures.extend((("temporary-write", None), ("fsync", None)))
        for failure_name, failed_report in failures:
            with self.subTest(failure=failure_name):
                temporary, journal = self.make_journal()
                with temporary:
                    tokens = iter(("1" * 16, "2" * 16, "3" * 16))
                    journal.token_source = lambda _size: next(tokens)
                    self.assertEqual(journal_module.reflect(journal), 0)
                    original_replace = journal_module.os.replace
                    original_open = Path.open
                    original_fsync = journal_module.os.fsync

                    def fail_one_replace(source, destination):
                        if failed_report is not None and Path(destination).name == failed_report:
                            raise OSError("injected report replacement failure")
                        return original_replace(source, destination)

                    def fail_temporary_write(path, *args, **kwargs):
                        if path.name.startswith(".summary.json.") and args == ("xb",):
                            raise OSError("injected report temporary-write failure")
                        return original_open(path, *args, **kwargs)

                    fsync_calls = 0

                    def fail_report_fsync(descriptor):
                        nonlocal fsync_calls
                        fsync_calls += 1
                        if fsync_calls == 2:
                            raise OSError("injected report fsync failure")
                        return original_fsync(descriptor)

                    if failure_name == "construction":
                        patcher = mock.patch.object(
                            journal_module,
                            "render_summary",
                            side_effect=journal_module.JournalError("injected report construction failure"),
                        )
                    elif failure_name == "temporary-write":
                        patcher = mock.patch.object(Path, "open", new=fail_temporary_write)
                    elif failure_name == "fsync":
                        patcher = mock.patch.object(journal_module.os, "fsync", side_effect=fail_report_fsync)
                    else:
                        patcher = mock.patch.object(journal_module.os, "replace", side_effect=fail_one_replace)
                    with patcher:
                        self.assertEqual(journal_module.reflect(journal), 125)
                    reflections = [event for event in journal.read_events() if event["event_type"] == "reflection_completed"]
                    self.assertEqual(len(reflections), 1)
                    expected_verify = 1 if failed_report in {"failures.md", "commands.md"} else 0
                    self.assertEqual(journal_module.verify(journal), expected_verify)
                    self.assertEqual(journal_module.reflect(journal), 0)
                    self.assertEqual(journal_module.verify(journal), 0)
                    reports = [
                        (journal.episode_dir / name).read_text(encoding="utf-8")
                        for name in journal_module.REPORT_FILENAMES
                    ]
                    self.assertTrue(all('"report-3333333333333333"' in report for report in reports))

        temporary, journal = self.make_journal()
        with temporary:
            tokens = iter(("1" * 16, "2" * 16, "3" * 16))
            journal.token_source = lambda _size: next(tokens)
            self.assertEqual(journal_module.reflect(journal), 0)
            original_append = journal._append_event_locked

            def fail_completion(event):
                if event["event_type"] == "reflection_completed":
                    raise journal_module.JournalError("injected completion append failure")
                return original_append(event)

            with mock.patch.object(journal, "_append_event_locked", side_effect=fail_completion):
                self.assertEqual(journal_module.reflect(journal), 125)
            reflections = [event for event in journal.read_events() if event["event_type"] == "reflection_completed"]
            self.assertEqual(len(reflections), 1)
            self.assertEqual(journal_module.verify(journal), 1)
            self.assertEqual(journal_module.reflect(journal), 0)
            self.assertEqual(journal_module.verify(journal), 0)

    def test_invalid_start_reflect_verify_arguments_return_two(self) -> None:
        episode = "20260714T120000Z-deadbeef"
        cases = (
            ["start", "extra"],
            ["reflect"],
            ["reflect", "--episode", episode, "extra"],
            ["verify"],
            ["verify", "--episode", "invalid"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), mock.patch.object(journal_module.sys, "stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as raised:
                    journal_module.main(arguments)
                self.assertEqual(raised.exception.code, 2)

    def test_malformed_event_schema_returns_status_one_without_traceback(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            events = journal.read_events()
            events[0]["evidence_paths"] = {"not": "a list"}
            journal.events_path.write_text(
                "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
                encoding="utf-8",
            )
            for operation in (journal_module.reflect, journal_module.verify):
                with self.subTest(operation=operation.__name__), mock.patch.object(journal_module.sys, "stderr", new_callable=io.StringIO) as stderr:
                    self.assertEqual(operation(journal), 1)
                    self.assertNotIn("Traceback", stderr.getvalue())

    def test_malformed_utf8_events_return_status_one_without_replacing_reports(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            self.assertEqual(journal_module.reflect(journal), 0)
            before = {name: (journal.episode_dir / name).read_bytes() for name in journal_module.REPORT_FILENAMES}
            journal.events_path.write_bytes(b"\xff\n")
            for operation in (journal_module.reflect, journal_module.verify):
                with self.subTest(operation=operation.__name__), mock.patch.object(journal_module.sys, "stderr", new_callable=io.StringIO) as stderr:
                    self.assertEqual(operation(journal), 1)
                    self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(before, {name: (journal.episode_dir / name).read_bytes() for name in journal_module.REPORT_FILENAMES})

    def test_reports_are_safe_and_useful(self) -> None:
        temporary, journal = self.make_journal()
        with temporary:
            def child_factory(*_args, **kwargs):
                return subprocess.Popen(
                    [sys.executable, "-c", "import sys; print('test-secret-output'); print('test-secret-output', file=sys.stderr); raise SystemExit(19)"],
                    cwd=kwargs["cwd"],
                    shell=False,
                )

            runner = journal_module.RecipeRunner(journal, Path(temporary.name), process_factory=child_factory)
            self.assertEqual(runner.run("validate"), 19)
            self.assertEqual(journal_module.reflect(journal), 0)
            reports = "".join((journal.episode_dir / name).read_text(encoding="utf-8") for name in ("summary.json", "failures.md", "commands.md"))
            self.assertIn('"validate"', reports)
            self.assertIn('"command-failed"', reports)
            self.assertNotIn("test-secret-output", reports)


class EndToEndTests(unittest.TestCase):
    def test_explicit_multi_invocation_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = journal_module.Journal.create(root / "update-runs", clock=lambda: dt.datetime(2026, 7, 14, 12, 0, tzinfo=dt.timezone.utc), token_source=lambda size: "deadbeef" if size == 4 else "a" * 16)
            journal.start()
            for command_token, recipe in zip(("a" * 16, "b" * 16), ("update", "validate")):
                journal.token_source = lambda _size, token=command_token: token
                runner = journal_module.RecipeRunner(journal, root, process_factory=lambda *args, **kwargs: RunnerTests.Process(0))
                self.assertEqual(runner.run(recipe), 0)
            self.assertEqual(journal_module.reflect(journal), 0)
            self.assertEqual(journal_module.verify(journal), 0)
            commands = json.loads((journal.episode_dir / "summary.json").read_text(encoding="utf-8"))["command_event_ids"]
            self.assertEqual(len(commands), 2)

    def test_failure_can_always_be_reflected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = journal_module.Journal.create(root / "update-runs", token_source=lambda size: "deadbeef" if size == 4 else "a" * 16)
            journal.start()
            runner = journal_module.RecipeRunner(journal, root, process_factory=lambda *args, **kwargs: RunnerTests.Process(41))
            self.assertEqual(runner.run("validate"), 41)
            self.assertEqual(journal_module.reflect(journal), 0)
            self.assertEqual(journal_module.verify(journal), 0)

    def test_child_failure_precedes_reflection_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = journal_module.Journal.create(root / "update-runs", token_source=lambda size: "deadbeef" if size == 4 else "a" * 16)
            journal.start()
            runner = journal_module.RecipeRunner(journal, root, process_factory=lambda *args, **kwargs: RunnerTests.Process(23))
            child_status = runner.run("validate")
            (journal.episode_dir / ".lock").write_text("held", encoding="utf-8")
            self.assertEqual(journal_module.reflect(journal), 125)
            self.assertEqual(child_status, 23)


class ExecutionEvidenceTests(unittest.TestCase):
    def record(self, sequence: int, task_id: str, archive_status: str = "not_ready") -> dict[str, object]:
        return {
            "episode_id": "update-run-journal", "sequence": sequence,
            "phase_id": evidence_module.PHASES[task_id], "task_id": task_id,
            "validation_command": "scripts/host-python.sh -m unittest fixture", "status": "passed",
            "archive_status": archive_status, "started_at": "2026-07-14T12:00:00Z",
            "completed_at": "2026-07-14T12:00:01Z", "evidence": "tests/test_update_session.py",
        }

    def test_valid_dependency_prefix_and_archived_f5(self) -> None:
        records = [self.record(index, task) for index, task in enumerate(evidence_module.TASKS[:-1], 1)]
        evidence_module.validate_records(records, "F4")
        records.append(self.record(11, "F5", "archived"))
        evidence_module.validate_records(records, "F5", require_archived=True)

    def test_malformed_duplicate_out_of_order_and_mismatched_records_fail(self) -> None:
        records = [self.record(1, "T1")]
        for broken in (
            [{**records[0], "sequence": 2}],
            [{**records[0], "episode_id": "other"}],
            [{**records[0], "status": "failed"}],
            [{key: value for key, value in records[0].items() if key != "evidence"}],
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(evidence_module.EvidenceError):
                    evidence_module.validate_records(broken, "T1")


if __name__ == "__main__":
    unittest.main()

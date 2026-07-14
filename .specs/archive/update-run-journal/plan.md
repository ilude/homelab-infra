---
created: 2026-07-14
status: completed
completed: 2026-07-14
---

# Plan: Deterministic Update Run Journal

## Context & Motivation

A recent homelab update required repeated investigation across Docker availability, OCI registry behavior, changed Forgejo release assets, missing backup dependencies, Windows bind-mount permissions, a Technitium shutdown race, unrelated destructive topology drift, and a final lint failure. Successful commands and recovery evidence existed only in terminal history and conversation context.

This plan adds a local journal that records what actually ran, where it failed, and which evidence supports a bounded process-improvement proposal. It observes existing public commands one at a time. It does not replace their review boundaries, validation results, plan/apply safeguards, backup gates, health checks, or rollback logic.

## Constraints

- Platform: Windows operator workstation with Docker Desktop; Linux tooling container; Debian-based homelab targets.
- Shell: Bash for existing public workflows; CPython 3.11 or newer for the journal CLI. Windows uses Git Bash from Git for Windows.
- The implementation adds `scripts/host-python.sh`. On Windows it probes `py -3.13`, `py -3.12`, then `py -3.11`; on POSIX it probes `python3.13`, `python3.12`, `python3.11`, `python3`, then `python`. Every candidate must report CPython 3.11 or newer. Old-only and absent installations fail with actionable setup guidance.
- `README.md` must add Bash plus CPython 3.11 or newer to local prerequisites and document installation through Python.org, `winget install --exact --id Python.Python.3.13`, or the platform package manager.
- The journal launcher runs on the host as `scripts/host-python.sh scripts/update-session.py`. It must not run through `scripts/python.sh` or recursively enter Docker.
- Existing public workflows remain `just update`, `just validate`, `just plan`, and approved `just apply`.
- One wrapper invocation observes exactly one allowlisted recipe: `update`, `validate`, or `plan`.
- `update` can change tracked source and private pins. `validate` can migrate private values. `plan` removes and replaces repository-root plan artifacts. The wrapper must display and record the applicable boundary before spawning the command.
- The operator retains the review boundary between update, validate, plan, and apply. The journal never automatically advances to another recipe.
- Runtime artifacts stay under ignored `.tmp/update-runs/<episode_id>/` and are sensitive local operational data, not a confidentiality boundary.
- Never persist environment dictionaries, credential values, tokens, private values, real domains, real IPs, raw private inventory, or unredacted child output.
- Child output is hostile. The subprocess inherits the operator terminal directly; the journal persists no opaque stdout/stderr text. Durable evidence is restricted to allowlisted structured metadata and stable failure codes.
- Journal commands accept no secrets and no arbitrary executable command strings in argv.
- Reflection is deterministic and advisory. It cannot modify source, clear an incident, authorize apply, or count as validation evidence.
- Existing uncommitted work must be preserved. Implementation touches only task-listed files.
- No live infrastructure mutation is required for implementation or validation.

## Risk & Manual Gate Decision

- **Risk level:** medium
- **Blast radius:** local/home-lab workflow tooling; allowed recipes have existing local mutation boundaries.
- **Rollback:** easy for tracked implementation files; existing public commands remain unchanged.
- **Manual approval before action:** not required
- **Manual validation after action:** not required
- **Decision reason:** implementation and tests do not perform live apply. Running a wrapped public recipe is the same explicit operator action as running that recipe directly. Tests use a fake `just`; final validation wraps only `just validate`, which is already the required repository validation entry point.

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Free-form reflection after failures | Minimal code | Non-deterministic; can invent causes; loses exact command status | Rejected |
| Multi-phase `run --through` orchestration | Automatic sequence and one episode | Collapses review boundaries, misstates mutation scope, and causes nested Docker when launched in the tooling container | Rejected |
| Host-side wrapper around one allowlisted public recipe with explicit episode joining | Preserves existing commands and review boundaries; correct Docker boundary; durable episode evidence | Requires the operator to pass an episode ID between invocations | **Selected** |
| Full apply/recovery orchestrator | Can observe live recovery directly | Requires backup, canary, endpoint/state, rollback, and incident-clearance design beyond this MVP | Rejected for this plan |

## Objective

Provide a tested host-side command that starts an update episode, observes one existing allowlisted public recipe per invocation with exact ordinary-exit parity and defined signal/journal-failure precedence, writes sanitized structured evidence under `.tmp/update-runs/<episode_id>/`, and generates bounded event-linked reflection without changing source or performing live apply.

## MVP Boundary

The MVP supports:

1. `start` to create an episode and print its generated ID.
2. `run --episode <id> update|validate|plan` to execute exactly one immutable public recipe from the repository root.
3. `reflect --episode <id>` to generate `summary.json`, `failures.md`, and `commands.md` from `events.jsonl`.
4. `verify --episode <id>` to validate JSONL schema, episode identity, terminal command events, nonempty reports, and report-to-event references without trusting opaque output.

The journal records the first failure and later observations in sequence, but it does not own workflow progression or resume deployment. This delivers durable command, failure, and process-improvement evidence while preserving the existing operator-controlled workflow.

## Explicit Deferrals

- Automatic `just apply`, `scripts/apply-service.sh`, rollback, recovery annotations, or verified recovery execution.
- Automatic incident clearance or deployment resume.
- Automatic source, rules, documentation, or workflow edits from reflection.
- Transactional refactoring of `scripts/update.py`.
- Automatic backup creation or backup-age enforcement.
- Scheduled upstream contract checks and centralized telemetry.
- Episode purge/retention automation. Operators may manage ignored `.tmp/` data outside the journal after inspecting the exact target.
- Parsing OpenTofu into a second deployment policy engine. Existing plan/apply checks remain authoritative.
- Resolving the current Infisical/onramp topology conflict.

## Project Context

- **Language**: CPython 3.11+ standard library for the host CLI; Bash/Just for existing workflows.
- **Host runtime preflight**: `bash --version >/dev/null && scripts/host-python.sh -c 'import platform,sys; raise SystemExit(sys.version_info < (3, 11) or platform.python_implementation() != "CPython")'`
- **Task test command**: `scripts/host-python.sh -m unittest tests.test_update_session`
- **Syntax command**: `scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py`
- **Lint command**: none detected outside `just validate`
- **Repo-wide validation**: `just validate`

## Adaptive Review Profile

- `plan_profile`: `medium-cross-cutting-workflow`
- `review_panel_decision`: reviewed by six independent personas; auto-applied findings replace orchestration with observation and harden evidence boundaries.
- Expected reviewer count: 6
- Selected personas: completeness, security, product/simplicity, QA, DevOps, and Python/subprocess.
- Complexity score: 6/10
- Risk score: 5/10
- Expected high-risk areas: nested Docker, redaction gaps, swallowed exit codes, partial JSONL writes, path escape, local mutations, ambiguous recovery, and concurrent writers.

## Automation Plan

| Operation | Command/wrapper | Credentials | Mutation boundary | Evidence |
|-----------|-----------------|-------------|-------------------|----------|
| Preflight and baseline | `git status --short && bash --version >/dev/null && baseline=".tmp/update-run-journal-implementation-baselines/$(date -u +%Y%m%dT%H%M%SZ)-$$" && test ! -e "$baseline" && mkdir -p "$baseline" && cp README.md docs/service-update-policy.md "$baseline/" && for path in scripts/host-python.sh scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py README.md docs/service-update-policy.md; do if test -e "$path"; then sha256sum "$path"; else printf 'ABSENT  %s\n' "$path"; fi; done > "$baseline/files.before" && git status --short -- scripts/host-python.sh scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py README.md docs/service-update-policy.md > "$baseline/status.before" && git diff --binary -- README.md docs/service-update-policy.md > "$baseline/docs.before.patch" && : > "$baseline/COMPLETE" && printf '%s\n' "$baseline"` | none | unique `.tmp/` baseline only | executor immediately records printed path as `baseline_path` in Execution Status before edits and declares one writer; no pre-existing baseline is reused |
| Host runtime preflight | `bash -c 'if command -v py >/dev/null 2>&1; then for version in 3.13 3.12 3.11; do py -"$version" -c "import sys; raise SystemExit(sys.version_info < (3, 11) or sys.implementation.name != \"cpython\")" >/dev/null 2>&1 && exit 0; done; fi; for executable in python3.13 python3.12 python3.11 python3 python; do command -v "$executable" >/dev/null 2>&1 || continue; "$executable" -c "import sys; raise SystemExit(sys.version_info < (3, 11) or sys.implementation.name != \"cpython\")" >/dev/null 2>&1 && exit 0; done; printf "Install CPython 3.11 or newer from Python.org, winget, or your platform package manager.\\n" >&2; exit 1'` | none | none | exits 0 only for a supported host interpreter; no Docker invocation |
| Start episode | `episode_id="$(scripts/host-python.sh scripts/update-session.py start)" && printf '%s\n' "$episode_id"` | none | `.tmp/update-runs/<episode_id>/` only | start event and printed ID |
| Observe update | `scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" update` | existing downstream sources; journal records no values | tracked/private pins, private Hermes artifacts, tooling workdirs, and Docker runtime/cache possible | command events and structured evidence |
| Operator review | `git diff --stat && git status --short` | none | none | terminal only; review is not automated away |
| Observe validation | `scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" validate` | existing ignored `values/`; journal records no values | private-values migration possible | command events and documented exit/signal status |
| Observe plan | `scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" plan` | existing ignored `values/`; journal records no values | root plan artifacts removed/replaced | events plus relative plan artifact paths and SHA-256 after success |
| Reflect | `scripts/host-python.sh scripts/update-session.py reflect --episode "$episode_id"` | none | episode reports only | `summary.json`, `failures.md`, `commands.md` |
| Verify implementation | Run the F1 task/syntax gate, then the F2 exact wrapped `just validate` gate | existing ignored private values for repo validation | standard validation migration boundary | F1/F2 exit codes 0 and non-secret episode evidence |
| Deploy | `not applicable` | none | no live mutation | none |
| Rollback implementation | Read the unique `baseline_path` from Execution Status; with the single-writer boundary still active, remove only files marked `ABSENT`, restore `README.md` and `docs/service-update-policy.md` from that baseline, then compare scoped status/diff with its `status.before` and `docs.before.patch` | none | plan-owned files only | exact pre-task public-doc content and scoped Git state restored; missing/mismatched baseline fails closed |

## Task Breakdown

| # | Task | Files | Type | Model | Agent | Depends On |
|---|------|-------|------|-------|-------|------------|
| T1 | Implement host runtime, journal foundation, and evidence validator | 5 | feature | medium | python | -- |
| V1 | Validate wave 1 | -- | validation | medium | validation-lead | T1 |
| T2 | Implement host-side single-recipe observation | 3 | feature | medium | engineering-lead | V1 |
| V2 | Validate wave 2 | -- | validation | medium | validation-lead | T2 |
| T3 | Add deterministic reflection and operator policy | 4 | feature | medium | python | V2 |
| V3 | Validate wave 3 | -- | validation | medium | validation-lead | T3 |

## Execution Waves

### Wave 1

**T1: Implement host runtime, journal foundation, and evidence validator** [medium] -- python
- Description: Add the CPython 3.11+ host selector, journal CLI, execution-evidence validator, and unit tests for episode creation, event persistence, locking, structured evidence, and report inputs. Define schema version 1 with event-specific required/nullable fields.
- Files: `scripts/host-python.sh`, `scripts/update-session.py`, `scripts/validate-execution-evidence.py`, `tests/test_update_session.py`, `README.md`
- Mutation boundary: tracked changes only to listed files; tests write only to temporary directories.
- Alternative: shell `tee` logs. Rejected because they cannot enforce event schema, path containment, locking, or pre-write redaction.
- Contract:
  - Episode IDs use `YYYYMMDDTHHMMSSZ-<8 lowercase hex>` from an injectable UTC clock and token source; input IDs must match exactly.
  - Runtime events follow the complete schema-v1 table in Telemetry & Evidence Contract. Execution-ledger fields such as `phase_id`, `task_id`, `validation_command`, and `archive_status` exist only in `execution-evidence.jsonl`, not runtime episodes.
  - Reports sort by `sequence`; timestamps are evidence metadata, not byte-for-byte reproducibility inputs.
  - One cross-process lock file protects every writer and report reducer. It is created exclusively, includes PID/start metadata, is removed in `finally`, and stale locks fail closed with an inspection instruction. No automatic stale-lock deletion.
  - A `command_started` event is durable before spawning. A missing matching completion is reduced as `interrupted-unknown`, so the plan does not claim impossible post-process/pre-append durability.
  - Each complete JSONL line is written under lock, flushed, and fsynced. A torn final line is rejected and reported; it is never silently ignored or rewritten.
  - Root is fixed to repository `.tmp/update-runs`. Generated episode paths must remain beneath the canonical root. Absolute/traversal IDs, symlinked or junction-like episode components, and evidence outside the episode are rejected.
  - Best-effort restrictive modes are applied to directories/files; the documentation states that Windows local ACL confidentiality is not guaranteed.
  - The child inherits stdout/stderr directly, so terminal behavior remains unchanged and no opaque child text is persisted. The journal records only allowlisted recipe identity, timestamps, mutation boundaries, exit/signal status, artifact hashes, and stable failure codes.
- Acceptance Criteria:
  1. [ ] The host selector chooses a supported CPython 3.11+ interpreter on Windows and POSIX, rejects older versions, verifies Bash availability, and prints documented setup guidance when unavailable.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.HostPythonSelectorTests`
     - Pass: tests cover Windows `py` installations for 3.11, 3.12, 3.13, old-only, and absent cases plus POSIX versioned/generic candidates; Python 3.10 is rejected and no container command runs.
     - Fail: host runtime selection remains a blocker.
  2. [ ] Schema, sequence, injected identity/time, and interrupted-command reduction are deterministic.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.JournalTests.test_schema_and_sequence tests.test_update_session.JournalTests.test_interrupted_command_reduction`
     - Pass: tests exit 0; reports reduce by sequence and incomplete commands remain unknown.
     - Fail: do not proceed; repair schema/reducer before integration.
  3. [ ] Lock contention, stale lock, fsync append, and torn-tail cases fail closed without losing the first complete event.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.JournalTests.test_lock_contention tests.test_update_session.JournalTests.test_stale_lock_fails_closed tests.test_update_session.JournalTests.test_torn_tail_is_rejected`
     - Pass: tests exit 0; no writer merges or repairs evidence silently.
     - Fail: preserve the fixture and fix the durability contract.
  4. [ ] Hostile child output is never persisted; safe structured fields and stable failure codes remain useful.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.JournalTests.test_child_output_is_terminal_only tests.test_update_session.JournalTests.test_structured_evidence_retains_utility`
     - Pass: tests exit 0; seeded stdout/stderr literals appear in no episode artifact while allowlisted fields remain.
     - Fail: any opaque child text in durable artifacts blocks integration.
  5. [ ] Traversal, absolute paths, symlink/junction-like episode paths, invalid IDs, and outside evidence paths are rejected before writes.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.JournalTests.test_path_boundary`
     - Pass: test exits 0 and files outside the temporary root are unchanged.
     - Fail: path-boundary failure blocks all later work.
  6. [ ] Fresh setup declares Bash and CPython 3.11+, with actionable Windows and platform-neutral installation paths while keeping infrastructure tooling containerized.
     - Verify: `grep -F "CPython 3.11 or newer" README.md && grep -F "Git Bash" README.md && grep -F "Python.Python.3.13" README.md && grep -F "Python.org" README.md && grep -F "platform package manager" README.md && grep -F "scripts/host-python.sh" README.md && grep -F "journal helper is the only host Python workflow; infrastructure tooling remains containerized" README.md`
     - Pass: all seven independent checks pass.
     - Fail: host runtime remains undeclared and V1 cannot pass.
  7. [ ] The execution-evidence validator enforces required fields, exact episode/task identity, unique dependency order, UTC timestamps, nonempty command/evidence, passed status, and pre/post archive modes.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.ExecutionEvidenceTests`
     - Pass: tests accept only T1-F4 before move and T1-F5 with archived F5 after move; malformed, duplicate, out-of-order, missing, or mismatched records fail.
     - Fail: V1 and F5 cannot run until ledger validation is deterministic.

### Wave 1 - Validation Gate

**V1: Validate wave 1** [medium] -- validation-lead
- Blocked by: T1
- Checks:
  1. Run all T1 acceptance commands.
  2. `bash --version >/dev/null && scripts/host-python.sh -c 'import platform,sys; raise SystemExit(sys.version_info < (3, 11) or platform.python_implementation() != "CPython")'` exits 0 with no warnings.
  3. `scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py` exits 0.
  4. `scripts/host-python.sh -m unittest tests.test_update_session` exits 0.
  5. Parse every generated fixture event as JSON and confirm no test secret appears in temporary artifacts.
- On failure: add a focused Wave 1 fix task, leave V1 unchecked, and rerun the complete gate.

### Wave 2

**T2: Implement host-side single-recipe observation** [medium] -- engineering-lead
- Blocked by: V1
- Description: Implement `run --episode <id> update|validate|plan` as a host process. Each recipe maps to an immutable argv (`["just", "update"]`, `["just", "validate"]`, or `["just", "plan"]`), repository cwd, `shell=False`, and the inherited environment required by the unchanged public command. The journal never serializes the environment. It persists a start event before spawn, lets the child inherit the terminal, and persists exactly one terminal event after wait/reap. Any extra token, unknown recipe, `apply`, destructive verb, or arbitrary command is rejected before spawning.
- Files: `scripts/host-python.sh`, `scripts/update-session.py`, `tests/test_update_session.py`
- Mutation boundary: fake-`just` tests use temporary directories. Implementation does not modify `justfile` or existing recipes.
- Alternative: instrument every existing script. Rejected because it makes all workflows depend on the journal and creates a larger cross-cutting change.
- Recipe declarations:
  - `update`: may change tracked source/private pins, create private `values/artifacts/hermes/` locks/artifacts, update tooling workdirs, and use Docker runtime/cache; operator review is required before another invocation.
  - `validate`: may run idempotent private-values migrations before checks.
  - `plan`: may run private-values migration, then removes/replaces root plan artifacts. Record both ordered mutation boundaries before spawn. After success, record only relative paths and SHA-256 for `tfplan` and `tfplan.meta.json`; do not copy plan contents or claim exit 0 means reviewed/safe.
- Exit contract:
  - Start-event write failure occurs before spawn, starts no child, and returns 125.
  - Spawn failure emits one `command_spawn_failed` event when possible and returns 127 for not found or 126 for permission/other launch failure; if that event cannot be written, return 125.
  - Ordinary child exits 0-255 are returned unchanged and stored as `exit_code` with `signal: null`.
  - On POSIX signal termination, store `exit_code: null` plus the positive signal number and return `128 + signal`.
  - On Windows interruption/termination, store the observed nonnegative process return code and `signal: null`; tests assert the platform-observed wrapper status.
  - Plan-artifact hashing/evidence construction failure after child success returns 125 and leaves the start event reducible as incomplete. It is not attempted after child failure.
  - Terminal-event construction or append failure overrides child success with 125. If the child already failed, preserve the child/signal wrapper status, print the journal failure to stderr, and leave the durable start event reducible as incomplete.
  - Parent interruption forwards SIGINT/SIGTERM to a child process group where supported, waits/reaps it, and emits exactly one `command_completed`, `command_interrupted`, or `command_spawn_failed` terminal event when persistence succeeds.
- Other CLI contract:
  - `start`: invalid arguments return 2; path/lock/write/fsync failure returns 125 without printing an ID; success durably appends `episode_started`, fsyncs, prints the ID, and returns 0.
  - `reflect`: invalid arguments return 2; invalid/torn runtime schema returns 1 without replacing reports; lock, construction, temporary-write, fsync, or replace failure returns 125 and appends no `reflection_completed`. It writes all reports to generation-tagged temporary files, fsyncs them, replaces reports in fixed order, then appends `reflection_completed` with the same `report_generation_id`. A failed partial replacement is stale and `verify` rejects it; rerunning `reflect` replaces the complete generation.
  - `verify`: invalid arguments return 2; schema, identity, terminal-event, generation, nonempty-report, or report-reference mismatch returns 1; internal read/lock failure returns 125; success returns 0 and writes nothing.
- Acceptance Criteria:
  1. [ ] A fake host `just` proves immutable argv, repository cwd, one child process, exact ordinary exit codes including several nonzero values, and visible episode artifacts.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.RunnerTests.test_host_recipe_dispatch tests.test_update_session.RunnerTests.test_exit_code_parity`
     - Pass: tests exit 0; wrapper and child exit codes match exactly.
     - Fail: any rewritten exit code or second process blocks V2.
  2. [ ] Forbidden verbs, extra arguments, arbitrary strings, and invalid episodes spawn zero child processes.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.RunnerTests.test_forbidden_inputs_spawn_nothing`
     - Pass: test exits 0 and fake process counter remains zero.
     - Fail: treat as a command-execution boundary defect.
  3. [ ] Recipe-specific mutation warnings are emitted and recorded before spawn; plan records ordered private-migration plus plan-artifact boundaries and hashes without plan contents.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.RunnerTests.test_mutation_declarations tests.test_update_session.RunnerTests.test_plan_artifact_identity`
     - Pass: tests exit 0; update, validate, and plan declarations match their recipes; plan report says exit 0 is not approval.
     - Fail: no real recipe may be observed until its boundary is accurate.
  4. [ ] A table-driven fixture covers ordinary exits 0, 1, 125, 126, 127, 128, and 255; POSIX signals; Windows termination; missing/denied spawn; start-write, evidence/hash, terminal-construction, and terminal-append failures; parent interruption; and child reaping.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.RunnerTests.test_exit_status_truth_table tests.test_update_session.RunnerTests.test_signal_and_journal_failure_precedence`
     - Pass: tests exit 0; each row matches the stored fields, terminal-event count, shell status, and precedence above, and no child remains running.
     - Fail: preserve fixture artifacts and repair phase handling.

### Wave 2 - Validation Gate

**V2: Validate wave 2** [medium] -- validation-lead
- Blocked by: T2
- Checks:
  1. Run all T2 acceptance commands.
  2. `scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py` exits 0.
  3. `scripts/host-python.sh -m unittest tests.test_update_session` exits 0.
  4. Run the CLI against a temporary fake `just` from the host entry point and confirm there is no Docker invocation by the journal itself.
- On failure: add a focused Wave 2 fix task, leave V2 unchecked, and rerun the complete gate.

### Wave 3

**T3: Add deterministic reflection and operator policy** [medium] -- python
- Blocked by: V2
- Description: Generate `summary.json`, `failures.md`, and `commands.md` from events. Runtime `failure_code` is the classification; an unmatched incomplete start derives `interrupted-unknown` without altering events. Recommendations use the exact mapping in the report contract and reference event IDs. Unknown/incomplete causes remain unknown. Update policy documentation with host usage, sensitivity, purge, and limitations.
- Files: `scripts/host-python.sh`, `scripts/update-session.py`, `tests/test_update_session.py`, `docs/service-update-policy.md`
- Mutation boundary: generated reports stay in the episode; reflection never edits tracked files.
- Alternative: unrestricted model-written reflection. Rejected because it is not deterministic or safely testable.
- Trend note: the MVP favors deterministic local reduction. Centralized or model-assisted synthesis fits only after the local schema and redaction contract are proven across repeated episodes.
- Report contract:
  - `summary.json` is UTF-8 JSON with sorted keys and one final newline. Required keys are `schema_version` (`1`), `episode_id`, `report_generation_id`, `generated_at`, `episode_status` (`passed|failed|incomplete`), `first_failure_event_id` (string or null), `command_event_ids` (ordered string array), `failure_event_ids` (ordered string array), `classifications` (ordered objects containing exactly `event_id` and `failure_code`), and `recommendations` (ordered objects containing exactly `event_ids` and `kind`). No additional keys are allowed.
  - Each Markdown report is UTF-8 with LF endings and starts with exactly one metadata line: `<!-- update-run-journal:{"episode_id":"<id>","event_ids":["<event-id>"],"report_generation_id":"<id>","report_type":"failures|commands","schema_version":1} -->`. Metadata JSON uses sorted keys and compact separators.
  - Markdown uses this literal grammar: headings end with LF; every field line is `- <field>: <compact JSON value>` using JSON `null`, strings, integers, and arrays with sorted object keys and compact separators. No free-form text or additional fields are allowed.
  - `failures.md` then has `# Failures`; failed/interrupted/spawn-failed terminal events and unmatched command starts appear in sequence order as `## <sequence> <event_id>`, followed in exact order by `recipe`, `status`, `exit_code`, `signal`, `failure_code`, and `recommendation` field lines. Unmatched starts use status `incomplete`, null exit/signal, and failure code `interrupted-unknown`. A no-failure report contains only metadata, heading, and `None.`
  - `commands.md` then has `# Commands`; every terminal command event, plus an unmatched start when present, appears in sequence order as `## <sequence> <event_id>`, followed in exact order by `recipe`, `command_argv`, `status`, `exit_code`, `signal`, `failure_code`, and `mutation_boundaries` field lines.
  - Classification/recommendation mapping is exact: `spawn-not-found` and `spawn-denied` -> `preflight`; `plan-artifact-missing` and `journal-write-failed` -> `workflow-guard`; `command-failed`, `command-interrupted`, and `interrupted-unknown` -> `no-action`. Emit exactly one recommendation object per failure event, never group events; order classifications and recommendations by event sequence. The Markdown `recommendation` field is the compact JSON string for that event's mapped kind. `first_failure_event_id` is the lowest-sequence ID in `failure_event_ids`, or null when the array is empty. `episode_status` is `incomplete` when any start lacks a terminal event, otherwise `failed` when any terminal event failed, otherwise `passed`.
  - Markdown `event_ids` must exactly equal the section IDs in order. `summary.json` arrays must exactly equal matching terminal events plus unmatched starts. The authoritative generation is the highest-sequence successful `reflection_completed` event. Older successful generations remain historical events; current report files must match only the authoritative generation. A partial rerun with no completion event is rejected because its files do not match that event; the next successful rerun becomes authoritative. `verify` parses metadata/sections, enforces grammar/mapping/status precedence, rejects unknown fields, stale/mixed generations, missing/extra/reordered references, opaque output, malformed JSON/Markdown, and writes nothing.
- Acceptance Criteria:
  1. [ ] Known fixtures map to stable failure codes and event-linked recommendations; unknown fixtures do not guess.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.ReflectionTests.test_known_taxonomy tests.test_update_session.ReflectionTests.test_unknown_does_not_guess`
     - Pass: tests exit 0; every recommendation references an event ID.
     - Fail: unreferenced or inferred causes block V3.
  2. [ ] Table-driven start, reflect, and verify fixtures cover invalid arguments, schema/torn input, lock/write/fsync/construction failures, each report replacement point, stale generations, rerun recovery, and shell statuses.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.ReflectionTests.test_failure_episode_contract tests.test_update_session.ReflectionTests.test_start_reflect_verify_truth_table`
     - Pass: tests exit 0; partial reports never validate, rerun creates one coherent generation, and all four artifacts are nonempty, schema-valid, episode-bound, and deterministically linked.
     - Fail: missing provenance, artifact, or status honesty blocks completion.
  3. [ ] Reports contain no seeded sensitive values or child output while retaining safe argv identity, exit/signal status, failure code, sequence, and evidence paths.
     - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.ReflectionTests.test_reports_are_safe_and_useful`
     - Pass: test exits 0; redaction is non-vacuous.
     - Fail: any leak or empty-evidence shortcut blocks completion.
  4. [ ] Documentation states that episodes are sensitive, Windows ACL confidentiality is not guaranteed, plan success is not approval, and opaque child output is not persisted.
     - Verify: `grep -F "sensitive local operational data" docs/service-update-policy.md && grep -F "Windows ACLs do not guarantee confidentiality" docs/service-update-policy.md && grep -F "does not mean the plan is reviewed" docs/service-update-policy.md && grep -F "does not persist command output" docs/service-update-policy.md`
     - Pass: all four independent checks pass.
     - Fail: correct documentation before V3.
  5. [ ] Fresh-setup documentation from T1 still declares Git Bash and CPython 3.11+, gives Windows and platform-neutral setup paths, and explains that only the journal helper runs on host Python while infrastructure tooling remains containerized.
     - Verify: `grep -F "CPython 3.11 or newer" README.md && grep -F "Git Bash" README.md && grep -F "Python.Python.3.13" README.md && grep -F "Python.org" README.md && grep -F "platform package manager" README.md && grep -F "scripts/host-python.sh" README.md && grep -F "journal helper is the only host Python workflow; infrastructure tooling remains containerized" README.md`
     - Pass: all seven independent checks pass.
     - Fail: correct documentation before V3.

### Wave 3 - Validation Gate

**V3: Validate wave 3** [medium] -- validation-lead
- Blocked by: T3
- Checks:
  1. Run all T3 acceptance commands.
  2. `scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py` exits 0.
  3. `scripts/host-python.sh -m unittest tests.test_update_session` exits 0.
  4. Execute the fake-`just` end-to-end episode command defined in Success Criteria 1 and verify all four artifacts automatically.
- On failure: add a focused Wave 3 fix task, leave V3 unchecked, and rerun the complete gate.

## Dependency Graph

```text
Wave 1: T1 -> V1
Wave 2: V1 -> T2 -> V2
Wave 3: V2 -> T3 -> V3
Final: V3 -> F1 -> F2 -> F3 -> F4 -> F5
```

## Success Criteria

1. [ ] A host-side fake-`just` episode observes update, preserves the operator boundary, then observes validate only when invoked separately, and produces all four sanitized artifacts.
   - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.EndToEndTests.test_explicit_multi_invocation_episode`
   - Pass: test exits 0; both invocations share the explicit episode ID, have independent sequence entries, preserve ordinary exit status, and reflection creates all four artifacts.
2. [ ] Failure reflection runs even when the observed child exits nonzero.
   - Verify: `scripts/host-python.sh -m unittest tests.test_update_session.EndToEndTests.test_failure_can_always_be_reflected tests.test_update_session.EndToEndTests.test_child_failure_precedes_reflection_failure`
   - Pass: tests exit 0; reflection runs after a wrapper failure, and simultaneous child/reflection failure reports the original child exit code.
3. [ ] The exact safe real entry point wraps repository validation from the host without nested Docker.
   - Verify: `bash -uo pipefail -c 'episode_id="$(scripts/host-python.sh scripts/update-session.py start)" || exit $?; run_rc=0; reflect_rc=0; artifact_rc=0; scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" validate || run_rc=$?; scripts/host-python.sh scripts/update-session.py reflect --episode "$episode_id" || reflect_rc=$?; scripts/host-python.sh scripts/update-session.py verify --episode "$episode_id" || artifact_rc=$?; for artifact in events.jsonl summary.json failures.md commands.md; do test -s ".tmp/update-runs/$episode_id/$artifact" || artifact_rc=1; done; if (( run_rc != 0 )); then exit "$run_rc"; fi; if (( reflect_rc != 0 )); then exit "$reflect_rc"; fi; exit "$artifact_rc"'`
   - Pass: exits 0 only when `just validate`, reflection, and all four artifact existence checks pass; a validation failure takes precedence over later reflection/artifact failures.
4. [ ] Task-specific code and repository diffs remain valid before the one wrapped repo-wide validation run.
   - Verify: `git diff --check && scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py && scripts/host-python.sh -m unittest tests.test_update_session`
   - Pass: exits 0 with no errors or warnings.

## Validation Contract

`/do-it` must satisfy this contract before reporting completion or archiving.

### Automation completeness

- Required: yes.
- All implementation and validation steps are runnable through the commands in this plan.
- Unit and E2E fixtures require no credentials, Docker, network, Proxmox, or live services.
- The exact real workflow check uses existing ignored `values/` only through unchanged `just validate`; the journal does not inspect or serialize credential values.

### Required automated validation

1. Run every task acceptance command and each wave gate.
2. Run the exact host wrapper validation from Success Criteria 3.
3. Run `git diff --check && scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py && scripts/host-python.sh -m unittest tests.test_update_session`, then run the one exact wrapped `just validate` command from Success Criteria 3.
4. Pass signals: every command exits 0, no errors or warnings remain, no seeded secret appears in test artifacts, and wrapper exit codes match child exit codes.
5. Failure action: leave the affected task/gate unchecked, record the command and non-secret evidence, add a focused fix task, and rerun the affected gate plus repo-wide validation.

### Manual validation

- Required: no.
- Justification: automated validation exercises the host boundary, fake command dispatch, failure reflection, redaction, and the real `just validate` entry point. No live apply or subjective UI decision exists.
- Steps: None.

### Deployment validation

- Required: no.
- Procedure: None. The MVP does not deploy or recover services.

### Final gate commands

- F1: `git diff --check && scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py && scripts/host-python.sh -m unittest tests.test_update_session`
- F2: `bash -uo pipefail -c 'episode_id="$(scripts/host-python.sh scripts/update-session.py start)" || exit $?; run_rc=0; reflect_rc=0; artifact_rc=0; scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" validate || run_rc=$?; scripts/host-python.sh scripts/update-session.py reflect --episode "$episode_id" || reflect_rc=$?; scripts/host-python.sh scripts/update-session.py verify --episode "$episode_id" || artifact_rc=$?; for artifact in events.jsonl summary.json failures.md commands.md; do test -s ".tmp/update-runs/$episode_id/$artifact" || artifact_rc=1; done; if (( run_rc != 0 )); then exit "$run_rc"; fi; if (( reflect_rc != 0 )); then exit "$reflect_rc"; fi; exit "$artifact_rc"'`
- F3: record `manual validation not required - automated evidence sufficient` in Execution Status.
- F4: record `deployment not required - no live mutation in MVP` in Execution Status.
- F5 preflight: `test ! -e .specs/archive/update-run-journal && test ! -L .specs/archive/update-run-journal && grep -Fx 'status: archiving' .specs/update-run-journal/plan.md && grep -Fx -- '- archive_status: ready' .specs/update-run-journal/plan.md && for gate in T1 V1 T2 V2 T3 V3 F1 F2 F3 F4; do grep -F -- "- [x] $gate:" .specs/update-run-journal/plan.md >/dev/null || exit 1; done && test "$(grep -Fxc -- '- [ ] F5: Archive preflight, move, evidence append, and final postcondition complete' .specs/update-run-journal/plan.md)" -eq 1 && scripts/host-python.sh scripts/validate-execution-evidence.py .specs/update-run-journal/review-1/execution-evidence.jsonl --through F4 && scripts/host-python.sh -c 'import pathlib,stat; root=pathlib.Path(".specs/update-run-journal"); paths=[pathlib.Path(".specs"),pathlib.Path(".specs/archive"),root,*root.joinpath("review-1").rglob("*")]; bad=[str(p) for p in paths if p.is_symlink() or (p.exists() and getattr(p.lstat(),"st_file_attributes",0) & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0))]; raise SystemExit(bool(bad))' && mkdir -p .tmp && scripts/host-python.sh -c 'import hashlib,json,pathlib; root=pathlib.Path(".specs/update-run-journal/review-1"); rows=[]; [(lambda data,p=p: rows.append({"path":p.relative_to(root).as_posix(),"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}))(p.read_bytes()) for p in sorted(x for x in root.rglob("*") if x.is_file())]; pathlib.Path(".tmp/update-run-journal-review-manifest.before").write_text(json.dumps(rows,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")' && test -s .tmp/update-run-journal-review-manifest.before`
- F5 moved postcondition: `test ! -e .specs/update-run-journal && test ! -L .specs/archive/update-run-journal && test -f .specs/archive/update-run-journal/plan.md && scripts/host-python.sh -c 'import hashlib,json,pathlib; root=pathlib.Path(".specs/archive/update-run-journal/review-1"); rows=[]; [(lambda data,p=p: rows.append({"path":p.relative_to(root).as_posix(),"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}))(p.read_bytes()) for p in sorted(x for x in root.rglob("*") if x.is_file())]; pathlib.Path(".tmp/update-run-journal-review-manifest.after").write_text(json.dumps(rows,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")' && cmp .tmp/update-run-journal-review-manifest.before .tmp/update-run-journal-review-manifest.after && grep -Fx 'status: archiving' .specs/archive/update-run-journal/plan.md && grep -Fx -- '- archive_status: moved_pending_verification' .specs/archive/update-run-journal/plan.md && grep -Fx -- '- archived_path: .specs/archive/update-run-journal/plan.md' .specs/archive/update-run-journal/plan.md && test "$(grep -Fxc -- '- [ ] F5: Archive preflight, move, evidence append, and final postcondition complete' .specs/archive/update-run-journal/plan.md)" -eq 1`
- F5 final postcondition: `test ! -e .specs/update-run-journal && grep -Fx 'status: completed' .specs/archive/update-run-journal/plan.md && grep -Eq '^completed: [0-9]{4}-[0-9]{2}-[0-9]{2}$' .specs/archive/update-run-journal/plan.md && grep -Fx -- '- archive_status: archived' .specs/archive/update-run-journal/plan.md && test "$(grep -Fxc -- '- [x] F5: Archive preflight, move, evidence append, and final postcondition complete' .specs/archive/update-run-journal/plan.md)" -eq 1 && scripts/host-python.sh scripts/validate-execution-evidence.py .specs/archive/update-run-journal/review-1/execution-evidence.jsonl --through F5 --require-archived`

### Archive rule

After F1-F4 pass, set frontmatter `status: archiving`, leave `completed:` blank, set Execution Status `archive_status: ready`, leave F5 unchecked, and run F5 preflight. Then move the plan and all sibling review artifacts:

```bash
mkdir -p .specs/archive
mv .specs/update-run-journal .specs/archive/update-run-journal
```

At the archived path, set `archive_status: moved_pending_verification` and `archived_path: .specs/archive/update-run-journal/plan.md`, leaving F5 and frontmatter pending, then run the moved postcondition. If it passes, append the sequence-11 F5 passed record to the archived `execution-evidence.jsonl`, mark F5 checked with that evidence, set frontmatter `status: completed` and the UTC `completed` date, and set `archive_status: archived`. Run the final postcondition. If any post-move step fails, keep the directory archived, revert any premature F5/completed markers to pending, retain `moved_pending_verification`, and set `blocker: archive postcondition failed - <failed command>` plus `next_command: <exact failed moved/final postcondition command>`. Resume from the archived path and never move it back automatically.

## Telemetry & Evidence Contract

For T1-F4, append one completed record to `.specs/update-run-journal/review-1/execution-evidence.jsonl` immediately after verification and before checking the ledger item. F5 is the two-phase exception: append its unique passed record at the archived path after the moved postcondition, then complete the plan markers and final postcondition before checking F5. Implementation evidence must include:

```json
{"episode_id":"update-run-journal","sequence":1,"phase_id":"wave-1|wave-2|wave-3|final-gates","task_id":"T1|V1|T2|V2|T3|V3|F1|F2|F3|F4|F5","validation_command":"exact command","status":"passed","archive_status":"not_ready|ready|archived","started_at":"ISO-8601 UTC","completed_at":"ISO-8601 UTC","evidence":"non-secret artifact path or bounded summary"}
```

Execution-evidence records require every key shown above. `sequence` is the unique integer 1-11 in dependency order `T1,V1,T2,V2,T3,V3,F1,F2,F3,F4,F5`; the F5 record's `validation_command` is the moved postcondition, while the checked F5 ledger item additionally proves the final postcondition. `episode_id` is exactly `update-run-journal`; `status` is `passed`; timestamps are nonempty UTC strings with `completed_at >= started_at`; `validation_command` and `evidence` are nonempty sanitized strings. Exact phase mapping is T1/V1 -> `wave-1`, T2/V2 -> `wave-2`, T3/V3 -> `wave-3`, and F1-F5 -> `final-gates`. T1-F4 records require `archive_status: not_ready`; F5 is appended only after the move with `archive_status: archived`.

Runtime schema version 1 is separate:

| Field | Type and allowed values | Required/nullability |
|-------|-------------------------|----------------------|
| `schema_version` | integer `1` | required, never null |
| `episode_id` | string matching `YYYYMMDDTHHMMSSZ-[0-9a-f]{8}` | required, never null |
| `event_id` | `<episode_id>-<sequence padded to 6 digits>` | required, never null |
| `sequence` | positive integer, contiguous and strictly increasing | required, never null |
| `event_type` | `episode_started`, `command_started`, `command_completed`, `command_interrupted`, `command_spawn_failed`, or `reflection_completed` | required, never null |
| `command_id` | generated non-secret string | required for command events; null otherwise |
| `recipe` | `update`, `validate`, `plan` | required for command events; null otherwise |
| `command_argv` | exact allowlisted string array | required for command events; empty otherwise |
| `mutation_boundaries` | ordered unique array from `episode_files`, `tracked_or_private_pins`, `private_artifacts`, `private_values_migration`, `root_plan_artifacts`, `tooling_workdirs`, `generated_python_cache`, `docker_runtime_cache` | required for command events; empty otherwise |
| `status` | `started`, `running`, `passed`, or `failed` | `started` for episode, `running` for command start, `passed|failed` for terminal/reflection |
| `started_at` | nonempty ISO-8601 UTC string | required, never null |
| `completed_at` | ISO-8601 UTC string | null only for `command_started`; required otherwise and not earlier than `started_at` |
| `exit_code` | integer 0-255 | required only for `command_completed`; null otherwise |
| `signal` | positive integer | required only for POSIX `command_interrupted`; null otherwise |
| `failure_code` | `command-failed`, `command-interrupted`, `spawn-not-found`, `spawn-denied`, `plan-artifact-missing`, `journal-write-failed`, or null | required non-null for failed terminal events; null for passed/start events |
| `evidence_paths` | array of relative regular-file paths below the episode | required; may be empty |
| `report_generation_id` | generated non-secret string | required only for `reflection_completed`; null otherwise |

Boundary declarations before spawn: `update` uses episode files, pins, private artifacts, tooling workdirs, and Docker runtime/cache; `validate` uses episode files, private migration, tooling workdirs, Python cache, and Docker runtime/cache; `plan` uses episode files, private migration, root plan artifacts, tooling workdirs, and Docker runtime/cache.

Runtime invariants: one `episode_started` at sequence 1; each `command_started` has zero or one later terminal event with the same `command_id`; zero is a valid interrupted/incomplete history reduced as `interrupted-unknown`; no other event uses that `command_id`; `command_completed` status is `passed` only for exit 0 and `failed` otherwise; `reflection_completed` references a complete report generation whose files all carry the same episode and generation IDs. No stdout/stderr content field exists in durable events or reports.

Evidence rules:

- Persist `command_started` before spawn; persist completion in `finally` when available.
- Persist only allowlisted fields. Sanitize exceptions before writing; never add opaque child stdout/stderr to events or reports.
- Never persist environment contents or raw private files.
- Never follow episode/evidence symlinks or paths outside the canonical root.
- Reflection recommendations reference event IDs and never change workflow state.
- Plan exit 0 means only that `just plan` exited 0. It does not mean the plan is reviewed, safe, current for apply, or free of destructive drift.
- No runtime journal entry counts as repository validation evidence without the underlying validation command passing.

## Execution Checklist

This checklist is the durable resume ledger. For T1-F4, `/do-it` appends the passed evidence record, marks the item `[x]`, and only then starts a dependent item. F5 follows the explicit two-phase archive rule and is checked only after its final postcondition. Checked means verified complete; every other state remains unchecked.

### Wave 1

- [x] T1: Implement host runtime, journal foundation, and evidence validator
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 1; 12 focused tests and README prerequisite checks passed
- [x] V1: Validate wave 1
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 2; full 12-test suite, syntax, host runtime, JSON parsing, and secret scan passed

### Wave 2

- [x] T2: Implement host-side single-recipe observation
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 3; 7 focused runner tests passed
- [x] V2: Validate wave 2
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 4; 19 tests, syntax, fake host entry point, and no journal Docker argv passed

### Wave 3

- [x] T3: Add deterministic reflection and operator policy
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 5; reflection, transaction, actual hostile child-output, and documentation checks passed
- [x] V3: Validate wave 3
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 6; all acceptance checks, 39-test suite, syntax, and explicit multi-invocation E2E passed

### Final Gates

- [x] F1: Task-specific syntax, tests, and diff checks pass
  - Verify: `git diff --check && scripts/host-python.sh -m py_compile scripts/update-session.py scripts/validate-execution-evidence.py tests/test_update_session.py && scripts/host-python.sh -m unittest tests.test_update_session`
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 7; diff, syntax, and 39-test suite passed
- [x] F2: Exact wrapped repo-wide validation and reflection pass
  - Verify: `bash -uo pipefail -c 'episode_id="$(scripts/host-python.sh scripts/update-session.py start)" || exit $?; run_rc=0; reflect_rc=0; artifact_rc=0; scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" validate || run_rc=$?; scripts/host-python.sh scripts/update-session.py reflect --episode "$episode_id" || reflect_rc=$?; scripts/host-python.sh scripts/update-session.py verify --episode "$episode_id" || artifact_rc=$?; for artifact in events.jsonl summary.json failures.md commands.md; do test -s ".tmp/update-runs/$episode_id/$artifact" || artifact_rc=1; done; if (( run_rc != 0 )); then exit "$run_rc"; fi; if (( reflect_rc != 0 )); then exit "$reflect_rc"; fi; exit "$artifact_rc"'`
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 8; exact wrapped validation passed after cross-platform test repair, with 321 container tests and verified reports
- [x] F3: Manual validation is not required
  - Verify: record automated-evidence justification in Execution Status
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 9; automated evidence covers the non-live, non-subjective workflow
- [x] F4: Deployment validation is not required
  - Verify: record no-live-mutation justification in Execution Status
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 10; local tooling MVP performs no apply or live infrastructure mutation
- [x] F5: Archive preflight, move, evidence append, and final postcondition complete
  - Verify: run F5 preflight; move; set moved-pending status; run moved postcondition; append or reuse the unique sequence-11 F5 evidence record; set completed/archive markers; run final postcondition; only then check F5
  - Status: completed
  - Evidence: execution-evidence.jsonl sequence 11; preflight, manifest-preserving move, and moved postcondition passed

## Execution Status

- status: completed
- current_wave: final-gates
- current_task: F5
- archive_status: archived
- archived_path: .specs/archive/update-run-journal/plan.md
- baseline_path: .tmp/update-run-journal-implementation-baselines/20260714T210122Z-1681
- writer: single executor for plan-owned files
- manual_validation: not required - no live or subjective operation
- deployment_validation: not required - MVP does not apply infrastructure
- evidence: T1-F4 passed with execution-evidence.jsonl sequences 1-10; exact F2 command is recorded literally and the hidden evidence audit blockers are resolved
- blocker: --
- next_command: none - execution and archive complete

## Workflow Eval Record

- episode_id: update-run-journal
- execution_outcome: completed-and-archived
- panel_quality_label: substituted-specialists-actionable
- friction_triggers: validation failure before repair; repeated contract-audit repairs; requested hidden-panel agents unavailable
- repaired_failures: Windows lock-release access denial; cross-platform global os.name test pollution; reflection transaction and schema gaps; hostile child-output test gap
- consistency_check: execution ledger T1-F4 validated; checklist and Execution Status reconciled; exact F2 command recorded
- archive_status: archived
- panel_summary: evidence audit blockers resolved; friction review passed; regression review identified a non-blocking future fake-shell sequencing test gap because the exact real F2 sequence passed
- backlog: repo validation reports unrelated TFLint unused-variable and optional-host-pattern warnings outside the task-listed files; just validate exits 0

## Handoff Notes

- Re-read `git status` before every wave. Preserve extensive existing public/private changes and unrelated untracked files.
- Before T1 edits, capture the Automation Plan baseline and declare a single writer for the five plan-owned files. Rollback may restore whole public documentation files only from that same-session baseline while the single-writer boundary remains true; otherwise stop and require a scoped manual merge.
- `.tmp/` is already ignored. Do not add another runtime-data root.
- Do not add or change a public Just recipe. The journal is opt-in and invokes existing recipes unchanged.
- Host Python implementation must use only the standard library so it does not require the tooling container.
- Tests use a fake `just` and temporary directories. They must not call network, Docker, Proxmox, live services, update, or plan.
- The only real wrapped command required for final validation is `validate`.
- Existing release holds and custom-pin outcomes are normal results, not failures.
- Existing `apply-infra.sh`, plan metadata checks, backup policy, one-service canary rule, direct health checks, and incident recovery remain authoritative.
- Review artifacts, including `review-1/synthesis.md`, are inputs already produced by `/review-it`, not implementation tasks. F5 inventories every review artifact before the move and requires the identical manifest afterward.
- Any future live observation or verified recovery plan must include current backup evidence, restore action, exact one-service target, direct endpoint/state gate, rollback boundary, and the rule that the first failed live mutation blocks every later wave until recovery passes.

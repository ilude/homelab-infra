---
reviewer: reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect -- the planned runtime side effects violate the stated artifact boundary and are not safely verified"
  confidence: high
  evidence: "The constraints require runtime artifacts under `.tmp/update-runs/`, but T2 explicitly permits `--through plan` to create the same local `tfplan` artifacts as `just plan`. `scripts/plan-infra.sh` runs `rm -f tfplan tfplan.meta.json ./*.tfplan ./*.tfplan.meta.json` and writes a repository-root `tfplan` and `tfplan.meta.json`; the plan neither scopes these paths to the episode nor tests preservation of pre-existing plan files."
  required_fix: "Define the authoritative plan-artifact location and preservation/cleanup policy. If the real `just plan` must run unchanged, explicitly document the repository-root side effect as an exception and add a test/smoke assertion that the wrapper reports it and does not delete unrelated pre-existing artifacts. Otherwise add an isolated plan mode that does not invoke the destructive cleanup or writes only under the episode root."
- severity: high
  category: "substantive defect -- recovery state and command provenance are contradictory and cannot be executed deterministically"
  confidence: high
  evidence: "T2 says the runner must refuse arbitrary shell strings, while the automation example accepts `record ... --command \"<exact successful command>\"`; the global rule requires redaction, which means the stored command may no longer be exact. The incident acceptance says later phases are blocked until a recovery record is added, but no resume/retry command or state transition is specified, and there is no validation of recovery evidence against the original endpoint/state."
  required_fix: "Specify a structured argv-only recovery record (or explicitly define safe parsing/redacted-vs-exact fields), its validation rules, and the state transition after recording. Add an executable resume/report test proving first failure remains, recovery is recorded without leakage, and blocked phases are either intentionally never resumed or resume only after the stated gates."
- severity: high
  category: "substantive defect -- the requested end-to-end journal outcome is not actually a required test"
  confidence: high
  evidence: "The success criterion requires a real `run --through validate` followed by `reflect --episode latest`, with `events.jsonl`, `summary.json`, `failures.md`, and `commands.md` and both public phases recorded. The required validation contract only runs `run --through validate` and does not invoke `reflect`; V2 smoke runs only `run --through update`; V3 inspects fixtures. No acceptance criterion tests the `latest` selector, the real update+validate sequence, or the resulting four artifacts."
  required_fix: "Add a named acceptance/end-to-end test and validation command that executes the exact success workflow including `reflect --episode latest`, verifies deterministic episode resolution and all four artifacts, confirms both `just update` and `just validate` events, and checks exit-code parity. Make it a prerequisite of F1/archive."
- severity: medium
  category: "process defect -- the durable checklist and archive gate do not provide executable completion semantics"
  confidence: high
  evidence: "The checklist requires F1 through F5 in sequence, but F1-F4 are labels with no commands or pass criteria of their own; F5 is only 'Archive preflight complete'. The archive rule names required gates but does not define an archive command, the artifact/status update that constitutes archiving, or how `archive_status` changes from `not_ready` to `ready`/`archived`. A brand-new `/do-it` session cannot complete or verify the final ledger from the plan alone."
  required_fix: "Give F1-F5 explicit commands, evidence paths, and pass criteria. Define the exact archive operation and the required plan frontmatter/checklist state transition, including the rule that any failed/skipped gate leaves `archive_status` not ready. Reconcile the telemetry schema with the checklist so every required gate has one unambiguous executable record."
- severity: medium
  category: "substantive defect -- episode lifecycle and command validity are underspecified"
  confidence: high
  evidence: "The automation table presents `start --through validate` followed by a separate `run --through validate`, but T2 says `run` owns the episode ID and the success flow only invokes `run`. It is unspecified whether `start` is required, whether `run` resumes the started episode, and what `--root .tmp/update-session-smoke` means; the required runtime root is `.tmp/update-runs/<episode_id>`, while the smoke command supplies a different path. `reflect --episode latest` likewise has no deterministic selection/concurrency rule."
  required_fix: "Choose and document one lifecycle (single `run`, or start/resume with an explicit episode identifier), define every CLI option and its path semantics, and add help/invalid-argument tests. Specify deterministic `latest` behavior or require the printed episode ID/path in subsequent commands, especially when concurrent episodes exist."

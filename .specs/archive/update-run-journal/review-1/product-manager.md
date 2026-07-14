# Product Manager Review

## Findings

### 1. Substantive defect - the MVP does not preserve the exact existing update workflow
- **Severity:** High. The proposed `run --through validate` changes the operator's entry point and sequencing while claiming exact workflow preservation.
- **Evidence:** The existing documented workflow is `just update`, review the diff, `just validate`, `just plan`, then approved `just apply` (`justfile`, `docs/service-update-policy.md`). The plan instead runs `update` and `validate` as phases, while `plan` is optional and `apply` is deferred. The success criterion validates `run --through validate`, not the complete existing workflow or an observational wrapper around each existing command.
- **Required fix:** Make the MVP an opt-in journal wrapper for one existing command invocation, or explicitly define and test a documented equivalent workflow that includes the review and plan boundaries. Do not present a new phase runner as preserving the existing workflow. Keep `just update`, `just validate`, and `just plan` unchanged and verify each original entry point independently.
- **Confidence:** High - verified against the current `justfile` and service-update policy.

### 2. Substantive defect - `just update` is incorrectly treated as non-destructive
- **Severity:** High. The wrapper can change pinned versions and private values before the operator reviews them, so the MVP has a real local mutation boundary and can disrupt extensive uncommitted work.
- **Evidence:** `just update` runs `scripts/update.py`, whose purpose is to update pinned tool and service versions. The plan calls the update/validate/plan phases "non-destructive" and only flags plan artifacts as mutation, despite allowing `run --through update` and a smoke test that invokes the real command.
- **Required fix:** Either remove `update` from the MVP and journal only already-existing commands, or record and test update as a tracked/private-file mutation with a preflight refusal when the working tree is not clean or an explicit opt-in is absent. The smaller reliable choice is to defer orchestration and ship observation first.
- **Confidence:** High - verified from `justfile` and `scripts/update.py`.

### 3. Low-value/theater - the schema and reflection system is too large for the stated user value
- **Severity:** Medium. JSONL events, per-episode locking, atomic summaries, a required multi-field schema, stable taxonomy, event-linked recommendations, three reports, and a separate `record` protocol create substantial correctness surface before proving that durable command history solves the problem.
- **Evidence:** T1-T3 require multiple artifacts (`events.jsonl`, `summary.json`, `failures.md`, `commands.md`), concurrency behavior, many telemetry fields, bounded taxonomy, and evidence-backed recommendations. The stated user question is primarily what command ran, its exit code, the first failure, and the recovery command.
- **Required fix:** Reduce MVP to one Python wrapper that records one sanitized JSON summary plus one bounded log per invocation, preserving argv, exit code, first failure, and artifact path. Defer JSONL/event schemas, lock handling, taxonomy, reflection recommendations, and Markdown report generation until repeated usage demonstrates a need.
- **Confidence:** High - based on the plan's task and acceptance-criteria count compared with its stated objective.

### 4. Process defect - external recovery is recorded, not verified
- **Severity:** High. The plan can report successful recovery without establishing that the supplied command ran or that the evidence belongs to the episode.
- **Evidence:** `record --phase recovery --status passed --command ... --evidence ...` records an explicitly supplied result and does not execute it. T2 then says later phases are blocked until an explicit recovery record is added, and T3 reports exact successful recovery commands. This allows an unverified assertion to clear an incident hold.
- **Required fix:** Do not let `record` change workflow state or label recovery as passed. Store it as operator notes with `unverified` status, or defer recovery state entirely. A future verified recovery feature must execute a narrowly allowlisted existing check and validate its result against the original endpoint/state gate.
- **Confidence:** High - directly stated in the Automation Plan and T2 acceptance criteria.

### 5. Substantive defect - deferring the goal's actionable output undermines the MVP
- **Severity:** Medium. The plan's motivation is to prevent repeated rediscovery and support process improvement, but the smallest useful operator-facing journal is spread across later waves and the most important recovery/application boundaries are excluded.
- **Evidence:** T1 only creates storage and redaction; T2 adds orchestration; T3 finally creates the reports and recommendations. Automatic apply and rollback are correctly out of scope, but the plan also defers cleanup, documentation of usable output until Wave 3, and any verified recovery path. A partially implemented journal provides little durable value before all three waves.
- **Required fix:** Re-scope MVP to one end-to-end command wrapper that immediately emits a readable, sanitized summary and log, with no recommendations or recovery state. Move taxonomy, reflection, recovery attachment, multi-phase orchestration, and extra reports to deferrals. This yields a smaller complete product rather than a three-wave framework whose useful result arrives last.
- **Confidence:** Medium - product judgment grounded in the plan's staged acceptance criteria and stated motivation.

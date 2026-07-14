---
date: 2026-07-14
status: synthesis-complete
---

# Review: Deterministic Update Run Journal

## Review Panel
| Reviewer | Base Agent | Assigned Expert Persona | Why selected | Adversarial angle | Artifact |
|----------|------------|-------------------------|--------------|-------------------|----------|
| reviewer | reviewer | Plan completeness and automation readiness | Tests standalone `/do-it` executability | Hidden prerequisites, invalid commands, checklist gaps | `.specs/update-run-journal/review-1/reviewer.md` |
| security-reviewer | security-reviewer | Evidence and local-data safety | Journal persists command and output evidence | Secret leakage, traversal, symlinks, concurrency, permissions | `.specs/update-run-journal/review-1/security-reviewer.md` |
| product-manager | product-manager | MVP and workflow simplicity | Challenges whether orchestration is needed | Scope inflation, altered operator workflow, deferred value | `.specs/update-run-journal/review-1/product-manager.md` |
| qa-engineer | qa-engineer | Verification realism | Plan depends on failure-injection tests | Non-hermetic smoke checks, false-positive redaction, missing E2E | `.specs/update-run-journal/review-1/qa-engineer.md` |
| devops-pro | devops-pro | Infrastructure workflow and incident boundaries | Existing commands cross Docker and mutate local state | Nested Docker, stale plans, destructive drift, false recovery | `.specs/update-run-journal/review-1/devops-pro.md` |
| python-pro | python-pro | Python CLI, subprocess, and journal durability | Core implementation is a cross-platform Python runner | Locking, atomicity, argv safety, event ordering, stream capture | `.specs/update-run-journal/review-1/python-pro.md` |

`review_panel_decision`: medium-cross-cutting workflow plan; complexity 6/10; risk 5/10; six reviewers selected. Expected high-risk areas were redaction gaps, swallowed exit codes, partial JSONL writes, accidental live apply, ambiguous mutation state, and concurrent writers. The panel confirmed these areas and found an additional host/container execution-boundary defect.

## Standard Reviewer Findings
### reviewer
- The planned `--through plan` path can delete and replace repository-root plan artifacts without a complete artifact-preservation contract.
- Recovery recording, incident clearing, and resume semantics conflict.
- The required E2E workflow does not actually run reflection or verify all four artifacts.
- Final checklist/archive gates lack executable completion semantics.
- `start`, `run`, `latest`, and `--root` form an inconsistent episode lifecycle.

### security-reviewer
- The redaction claim is broader than the specified implementation can prove; hostile child output must be sanitized before every write.
- User-controlled roots, episode IDs, and evidence paths lack traversal/symlink boundaries.
- Environment non-serialization does not prevent child processes from printing inherited secrets.
- Locking, fsync, torn-tail, and reader/writer behavior are undefined.
- Ignored `.tmp/` artifacts still require explicit local-sensitivity, permission, and purge guidance.

### product-manager
- `run --through` replaces the operator-controlled review boundaries between existing public commands.
- `just update` is mutating, despite being described as non-destructive.
- The original MVP contains avoidable orchestration and lifecycle complexity.
- An operator assertion cannot verify or clear recovery.
- Useful output arrives only after all three framework-oriented waves.

## Additional Expert Findings
### qa-engineer
- `latest` is undefined and `&&` suppresses reflection for the failure episodes that matter most.
- The real update smoke is mutating, network-dependent, and non-hermetic.
- Named tests need explicit failure injection and wrapper-level exit-code assertions.
- Incident/recovery tests can pass without endpoint/state verification.
- Redaction tests can pass vacuously by dropping all useful evidence.

### devops-pro
- Plan artifacts need identity/freshness evidence if represented in the journal.
- A successful plan exit must never be summarized as approval or safety.
- Launching the wrapper through `scripts/python.sh` and then invoking public recipes creates an undefined nested-Docker boundary.
- A recorded recovery assertion must not clear incident state.
- Non-live fixtures should preserve existing stale-plan, destructive-drift, and stateful-batch holds.

### python-pro
- The lock/durability contract is insufficient for the claimed interruption guarantee.
- Phase argv, cwd, environment, and host/container executable resolution are undefined.
- Events require sequence/event identifiers and injectable time for deterministic reduction.
- Stream bounds, encoding, truncation, and cross-chunk redaction are undefined.
- Event types, nullable fields, recovery conflicts, and report reduction need a versioned schema/state machine.

## Suggested Additional Reviewers
- None before the plan is repaired. The six-person panel covers the implementation, workflow, security, and validation domains needed for this MVP.

## Bugs (must fix before execution)
1. Replace the in-container multi-phase `run --through` design with a host-side, opt-in, one-allowlisted-command wrapper. Require an explicit episode ID and preserve the operator's review boundary between `update`, `validate`, and `plan`.
2. Declare real mutation boundaries: `update` can change tracked/private pins, `validate` can migrate private values, and `plan` removes/replaces root plan artifacts. Remove the mutating real-update smoke and validate dispatch hermetically.
3. Remove `latest`, implicit resume, ambiguous `start --through`, arbitrary command strings, and recovery-as-passed assertions. Recovery notes remain explicitly unverified and cannot clear an incident.
4. Define a versioned event schema and reducer with generated episode IDs, event IDs, monotonic sequence, event types, timestamp format, exact exit/signal behavior, and incomplete/torn event handling.
5. Define host-side immutable argv, `shell=False`, repository cwd, deliberate environment inheritance, bounded hostile-output capture, pre-persistence redaction, and exact wrapper exit-code parity.
6. Enforce the runtime path boundary with generated ID validation, canonical containment checks, symlink/junction rejection, restrictive best-effort permissions, and episode-local evidence paths.
7. Add executable E2E/report validation and final-gate/archive semantics, including the required `## Execution Status` section and one-to-one checklist evidence.

## Hardening
1. Record plan artifact paths and hashes after `plan`, but never represent exit 0 as reviewed or safe; retain the existing full terminal output and public apply gate.
2. Specify lock owner metadata, contention behavior, stale-lock refusal, flush/fsync boundary, torn-tail quarantine, and deterministic report reduction by sequence.
3. Specify stdout/stderr byte limits, UTF-8 replacement behavior, truncation metadata, and chunk-boundary redaction tests.
4. Add an operator-controlled purge command or documented deletion command and classify episodes as sensitive local operational data; do not treat `.gitignore` as confidentiality.
5. Ensure redaction tests prove both removal and retained utility: safe argv shape, stable failure code, bounded output, and deterministic placeholders.

## Simpler Alternatives / Scope Reductions
1. The targeted rebuttal unanimously selected a host-side one-command observational wrapper over `run --through`. Episode continuity comes from an explicit ID, not runner-owned sequencing.
2. Keep JSONL plus deterministic reports because the conversation explicitly requires structured evidence and bounded reflection, but remove implicit lifecycle, automatic phase ordering, resume, and incident clearing.
3. Keep verified live recovery, apply orchestration, automatic rollback, backup enforcement, and source-changing recommendations deferred.

## Automation Readiness
- Agent-runnable operational steps: not ready in the original plan; `scripts/python.sh scripts/update-session.py` would run the wrapper inside Docker and recurse into Docker-backed recipes.
- Credential/auth flow clarity: incomplete; output must be treated as hostile and redacted before persistence, with no environment capture.
- Evidence and archive gates: incomplete; event identity, report generation, final checklist commands, and archive transitions require repair.
- Manual-only steps and justification: no exceptional manual validation is needed for implementation. The operator-controlled review between mutating public commands is workflow sequencing, not a manual validation gate.

## Contested or Dismissed Findings
1. Product's proposal to reduce the MVP to one JSON summary and one log was not adopted in full. The requested outcome explicitly includes structured events, summary, command/failure reports, and bounded reflection; removing them would miss the stated goal. The orchestration portion is removed instead.
2. DevOps' request to parse all plan resource identities and make destructive findings a journal-level resume blocker is downgraded to hardening. This MVP does not apply, approve, or resume deployments; existing `just plan` output and `apply-infra.sh` remain authoritative. The journal must state that exit 0 is not safety approval and may record existing metadata without becoming a second policy engine.
3. A full verified recovery state machine is deferred rather than implemented. An unverified operator note may preserve a command for later review but cannot be labeled successful, clear an incident, or authorize another phase.
4. The security finding about process-list exposure is accepted only as an argv policy: secrets must never be accepted in journal CLI argv. The wrapper cannot guarantee behavior of every existing downstream tool, so child output is treated as hostile and redacted before persistence.

## Verification Notes
1. Confirmed: `scripts/python.sh` executes `docker compose run --rm ... infra python`; invoking Docker-backed public recipes from that process creates the nested-boundary defect.
2. Confirmed: `scripts/update.py` writes managed files at multiple call sites; update is a local mutation.
3. Confirmed: `just validate` depends on `migrate-values`, and `scripts/migrate-values.py` writes private env/tfvars/inventory when migration changes exist.
4. Confirmed: `scripts/plan-infra.sh` removes `tfplan`, `tfplan.meta.json`, and matching root plan artifacts before writing a new plan.
5. Confirmed: the original plan lacks `## Execution Status`; its final checklist items have no executable evidence contract.
6. Rebuttal outcome: product-manager and devops-pro independently preferred the host-side one-command wrapper and agreed that explicit episode IDs preserve journal continuity without collapsing workflow gates.

## Reviewer Artifact Status
| Reviewer | Artifact | Status | Notes |
|----------|----------|--------|-------|
| reviewer | `.specs/update-run-journal/review-1/reviewer.md` | read | usable |
| security-reviewer | `.specs/update-run-journal/review-1/security-reviewer.md` | read | usable |
| product-manager | `.specs/update-run-journal/review-1/product-manager.md` | read | usable; alternate heading format retained actionable fields |
| qa-engineer | `.specs/update-run-journal/review-1/qa-engineer.md` | read | usable; alternate heading format retained actionable fields |
| devops-pro | `.specs/update-run-journal/review-1/devops-pro.md` | read | usable JSON artifact |
| python-pro | `.specs/update-run-journal/review-1/python-pro.md` | read | usable; alternate heading format retained actionable fields |

## Timing Notes
| Step | Duration | Notes |
|------|----------|-------|
| Initial review panel | 1m55s | 2026-07-14T18:55:08Z to 2026-07-14T18:57:03Z |
| Artifact reads | included in verification span | all six expected artifacts read; per-reviewer timing unavailable |
| Recovery calls | none | no missing or unusable artifacts |
| Rebuttal | timing unavailable | two targeted medium reviewers; no artifact recovery |
| Verification | completed by 2026-07-14T18:59:26Z | high-severity repository claims checked directly |
| Synthesis | timing unavailable | coordinator synthesis |

## Review Yield

- Raw findings: 30 (24 substantive defects, 4 process defects, 2 low-value/theater).
- Merged must-fix themes: 7.
- Merged hardening themes: 5.
- Duplicate/overlapping findings merged: 18 raw findings contributed to shared themes.
- Low-value/theater findings: 2, both used to simplify scope and strengthen non-vacuous tests.
- False positives: 0 reviewer-labeled; 2 requested expansions were downgraded or partially dismissed in synthesis.
- Applied/rejected: 12 initial bug/hardening themes applied; 2 scope expansions rejected or downgraded. Standalone repair passes applied 3 additional bug fixes and 1 hardening fix.
- Readiness change: original plan was not standalone-ready; 3 blockers remain after the two permitted repair passes.
- Per-reviewer yield: reviewer 5/5 actionable; security-reviewer 5/5 actionable; product-manager 4/5 directly accepted and 1 partially accepted; qa-engineer 5/5 actionable; devops-pro 4/5 directly accepted and 1 downgraded; python-pro 5/5 actionable.

## Panel Quality Inputs

- Task structure: changed T2 from multi-phase orchestration to a host-side one-command wrapper.
- Validation commands: removed mutating real-update smoke; added hermetic fake-`just` dispatch, host-boundary, failure, and report tests.
- Manual-gate decision: unchanged; implementation remains non-live and agent-runnable.
- Archive rules: must gain executable F1-F5 semantics and `Execution Status`.
- Automation readiness: changed from not ready due nested Docker and ambiguous lifecycle to pending repair around a host-only launcher.

## Auto-Apply Plan
- Applied fixes artifact: `.specs/update-run-journal/review-1/applied-fixes.md`
- Known-blocker fixes artifact: `not run/no prior blockers`
- Section integrity check: passed after each plan edit; no checklist item was marked complete
- Standalone-readiness result: STANDALONE READY; zero blockers in `.specs/update-run-journal/review-1/standalone-readiness.md`
- Repair passes used: initial workflow budget plus explicit user-authorized blocker completion; final check passed

## Review Artifact
Wrote full synthesis to: `.specs/update-run-journal/review-1/synthesis.md`

## Overall Verdict
**Ready to execute**

## Recommended Next Step
- Execute via `/do-it .specs/update-run-journal/plan.md`.

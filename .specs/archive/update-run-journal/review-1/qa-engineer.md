# QA Engineer Review

## Finding 1
- Category: substantive defect - high severity because the documented success workflow is not deterministically runnable
- Severity: high
- Evidence: The Success Criteria command is `scripts/python.sh scripts/update-session.py run --through validate && scripts/python.sh scripts/update-session.py reflect --episode latest`, but the plan never defines `latest` as a supported episode identifier or a resolution rule. The runner is only required to print an episode artifact path. Also, the `&&` means a failed update or validation prevents the required reflection command from running, even though failure episodes are a stated MVP outcome.
- Required fix: Define and test `latest` resolution, or use the episode ID/path emitted by `run`. Add a failure-path command sequence that always invokes `reflect` for a completed or failed episode and specify its expected exit status.
- Confidence: high

## Finding 2
- Category: substantive defect - high severity because the real smoke check can mutate local update inputs and is not hermetic
- Severity: high
- Evidence: V2 requires `run --through update --root .tmp/update-session-smoke` to invoke the real `just update`. The plan calls update non-destructive, but the existing `justfile` maps `update` to `scripts/update.py`, which checks upstream releases and can update pinned files. The smoke also depends on Docker, network/upstream responses, and ignored private values, while the validation contract treats it as required automated validation and does not define a fixture, offline mode, or clean-worktree assertion.
- Required fix: Either make the smoke use a deterministic fake `just`/command environment and separately test the exact argv, or explicitly authorize and isolate local update mutations with a disposable checkout and pinned network fixtures. Add pre/post mutation checks and document required Docker, values, and network prerequisites; do not label this path non-destructive unless verified.
- Confidence: high

## Finding 3
- Category: substantive defect - high severity because named unit tests cannot prove the required subprocess boundary behavior
- Severity: high
- Evidence: T1 tests are specified only by names and are required to use fake commands and temporary directories. `test_command_exit_code_is_preserved` and `test_atomic_event_append` do not, by their stated contracts, prove the wrapper preserves the exit code of the real `just update`/`just validate` entry points, nor that an interruption occurs after child process completion but before the event append. V2 has only a success-oriented real smoke; there is no real-command failure injection.
- Required fix: Specify test fixtures and assertions for a child that exits with several exact nonzero codes, a deterministic signal/crash injection at the post-process/pre-append boundary, and wrapper-level exit-code assertions. Add a controlled real-entry-point failure fixture (for example, a fake `just` on PATH) that verifies phase status, returned code, and durable event output without network or infrastructure.
- Confidence: high

## Finding 4
- Category: substantive defect - medium severity because the incident/resume acceptance can pass without proving recovery behavior
- Severity: medium
- Evidence: T2 only requires `test_incident_transition_event` and says later phases are blocked until an explicit recovery record is added, but no acceptance test verifies the subsequent resume path, recovery command/evidence association, original endpoint/state validation, or rejection of an unrelated recovery record. The telemetry contract specifically requires recovery plus original endpoint/state validation before future live rollout can resume, while the MVP's `record` command merely attaches a path and does not validate it.
- Required fix: Add an end-to-end failure -> incident -> blocked attempt -> valid recovery record -> resume test, plus a negative test for a missing, outside-episode, or mismatched recovery evidence path. Define which validation is possible for this non-live MVP and ensure the report distinguishes recorded recovery from verified recovery.
- Confidence: high

## Finding 5
- Category: low-value/theater - medium severity because the redaction pass condition permits a vacuous implementation
- Severity: medium
- Evidence: T1 acceptance 3 passes when seeded sensitive literals are absent, while also requiring useful failure classifications. A runner that drops all captured output, omits command arguments, or replaces the entire event with a generic placeholder can satisfy the literal-absence assertion without proving bounded evidence retention, environment non-capture, private path handling, or classification usefulness. V3's inspection is manual despite the contract declaring manual validation unnecessary, and it has no exact required fields beyond ordering/redaction.
- Required fix: Assert that non-sensitive command structure and a stable failure code remain present, sensitive values are replaced by deterministic placeholders, captured output is bounded, environment variables are absent, and evidence paths stay under the episode directory. Turn the V3 artifact checks into automated assertions and define archive evidence that records these results.
- Confidence: high

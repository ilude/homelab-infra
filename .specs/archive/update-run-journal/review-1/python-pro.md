# Adversarial review: python-pro

## Finding 1
- Category: substantive defect - high severity because the stated interruption-safety and append-only guarantees are not implementable from the current contract.
- Severity: high
- Evidence: T1 requires an append-only JSONL writer and says a per-episode lock or fail-closed behavior is sufficient, but does not define the lock protocol for Windows and Linux, lock lifetime, stale-lock handling, append atomicity, flush/fsync behavior, or recovery from a torn final line. It also claims durable events when interrupted after process completion; an interruption between `Popen` completion and the event append can lose the result.
- Required fix: Specify a cross-platform lock protocol (exclusive lock-file creation or an explicitly named library), owner metadata, stale-lock behavior, and fail-closed error handling. Specify the durability boundary (`flush` plus `fsync`, and what Windows provides), single-writer append behavior, and malformed-tail recovery policy. Define a subprocess completion journal/state marker or a `finally`/reconciliation protocol that makes the post-process/pre-event interruption state explicit rather than claiming it is durable. Add tests for lock contention, interruption at that boundary, and a torn final line.
- Confidence: high

## Finding 2
- Category: substantive defect - high severity because the phase runner can accidentally execute a different command or a shell payload while still appearing to preserve the intended workflow.
- Severity: high
- Evidence: T2 says to record exact argv and reject arbitrary shell strings, but it does not define the exact argv for `update`, `validate`, or `plan`, how `just` is located on a Windows host versus inside the Linux tooling container, the working directory, environment policy, or argument allowlisting. The automation examples use `scripts/python.sh`, which itself invokes Docker and Bash, while the project also describes a Windows operator workstation. “Existing public commands” is not an executable contract. `record --command` accepts an exact command string and its redaction/validation contract is unspecified; future reuse of that value could become command injection.
- Required fix: Make each phase an immutable argv list with an explicit executable, cwd, and controlled environment; invoke with `shell=False` and define the supported host/container entry point and path conversion rules. Reject all extra tokens and forbidden verbs before spawning, and test that zero subprocesses start on forbidden input. Treat recorded recovery commands as display-only data, store them as argv or a clearly non-executable string, and document that they are never parsed or executed. Add Windows and container invocation tests using fake executables.
- Confidence: high

## Finding 3
- Category: substantive defect - high severity because “deterministic” artifacts cannot have stable identity or reproducible ordering under the specified fields.
- Severity: high
- Evidence: T1 requires stable episode/phase identifiers and UTC timestamps, but gives no generation algorithm, collision behavior, clock source, precision, or injectable clock. T3 requires deterministic ordering, yet no event ID/sequence field is required and concurrent or resumed writes can produce ambiguous ordering. The telemetry schema does not include an event identifier, although T3 recommendations must reference event IDs.
- Required fix: Define `event_id` and a monotonic per-episode `sequence` assigned under the writer lock, plus exact ID algorithms and collision handling for `episode_id` and `phase_id`. Define timestamp format and precision, use an injected clock in tests, and state whether timestamps are evidence metadata or excluded from byte-for-byte reproducibility. Require report sorting by sequence, not filesystem or wall-clock order, and add a resume/restart test proving IDs and ordering remain unambiguous.
- Confidence: high

## Finding 4
- Category: substantive defect - medium severity because output capture can violate both evidence usefulness and the no-secret contract.
- Severity: medium
- Evidence: T1 says “bounded sanitized logs” and the contract says “redact before writing,” but neither specifies whether stdout and stderr are separate, the byte/character limit, encoding and decode-error policy, truncation markers, line handling, or redaction order. A secret split across chunks, a sensitive value in a partial UTF-8 sequence, or a very large single line can evade a naive per-chunk/per-line redactor or exhaust memory. The redaction corpus only proves seeded literals, not the streaming behavior.
- Required fix: Define byte limits per stream and total, deterministic UTF-8 decoding with replacement, explicit truncation metadata, separate stdout/stderr fields, and a streaming redaction strategy that preserves enough overlap to catch secrets split across reads (or spool only to a bounded private temporary file before redaction). Specify replacement tokens and fail closed if sanitization cannot complete. Add chunk-boundary, malformed-UTF-8, large-line, and truncation tests, including secrets spanning chunks.
- Confidence: high

## Finding 5
- Category: process defect - medium severity because the task gates and schema do not give implementers a testable contract for status and report generation.
- Severity: medium
- Evidence: T1 acceptance requires `status`, `archive_status`, and `completed_at` on a start event even though a start event is not complete; T2 introduces phase statuses, blocked phases, incident transitions, and `mutation_started` without defining whether these are event types or values in the common record. T3 requires `summary.json`, `failures.md`, and `commands.md`, while its acceptance text says “all four artifacts,” and `record`/resume semantics do not define duplicate recovery records, latest-state selection, or whether a failed command's output is authoritative. The telemetry contract also permits only `evidence_paths` under the episode but separately allows a supplied external evidence path.
- Required fix: Publish a versioned JSON schema with explicit event types, required/nullable fields per type, enums, exit-code rules for signals, and relative-path constraints. Define the state machine and reducer for start, phase completion, blocked, incident, recovery, and resume, including duplicate/conflicting records and incomplete episodes. Name the fourth artifact or correct the acceptance criterion, define whether external evidence is copied or only referenced (and reject paths outside the episode if required), and add fixture tests for interrupted, resumed, failed, and duplicate-record episodes.
- Confidence: high

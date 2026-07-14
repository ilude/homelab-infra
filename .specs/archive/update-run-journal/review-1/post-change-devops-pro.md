# Post-change DevOps review

## Findings

1. **High** | **Category:** mutation-boundary
   - **Evidence:** The plan declares `plan` as `root_plan_artifacts` only (Wave 2 recipe declarations and runtime schema), but the current public `plan` recipe depends on `migrate-values`, and `migrate-values` runs `scripts/migrate-values.py`. The plan itself also says `plan` may perform private-values migration in the Automation Plan.
   - **Required fix:** Declare and display both possible boundaries before `plan` runs: private-values migration and root plan-artifact replacement. Represent both in the event schema (for example, an ordered `mutation_boundaries` list) rather than recording only `root_plan_artifacts`; add a fake-`just` assertion for the combined declaration.
   - **Confidence:** high

2. **Medium** | **Category:** subprocess-exit-semantics
   - **Evidence:** The objective requires exact exit-code parity, while the runtime schema requires a nonnegative `exit_code` and a separate `signal` field. Python `subprocess` reports signal termination as a negative return code, but the plan does not define the wrapper's returned status for that case or test it.
   - **Required fix:** Specify the signal-to-wrapper exit-status mapping, persist the original signal separately, and add a SIGTERM/SIGKILL fixture that proves the terminal status, event fields, and reflection behavior agree. Preserve direct non-signal child exit codes unchanged.
   - **Confidence:** high

3. **Medium** | **Category:** purge-safety
   - **Evidence:** Purge validates only the episode directory as a direct non-symlink child before recursive deletion. The plan does not define handling for symlinks, junctions, or other reparse points created below that directory during the recursive delete.
   - **Required fix:** Define a no-follow purge algorithm that walks descendants with link/reparse-point detection and either rejects the purge before deletion or unlinks only the link itself. Add fixtures for nested symlink and Windows junction-like descendants proving no target outside the episode can be removed.
   - **Confidence:** medium

4. **Medium** | **Category:** archive-recovery
   - **Evidence:** F5 has a post-move repair instruction, but no concrete durable blocker format or command when the move succeeds and the later archived-plan edit or postcondition fails. The preflight checks only for `review-1/synthesis.md`, while the archive rule requires all sibling review artifacts.
   - **Required fix:** Add an explicit post-move failure procedure that records the failed command and non-secret evidence in the archived plan's Execution Status, leaves F5 unchecked, and names the exact resume command from the archived path. Make F5 preflight verify every required review artifact that must move, not only the synthesis file.
   - **Confidence:** high

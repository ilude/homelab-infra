---
date: 2026-07-14
status: resolved
---

# Standalone Readiness Blockers

All blockers below were subsequently repaired. The final standalone artifact reports `STANDALONE READY` with zero findings.

## Resolved blockers

1. Validator task ownership deadlocks Wave 1.
   - `scripts/validate-execution-evidence.py` is created in T3, but V1 and V2 compile it before T3 can start.
   - Required fix: move validator ownership to T1 and update task file counts/baseline scope, or compile it only in V3 and final gates.

2. Report formats are not machine-readable enough for deterministic verification.
   - `summary.json`, `failures.md`, and `commands.md` require generation and event references, but their exact schemas/metadata/ordering are undefined.
   - Required fix: define exact JSON and Markdown frontmatter/body contracts and verify all partial-generation states without rewriting reports.

3. Documentation validation can miss the Windows ACL warning.
   - T3 criterion 4 claims four independent checks but runs only three.
   - Required fix: add an independent exact ACL-warning check and keep V3 bound to the corrected criterion.

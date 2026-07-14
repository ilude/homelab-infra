---
date: 2026-07-14
status: applied
---

# Applied Plan Fixes

| Finding | Category | Target sections | Edit intent | Checklist impact |
|---------|----------|-----------------|-------------|------------------|
| Nested Docker and collapsed review boundaries | bug | Objective, MVP Boundary, Automation Plan, T2 | Replace `run --through` with a host-side wrapper around one allowlisted public recipe per invocation | T2 renamed; criteria replaced; remains unchecked |
| Update/validate/plan mislabeled non-destructive | bug | Constraints, Risk, Automation Plan, T2 | Declare recipe-specific tracked/private/plan-artifact mutations before execution | T2 criteria expanded; remains unchecked |
| Ambiguous start/latest/resume lifecycle | bug | Automation Plan, T1, T2, Success Criteria | Use generated episode ID plus explicit ID on every later command; remove `latest` and implicit resume | T1/T2 criteria replaced; remain unchecked |
| Unverified recovery could clear incident | bug | MVP Boundary, Deferrals, T2, Telemetry Contract | Make recovery notes unverified display-only data; never clear state or claim success | T2 criterion added; remains unchecked |
| Weak redaction and hostile output contract | bug/hardening | Constraints, T1, Telemetry Contract | Add pre-write redaction, safe argv identifiers, environment non-capture, stream bounds, utility assertions | T1 criteria expanded; remains unchecked |
| Path traversal, symlink, and local permission gaps | bug/hardening | T1, Telemetry Contract | Constrain generated IDs and episode-local paths; reject links/traversal; require restrictive best-effort permissions | T1 criteria expanded; remains unchecked |
| Undefined event identity, lock, and durability | bug/hardening | T1, Telemetry Contract | Add schema version, event ID, sequence, event types, lock protocol, fsync boundary, torn-tail policy | T1 criteria expanded; remains unchecked |
| Non-hermetic mutating smoke test | bug | V2, Validation Contract, Success Criteria | Replace real update smoke with fake-`just` host dispatch; retain real `just validate` as repo-wide check | V2 commands changed; remains unchecked |
| Incomplete E2E report and vacuous redaction checks | bug/hardening | T3, V3, Success Criteria | Add deterministic failure episode, explicit reflection, four-artifact validation, retained-useful-evidence assertions | T3/V3 criteria expanded; remain unchecked |
| Missing executable final/archive status | process defect | Validation Contract, Execution Checklist, Execution Status | Define F1-F5 commands/evidence/pass criteria and add required status section | F1-F5 remain unchecked with explicit semantics |
| Plan artifact identity and safety wording | hardening | T2, T3 | Record existing plan artifact hashes/metadata references; never label plan exit 0 reviewed or safe | T2/T3 criteria expanded; remain unchecked |
| Sensitive local retention | hardening | Constraints, T3, Handoff Notes | Document episodes as sensitive and provide explicit operator-controlled purge command without automatic cleanup | T3 criteria expanded; remains unchecked |

## Intentional Omissions

| Finding | Reason omitted or limited |
|---------|---------------------------|
| Parse all OpenTofu resource identities and enforce deployment resume policy in the journal | The MVP does not apply or authorize deployment. Existing plan/apply safeguards remain authoritative; the journal records metadata and explicitly avoids a second policy engine. |
| Reduce output to one JSON file and one log | Conversation requirements explicitly call for JSONL events, summary, commands, failures, and bounded reflection. Orchestration is removed instead. |
| Verified live recovery execution | Requires backup, direct endpoint/state, canary, and rollback design. It remains a separate rollout plan; annotations cannot clear incidents. |

---
reviewer: security-reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect -- high because the stated redaction guarantee is not achievable with the specified corpus"
  confidence: high
  evidence: "The plan requires `test_redaction_corpus` to cover seeded secrets, bearer values, private IPv4/IPv6, private domains, and sensitive paths, while also requiring exact `command_argv` and exact recovery commands and forbidding the runner from reading credential values (T1 AC3; Telemetry & Evidence Contract; Automation Plan). Arbitrary passwords, API keys, JWTs, query-string credentials, base64/encoded secrets, custom hostnames, and secrets printed by `just`/Docker are not covered by those classes. Passing a finite seeded corpus cannot establish that artifacts contain no private values."
  required_fix: "Define a concrete fail-closed redaction contract: structural rules for common secret formats plus exact-value replacement loaded in memory from authorized private inputs without persisting them, and explicit treatment of shell/argv/output. Do not claim exact commands when they contain sensitive material; store a sanitized argv plus a stable hash or safe command identifier. Add adversarial fixtures for custom secrets, URLs with credentials/query tokens, multiline/private-key material, encoding, and child output."
- severity: high
  category: "substantive defect -- high because an attacker or accidental local link can redirect evidence writes outside the intended runtime boundary"
  confidence: high
  evidence: "The CLI accepts `--root .tmp/update-session-smoke`, `--episode <id>`, and `--evidence <non-secret-path>`, but the plan specifies no canonicalization, traversal rejection, symlink policy, or permission checks (V2 AC2; Automation Plan; Telemetry contract). The requirement that evidence paths be relative under the episode directory is only a data contract, not an enforced write/read boundary. An episode id such as `../...`, a root symlink, or an evidence path symlink can overwrite/read arbitrary files; `record` can also attach a path outside the episode."
  required_fix: "Constrain episode IDs to a strict generated format, resolve and verify root/episode/evidence paths remain beneath a trusted runtime root, reject symlinked components (including pre-existing episode directories), and open files with no-follow/exclusive semantics where supported. Make `--evidence` accept only an existing regular file under the episode directory or copy bounded content into a controlled file; test traversal, absolute paths, symlinks, junctions, and races."
- severity: high
  category: "substantive defect -- high because subprocess execution and inherited runtime state can expose credentials even if the environment dictionary is never serialized"
  confidence: high
  evidence: "The wrapper must execute real `just update`, `just validate`, and `just plan` (V2 validation), while this repository's `just validate` consumes `values/` and `run-infra.sh` converts `values/.env` into an env file for Docker. The plan only says not to record environment contents. Child processes can print environment-derived tokens/URLs, Docker can emit them, and command-line arguments are observable via process listings; bounded capture and the listed redaction corpus do not prevent those values reaching disk."
  required_fix: "Specify `shell=False`/list-only subprocess invocation, a deliberate environment policy (inherit only required variables and never pass secrets as argv), and a capture policy that treats child output as hostile. Redact before every persistence path, including exceptions, timeouts, signals, stderr, report rendering, and recovery records. Add tests with a fake child that emits inherited-secret values and verifies no artifact contains them; fail closed or store only a code/hash when sanitization is uncertain."
- severity: medium
  category: "substantive defect -- medium because concurrent record/reflect or interruption can corrupt or lose the security-relevant audit trail"
  confidence: high
  evidence: "T1 says the writer must use a per-episode lock or fail closed, but does not define lock ownership across `run`, `record`, `reflect`, or multiple processes. JSONL append atomicity, torn final lines, fsync, and recovery after termination are unspecified; the acceptance text specifically expects durability when interrupted after process completion. Atomic summary writes do not make event appends durable or prevent `reflect` from reading a partial stream."
  required_fix: "Define one cross-process episode lock covering all writers and report generation, reject concurrent mutation rather than merge, append complete records under the lock with flush/fsync (and directory durability where applicable), and make readers reject/quarantine torn lines. Add subprocess concurrency and kill-after-child-exit tests, then ensure a resume cannot silently rewrite or omit the first failure."
- severity: medium
  category: "substantive defect -- medium because `.gitignore` prevents Git tracking but provides no confidentiality or retention guarantee"
  confidence: high
  evidence: "The plan treats ignored `.tmp/update-runs/` as the safe runtime artifact root and defers all automatic cleanup/retention. Reports intentionally contain exact successful/recovery commands, paths, failure output, and operational evidence (MVP Boundary; Explicit Deferrals; Archive rule). On Windows, inherited ACLs and Docker bind mounts may allow other local users/containers to read them, and backup/indexing/crash tooling may copy them. Ignored files can still be staged explicitly or included by broad archives."
  required_fix: "Classify episodes as sensitive local operational data, enforce restrictive directory/file permissions/ACLs with a verified fallback on Windows, avoid storing raw paths and exact commands unless sanitized, and document/expose explicit operator-controlled purge plus backup/index exclusion. Add a permission and archive-boundary test/check; do not use the fact that `.tmp/` is ignored as the safety argument."

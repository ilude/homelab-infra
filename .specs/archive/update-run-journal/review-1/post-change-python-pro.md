---
reviewer: post-change-python-pro
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: subprocess-signals
  confidence: high
  evidence: "T2 requires exact child exit-code parity, while the runtime schema requires a nonnegative `exit_code` and a separate `signal` field. `subprocess.Popen.returncode` is negative on POSIX signal termination, and the plan does not specify process-group creation, forwarding of SIGINT/SIGTERM, child reaping, or the wrapper's own return value after an interrupted child. `command_completed` in `finally` also conflicts with the declared `command_interrupted` event without a transition rule."
  required_fix: "Define one signal contract for POSIX and Windows: process-group/session setup, which parent signals are forwarded, wait/reap behavior, interrupted event fields, and wrapper process exit mapping. State whether exact parity applies only to ordinary nonnegative child exits. Add POSIX signal and Windows Ctrl-C/process-termination fixtures that assert exactly one terminal event and no orphan child."

- severity: high
  category: filesystem-locking
  confidence: high
  evidence: "The plan relies on exclusive creation plus canonical path checks to reject symlinks and junction-like paths, but it does not define race-safe opens or deletion. Resolving a path and then opening or recursively purging it is TOCTOU-prone if a component is replaced with a symlink or Windows junction. CPython standard `open()` does not provide a portable no-follow, directory-handle traversal primitive, and Windows reparse points differ from POSIX symlinks."
  required_fix: "Specify a supported platform-safe implementation rather than a pre-check: use platform-specific handle/descriptor-safe operations or narrow the guarantee to a root whose parents are operator-owned and reject unsupported reparse-point protection before creating episodes. Apply the same rule to events, reports, locks, and purge. Add race-oriented tests or platform-gated tests for symlink and junction replacement during append and purge."

- severity: high
  category: purge-concurrency
  confidence: high
  evidence: "The lock protects writers and the report reducer, but purge is not included in the lock ownership contract. A purge can therefore remove an episode while `run` has spawned a child or while `reflect` is reading events. Conversely, a stale lock must fail closed and cannot be automatically removed, but the plan does not say how an operator can purge the now-unusable episode without weakening that rule. Windows open-file sharing can also make lock-file and directory deletion fail differently from POSIX."
  required_fix: "Define purge as a synchronized state transition: coordinate from a lock outside the target episode or otherwise atomically prove no active owner, reject active and ambiguous locks, and give an explicit inspected-stale-lock recovery procedure. Specify Windows sharing-violation behavior as a clean failure. Add concurrent run/reflect/purge and stale-lock purge tests that prove no child output or event write can occur after deletion begins."

- severity: medium
  category: subprocess-output
  confidence: high
  evidence: "The plan requires terminal teeing, independent 64 KiB stdout/stderr excerpts, UTF-8 replacement, line-level fail-closed redaction, and chunk-boundary-secret handling, but it does not define the pump. A sequential `read()` deadlocks when the other pipe fills; `readline()` permits an unbounded no-newline record; selectors do not support Windows pipe handles; and independently drained streams cannot preserve a single original cross-stream ordering."
  required_fix: "Specify a bounded binary-stream design, such as one reader thread per pipe with fixed-size reads, bounded retained excerpts, a synchronized terminal writer, and sanitizer overlap state. Define the intentional terminal ordering guarantee and behavior for undecodable or unterminated data. Add high-volume stdout/stderr, no-newline, cross-chunk secret, and child-exits-before-drain tests on Windows and POSIX."

- severity: medium
  category: redaction-contract
  confidence: high
  evidence: "The plan says private domains, sensitive paths, encoded fixtures, and unsafe lines are redacted, but supplies no decision procedure for an arbitrary real hostname, custom token, encoded secret, or exception text. The runner is also prohibited from reading private values needed for exact-value matching. A finite seeded corpus can demonstrate only those fixtures, not the stated guarantee that artifacts never persist private values while retaining useful child output."
  required_fix: "Replace the broad claim with an enforceable contract. Prefer structured allowlisted fields for durable evidence and redact opaque child text by default, or define approved in-memory exact-value sources plus bounded structural detectors and a deterministic fallback marker. Cover exception formatting, notes, report rendering, URLs, multiline material, arbitrary tokens, and encoded data with adversarial tests that prove both no leak and retained safe fields."

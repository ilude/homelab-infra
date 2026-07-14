---
reviewer: post-change-reviewer
status: complete
finding_count: 3
---

# Findings

- severity: high
  category: "archive mechanics"
  confidence: high
  evidence: "plan.md:332 requires `.specs/archive/update-run-journal/review-1/synthesis.md` in F5 postcondition, but the task breakdown/waves contain no task or acceptance criterion that creates `synthesis.md`; the archive rule at lines 334-343 only moves existing sibling artifacts. The required file is therefore absent under the plan's own execution contract."
  required_fix: "Either add a prerequisite synthesis task with an explicit producer, path, and validation before F5, or remove/replace the postcondition requirement with artifacts this plan actually creates."
- severity: medium
  category: "subprocess exit semantics"
  confidence: high
  evidence: "plan.md:54, 188, 197, and 284 require exact wrapper/child exit-code parity, while lines 360 and 368 require a nonnegative `exit_code`, separate signal field, and completion persistence in `finally`. A POSIX subprocess terminated by a signal is represented as a negative return code in Python, whereas the wrapper's shell-visible status is conventionally 128+signal; a completion-write failure after a successful child also conflicts with unconditional parity. No precedence or encoding is specified or tested."
  required_fix: "Define and test a single exit-status contract for normal exits, signal termination, journal completion-write failure, and interruption. State the stored fields and shell return status for each case, including whether a journal durability failure overrides child status."
- severity: medium
  category: "prerequisites and command executability"
  confidence: high
  evidence: "The declared operator platform is Windows (plan.md:17), while every host invocation directly executes the Bash script `scripts/host-python.sh` (for example lines 83-85 and final gates) and F1/F3 explicitly invoke `bash` (lines 290-294, 326-328). The plan documents only CPython installation and does not declare or verify a Windows Bash runtime, executable-bit/shebang behavior, or a supported invocation from the documented shell."
  required_fix: "Document and preflight the required Windows Bash environment (for example Git Bash/WSL) and use that explicit launcher consistently, or provide a Windows-native host launcher and update every verification command and test accordingly."

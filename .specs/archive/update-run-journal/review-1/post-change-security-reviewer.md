---
reviewer: post-change-security-reviewer
status: complete
finding_count: 3
---

# Findings

- severity: high
  category: "redaction / sensitive output"
  confidence: high
  evidence: "Wave 1 permits persistence of child stdout/stderr excerpts after an unspecified sanitizer decides a line is safe, while the child inherits its environment and may emit arbitrary downstream output. The proposed tests only require removal of seeded fixture values. The stated prohibition covers all credential values, private domains/IPs, raw inventory, and unredacted child output, which a blocklist-style sanitizer cannot establish for unknown values."
  required_fix: "Make persisted child evidence strictly allowlisted structured metadata (recipe, exit/signal, bounded stable failure signature) by default, or define and test a conservative grammar that rejects all non-allowlisted output. Treat any unmatched/redaction-uncertain content as the deterministic marker, and test unknown secret-shaped values and report rendering paths."
- severity: high
  category: "deletion boundary / TOCTOU"
  confidence: high
  evidence: "The purge contract validates a direct-child, non-symlink episode path and then deletes it, but specifies no race-resistant operation between validation and recursive deletion. A local concurrent actor can replace the checked directory with a symlink/junction/reparse point before deletion; the plan's generic canonical checks do not bind the deletion to the checked object."
  required_fix: "Specify a race-resistant purge primitive: acquire the episode lock, validate using no-follow/reparse-point-aware handles, atomically rename the validated directory to a unique non-symlink tombstone under the canonical journal root, revalidate it, then recursively delete without following links. Fail closed on any reparse point and add a swap-race regression test."
- severity: medium
  category: "archive safety / path containment"
  confidence: high
  evidence: "The Archive rule executes `mkdir -p .specs/archive` followed by `mv .specs/update-run-journal .specs/archive/update-run-journal` with only an existence check for the target. It does not verify that `.specs`, `.specs/archive`, the source, and target parent are canonical non-symlink directories beneath the repository root. A pre-existing symlink/junction in the archive path can redirect the move outside the repository and relocate the plan and review artifacts."
  required_fix: "Before archiving, resolve the repository root and require each archive path component and source to be non-symlink/non-reparse directories canonically contained beneath it; reject an existing destination of any type. Perform the move with a documented same-filesystem atomic rename where possible, then revalidate the archived path before editing it."

---
date: 2026-07-14
status: applied
---

# Known Blocker Fixes

Source: `.specs/update-run-journal/review-1/standalone-readiness-blockers.md`

| Blocker | Sections edited | Fix |
|---------|-----------------|-----|
| Host Python absent from repository prerequisites | Constraints, Project Context, Automation Plan, T1, T3, checklist/handoff | Added a CPython 3.11+ host selector, actionable fresh-setup prerequisite/documentation work, platform-specific resolution tests, and preflight evidence. |
| Documentation check could pass on one phrase | T3 acceptance criteria | Replaced one alternation with independent required checks for every policy statement. |
| Archive gate lacked completion proof | Final gate commands, Archive rule, F5 checklist, Execution Status | Added separate preflight and postcondition commands, archived status/path evidence, source/archive path checks, review artifact check, and partial-move failure handling. |
| Empty episode ID could broaden purge | MVP Boundary, Explicit Deferrals | Removed purge from the MVP and deferred retention cleanup. |

No blocker was omitted. All checklist items remain pending.

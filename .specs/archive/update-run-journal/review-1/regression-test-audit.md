GAP - static inspection only; no recipes/Docker/network run.

Covered:
- Hostile child output: `RunnerTests.test_host_recipe_dispatch`, `ReflectionTests.test_reports_are_safe_and_useful`
- Platform isolation: `RunnerTests.test_windows_nonnegative_return_code_contract`
- Windows lock retry/denial: `JournalTests.test_lock_release_*`
- Malformed UTF-8: `ReflectionTests.test_malformed_utf8_events_*`
- Report replacement/completion append failures: `ReflectionTests.test_start_reflect_verify_truth_table`
- Invalid CLI status 2: `ReflectionTests.test_invalid_start_reflect_verify_arguments_return_two` plus runner invalid-input cases

Concrete gap:
- The exact F2 wrapped-validation shell workflow is not automated with a fake `just`. The closest host CLI test stops after `run`; E2E tests call journal classes directly. Thus wrapper sequencing, artifact loop, and `run_rc` precedence over reflection/artifact failures are only claimed in plan evidence, not regression-tested.
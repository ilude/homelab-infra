[
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "A successful journal run could leave an operator with a plan artifact whose inputs no longer match the intended apply, allowing stale or unrelated drift to be treated as the reviewed result.",
    "evidence": "T2 says --through plan may write the repository-root tfplan artifacts (plan.md:191-192), but it does not bind tfplan/tfplan.meta.json to the episode or record hashes and input identity. The proposed record command only attaches an arbitrary evidence path (plan.md:148-149), while existing apply verifies the saved files independently; there is no journal resume gate requiring a fresh plan after source, values, settings, or target changes.",
    "required_fix": "Record relative paths plus SHA-256 and the plan metadata/input fingerprint for tfplan and tfplan.meta.json without copying private plan contents into the episode. Add a resume rule and test that any relevant checkout, values, settings, target-service, or plan-file change blocks apply guidance and requires rerunning the public just plan entry point.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "OpenTofu plan can exit successfully while showing deletes, replacements, or stateful drift; bounded sanitized output can hide the very changes that must stop a rollout.",
    "evidence": "The plan promises per-phase bounded sanitized logs (plan.md:132) and only requires that plan mode record possible local artifacts (plan.md:191-192). T2 has no acceptance requirement to parse tfplan metadata or preserve complete counts and resource identities for destroys, replacements, or stateful services. Existing safeguards are enforced by apply-infra.sh, but a journal summary that merely reports exit code 0 can obscure destructive drift before the operator reviews it.",
    "required_fix": "After plan completes, parse the existing tfplan metadata/summary and record structured create/update/replace/destroy counts, target scope, stateful-service scope, and artifact paths. Make destructive or stateful-batch findings prominent and blocking for resume guidance, and add fixtures proving truncation/redaction cannot turn a destructive plan into a clean result.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "The specified invocation crosses the Docker boundary incorrectly and can fail before exercising the real user workflow, or recurse into Docker from inside the tooling container.",
    "evidence": "The documented runner command is launched through scripts/python.sh (plan.md:143,155), which already executes inside docker compose run. T2 then says the runner invokes the existing just update, just validate, and just plan commands (plan.md:188-190). Those recipes call scripts/python.sh and scripts/run-infra.sh, which invoke docker compose again; the plan provides no host-boundary wrapper, socket/tooling contract, or exact smoke test for nested invocation. V2's smoke command is itself launched through scripts/python.sh (plan.md:225), so fake subprocess tests do not prove the real Windows/Docker path.",
    "required_fix": "Choose and document one execution boundary: run the journal launcher on the host so it can invoke the unchanged public just recipes, or add a deliberate in-container mode that invokes the inner commands without recursively calling Docker while preserving their environment and exit semantics. Add a Docker Desktop smoke test from the same host entry point an operator uses, including failure propagation and artifact visibility.",
    "confidence": "high"
  },
  {
    "category": "substantive defect",
    "severity": "high",
    "severity_rationale": "An operator can attach a claimed recovery result and receive an apparently cleared incident without proof that recovery succeeded or that the original endpoint and state are healthy.",
    "evidence": "The record operation accepts --status passed, an exact command string, and an arbitrary evidence path, but explicitly does not execute recovery (plan.md:148-149,190). T2 nevertheless requires later phases to remain blocked until an explicit recovery record is added and describes incident transition/recommended recovery (plan.md:199-201). The telemetry contract requires original endpoint/state validation for a future live mutation (plan.md:260), but no record schema or acceptance test requires those checks, binds the evidence to the failed episode, or prevents a false passed record.",
    "required_fix": "Separate an operator annotation from an incident-clearing event. A recovery record must be immutable, episode-bound, reference existing sanitized evidence, include the failed phase and original endpoint/state validation results, and remain non-clearing unless a verifier command or explicitly validated evidence contract passes. Add tests for missing, unrelated, and forged passed recovery evidence; do not call non-live failures a live-mutation incident.",
    "confidence": "high"
  },
  {
    "category": "process defect",
    "severity": "medium",
    "severity_rationale": "The validation plan can declare the wrapper safe without proving that existing plan freshness, one-service canary, backup, and apply refusal boundaries remain observable and actionable after a partial failure.",
    "evidence": "V2 only requires a real update smoke run and exit-code/artifact checks (plan.md:220-226). The plan explicitly defers automatic backup-age enforcement, apply, rollback, and stateful orchestration (plan.md:157-165), but adds no integration fixture for stale tfplan metadata, a destructive plan, a stateful batch, or the first failed mutation transition. The repository workflow requires reviewing creates/changes/destroys, fresh plans, verified backups, and one-service canaries before apply (README.md:126; AGENTS.md:81-86); those controls are not represented in the journal acceptance contract.",
    "required_fix": "Add non-live fixtures that feed stale metadata, destroy/replacement summaries, missing/expired backup evidence, and multi-stateful-service plans through the journal. Require the report to preserve the existing apply hold and name the public recovery entry point (rerun just plan, canary target, backup/state check) rather than recommending rollback or deployment actions that the MVP cannot perform.",
    "confidence": "medium"
  }
]

---
name: hermes-fork-maintenance
description: "Maintains the homelab Hermes fork, releases, pins, deployment, rollback, and upstream synchronization. Use when changing, updating, releasing, or deploying the customized Hermes Agent fork. Not for routine Hermes operation or upstream contributions."
---

# Hermes Fork Maintenance

**Auto-activate when:** changing `../hermes-agent`, building a `homelab-v*` release, switching Hermes artifact pins, updating the fork from NousResearch, or deploying a customized Hermes wheel.

## Boundary

- Fork: the repository configured by `hermes_custom_repository`, checked out at `../hermes-agent`.
- Public infrastructure: this repository.
- Private site pins, generated custom locks, backups, and state: `values/`.
- Runtime state: `/home/<runtime-user>/.hermes` in the Hermes LXC.
- Do not open upstream issues, discussions, or pull requests without a separate contribution-policy review and explicit operator approval.
- Do not push, tag, publish, plan, or apply unless the operator has explicitly requested that Git action or deployment outcome.

## Branch and Remote Model

In `../hermes-agent`:

- `origin` is the operator's fork.
- `upstream` is `git@github.com:NousResearch/hermes-agent.git`.
- `main` follows the fork's upstream baseline.
- `homelab` contains the minimal customization patch set.
- Never force-push published branches or tags.
- Merge reviewed upstream changes into `homelab`; do not silently rebase published customization history.

Verify before work:

```bash
git -C ../hermes-agent status --short --branch
git -C ../hermes-agent remote -v
git -C ../hermes-agent fetch upstream --tags
git -C values status --short --branch
git status --short --branch
```

Preserve unrelated changes in all three repositories.

## Customization Rules

1. Reproduce the behavior against the currently deployed fork commit.
2. Keep each customization as a focused commit with focused tests.
3. Preserve Hermes package name, console entry points, dashboard/TUI assets, messaging imports, and state format unless a separately reviewed migration requires otherwise.
4. Keep user data and configuration outside application releases. Never package or replace `.hermes` state.
5. Prefer a `config.yaml` setting over a new environment variable for non-secret behavior.
6. Do not modify installed `site-packages` on the LXC. Changes belong in the fork and are deployed as a verified wheel.

## Validate the Fork

Use Hermes's canonical test wrapper on POSIX:

```bash
cd ../hermes-agent
scripts/run_tests.sh <focused-test-path> -q
```

On Windows, if the wrapper cannot detect `.venv/Scripts/python.exe`, invoke `scripts/run_tests_parallel.py` with that project-local interpreter and set `PYTHONUTF8=1`, `TZ=UTC`, `PYTHONHASHSEED=0`, and `PYTHONDONTWRITEBYTECODE=1`.

Before release, the GitHub workflow also:

- installs the locked development environment;
- runs the customization regression tests;
- builds dashboard and TUI assets;
- builds the universal Python wheel;
- installs that wheel into a clean Python 3.13 environment;
- runs `pip check` and import/asset/CLI smoke checks;
- records the wheel SHA-256.

## Release Workflow

Releases use tags shaped as:

```text
homelab-v<package-version>.<positive-revision>
```

Example for package version `0.18.0`:

```text
homelab-v0.18.0.1
```

The package version remains aligned with the upstream base release for this first customization line. The revision distinguishes fork builds without changing dependency metadata.

Release procedure:

1. Confirm `homelab` is clean and contains only reviewed customization commits.
2. Run focused tests and inspect the complete diff from the deployed tag.
3. Confirm the tag revision has never been published.
4. Create and push the tag only after explicit operator approval.
5. Wait for `.github/workflows/homelab-release.yml` to publish the wheel and `.sha256` release assets.
6. Do not deploy a draft, prerelease, failed workflow, or release younger than the configured 168-hour hold.

GitHub release assets are trusted as output of the configured fork. `just update` independently downloads the wheel, validates its canonical release URL, checks the manifest and actual SHA-256, confirms package metadata compatibility with the official wheel, resolves the exact tag commit, and writes checksum-specific private locks.

## Select the Fork in Private Values

Set these only in `values/ansible/inventory/local.yml`:

```yaml
hermes_artifact_source: custom_github_release
hermes_custom_repository: <fork-owner>/hermes-agent
hermes_custom_tag_prefix: homelab-v
```

Leave `hermes_custom_wheel_url` and both custom lock paths to `just update`. It writes them as one pin group after validating an eligible release. Generated locks live under checksum-specific directories in `values/artifacts/hermes/`.

Never place the real repository selection or generated private pin state in `scaffold/`.

## Update and Deploy

Run the public workflow only:

```bash
just update
just validate
just plan
```

Review:

- selected tag and exact source commit;
- wheel SHA-256 and canonical release URL;
- generated full and dependencies-only locks;
- Hermes-only resource changes;
- no LXC replacement, state deletion, or unrelated service mutation.

Before applying a stateful Hermes update, require a current checksum-verified backup and known restore path. Then use the approved public apply path:

```bash
just apply
```

The Ansible role:

- downloads official dependencies from the hash-locked dependencies file;
- verifies the custom wheel before pip sees it;
- installs offline from the local wheelhouse;
- stages a checksum-specific release directory;
- atomically switches the active venv;
- retains the previous release;
- verifies gateway and dashboard health;
- restores and verifies the previous runtime if activation fails.

## State and Rollback Invariants

- `/home/<runtime-user>/.hermes` is never inside a release directory.
- Application rollback does not automatically undo state-schema mutations.
- Do not merge or deploy a fork change that migrates state unless backward compatibility, backup, restore, and rollback behavior are separately proven.
- Replace only the Hermes application release in this rollout wave.
- On the first failed live mutation, enter incident mode: stop unrelated work, preserve healthy services, recover Hermes directly, and verify its original endpoint and state before resuming.

## Upstream Synchronization

Treat upstream updates as a separate reviewed wave from customization changes.

1. Fetch `upstream main` and tags.
2. Review upstream release notes, dependency changes, state/config migrations, and packaging changes between the deployed base and candidate.
3. Merge the candidate upstream baseline into `homelab` without rewriting published history.
4. Resolve conflicts by preserving the customization's behavioral tests, not by blindly choosing either side.
5. Regenerate the Debian 13 amd64/Python 3.13 dependency lock when package metadata changes.
6. Run the relevant Hermes regression suite and release smoke checks.
7. Publish a new `homelab-v*` revision.
8. Use the normal hold, update, validate, plan, backup, and canary apply sequence.

## Contribution Boundary

A fork change does not imply an upstream contribution. Before any upstream contact:

- read current `AGENTS.md`, `CONTRIBUTING.md`, security policy, templates, DCO/CLA rules, and automation-assistance policy;
- search existing issues and pull requests;
- inspect maintainer guidance on comparable changes;
- present a contribution plan to the operator;
- obtain explicit approval before opening any issue, discussion, comment, or pull request.

## Verification Checklist

- Fork regression tests pass.
- Release workflow syntax and pinned actions are validated.
- Published wheel installs cleanly and contains dashboard/TUI assets.
- `just update` writes an immutable checksum-specific private lock directory.
- `just validate` passes without warnings.
- `just plan` shows no replacement or unrelated mutation.
- Backup and restore path are verified before apply.
- Direct Hermes SSH/HTTPS endpoint, gateway, dashboard, and persisted state pass after apply.
- Windows Terminal launches `/usr/local/bin/hermes` directly; no local stderr filter is required after the fork is deployed.

# Site-Aware Values and Service Selection Migration

**Status:** Implemented — site-aware development validation completed; production
was left untouched.

## Objective

Allow one private values repository to describe multiple independent sites and
environments without duplicating the infrastructure source repository.

The canonical shared development environment is named `dev`. Persistent sites
may have optional disposable shadow environments such as `site-a-dev`.

## Target model

```text
values/
  settings.local.json              # operator metadata and values remote only
  sites/
    dev/
      site.json                    # class, lifecycle, policy, services
      .env
      terraform.tfvars
      terraform.tfstate*
      dns-records.local.json
      ansible/inventory/local.yml
      ansible/known_hosts
    site-a/
      site.json
      ...
    site-a-dev/
      site.json
      ...
```

The source repository remains shared. Site values, state, credentials, DNS
records, and inventories remain private and site-local.

## Site metadata

Each site must declare policy independently of its name. A site metadata file
should contain public-safe structure such as:

```json
{
  "name": "dev",
  "class": "development",
  "lifecycle": "disposable",
  "allow_apply": true,
  "allow_destroy": true,
  "services": ["technitium", "hermes"]
}
```

The `services` list moves out of the repository-root `settings.local.json`.
The root settings file retains private values-repository metadata such as its
remote. It may contain a local preference for displaying a site, but mutation
commands must require an explicit site context.

The shared `dev` site is created by default as the repository conformance
target. A `<site>-dev` shadow site is optional and should be created only when
site-specific network, storage, DNS, service-selection, migration, or rollback
behavior requires rehearsal.

## Safety invariants

- A site context resolves values, inventory, DNS records, state, known-hosts,
  plan artifacts, and site metadata together.
- A plan records the site identity and cannot be applied for another site.
- Production and development state files are never shared.
- Production credentials and backups are never copied into `dev` or a shadow
  site unless an explicitly reviewed test requires a non-secret fixture.
- `just plan`, `just apply`, restore, and teardown require an explicit site.
- The default `dev` target must not become an implicit production fallback.
- Site names are identifiers; class and lifecycle metadata control safety.
- Existing root-layout users receive a deliberate migration path, not silent
  path guessing.

## Implementation phases

### Phase 1 — Define and test the site context

- Add a single resolver for `VALUES_SITE`, `VALUES_DIR`, and site paths.
- Resolve site metadata, service selection, env file, Terraform variables,
  state, DNS records, inventory, and known-hosts from one context.
- Preserve `VALUES_DIR` as a low-level compatibility override.
- Add tests for missing sites, unknown sites, path traversal, and production/dev
  separation.

### Phase 2 — Move service selection into sites

- Update `scripts/settings.py` to read root operator metadata separately from
  selected site metadata.
- Add site metadata to the scaffold.
- Remove the service list from `settings.local.json`.
- Add `values/sites/dev/site.json` with the initial conformance service set.
- Validate every selected service against `infra/services.json` and its
  dependency graph.
- Add migration logic that moves the existing root service list into the
  selected production site.

### Phase 3 — Update workflow consumers

Update all consumers of the root values layout, including:

- `just` setup, validation, plan, and apply workflows;
- `scripts/run-infra.sh`;
- OpenTofu plan/state and metadata helpers;
- dynamic Ansible inventory;
- service-state backup and restore;
- DNS synchronization;
- update and migration scripts;
- operator status and action tooling.

Every path must come from the same resolved site context. Avoid permanent
parallel path knobs.

### Phase 4 — Migrate private values safely

- Use `scripts/migrate-site-values.py` for a dry-run first, then an explicit
  `--apply` after review.
- Back up the private values repository and verify its current status.
- Create the persistent production site directory without changing values.
- Move production env, tfvars, state, DNS records, inventory, and known-hosts
  atomically within the private repository.
- Create the isolated `dev` site with independent generated secrets and state.
- Keep the existing temporary dev checkout until site-aware validation passes.
- Do not commit, push, apply, destroy, or delete old paths during preparation.

### Phase 5 — Validate and cut over

For each site:

```text
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
```

Compare the production plan before and after migration. The expected result is
no production resource change caused solely by path migration. Validate the
dev plan separately and confirm only dev VMIDs, addresses, names, VLANs,
state, and DNS records are selected.

After explicit approval, use the site-aware apply workflow for dev first. Run
production only after the migration has passed wiring, plan metadata, and
rollback checks.

**Validation result:** The isolated `dev` cycle completed successfully on the
correct Proxmox target. Its state, service configuration, backup/restore path,
endpoint checks, and final zero-change plan were validated. Production was not
applied or modified.

The migration helper refuses an existing target site, active Terraform locks,
and missing legacy files. Its apply path rolls back completed moves if a later
operation fails, and it never prints secret contents.

### Phase 6 — Remove compatibility paths

Completed after the successful site-aware dev cycle:

- removed obsolete root values assumptions;
- removed the temporary dev checkout;
- updated documentation and agent instructions;
- retained a clear migration or rollback tool for older private values layouts.

## Testing requirements

- Resolver unit tests for every site path.
- Service-selection and dependency tests.
- Plan metadata site-binding tests.
- Cross-site state and credential isolation tests.
- Root-layout migration tests using disposable fixtures.
- Public-safety and path-traversal tests.
- Production plan equivalence test before/after migration.
- Dev plan test for the canonical conformance services.
- Site-specific shadow plan tests where applicable.
- No live apply or teardown is evidence for the migration until the isolated
  dev path has passed validation.

## Open decisions

- Exact site metadata filename and schema.
- Whether site metadata is JSON or YAML.
- Whether `VALUES_SITE` is mandatory for validation as well as mutation.
- Whether the production site keeps its current name or becomes `prod`.
- Whether a site-shadow generator should materialize values or use explicit
  overlays.
- Whether site-specific private values share one private remote or use separate
  remotes with a common repository convention.

## Rollback

Rollback must restore the original private values layout from the verified
backup, remove only site-aware generated artifacts, and leave public source
unchanged. State files must never be renamed, copied, or reused across sites
without an explicit state migration procedure and matching plan metadata.

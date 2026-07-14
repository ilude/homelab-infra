# Service update policy

Managed services should use deterministic version pins and the normal reviewed workflow:

```bash
just update
just validate
just plan
just apply
```

`just update` applies the release-age safety hold before changing supported pins. For private inventory, it advances a version/checksum set only when every field still matches the runbook's managed defaults; a differing version or checksum is treated as an operator pin and is left unchanged. OCI updates use a 168-hour hold, Registry V2 multi-arch indexes, matching header/body digests, and a linux/amd64 manifest; the tag is resolved again immediately before writing. After any update, review the diff and plan before applying.

## Local update-run journal

Use the host-side journal only to observe one existing public recipe at a time:

```bash
episode_id="$(scripts/host-python.sh scripts/update-session.py start)"
scripts/host-python.sh scripts/update-session.py run --episode "$episode_id" update
scripts/host-python.sh scripts/update-session.py reflect --episode "$episode_id"
scripts/host-python.sh scripts/update-session.py verify --episode "$episode_id"
```

Run later `validate` or `plan` observations explicitly with the same episode ID; the journal never advances the workflow or runs `apply`. Episode files under `.tmp/update-runs/` are sensitive local operational data. Windows ACLs do not guarantee confidentiality, so inspect the exact ignored episode before manually purging it. The journal does not persist command output, environment values, or private inventory; it stores only structured command and report metadata. A successful `plan` observation only records that `just plan` exited successfully and does not mean the plan is reviewed, safe, or approved for apply.

## Managed pins

A service belongs in `just update` when the repo can identify a specific upstream release and update a deterministic local pin. Examples include Forgejo and Forgejo runner.

For downloadable tools or archives, prefer a version plus checksum. If upstream artifacts are mutable or unversioned, cache the reviewed artifact in ignored private storage and install from that cache during `just apply`.

## OCI image pins

Infisical, PostgreSQL, Redis, SearXNG, and the tooling Debian base use full `registry/repository:tag@sha256:...` references. The managed defaults are:

- `docker.io/infisical/infisical:v0.161.11@sha256:efe2d4fe5f37fb250ce5956ecc4734cc9ab1b50629d97cf7793d54200a18642b`
- `docker.io/library/postgres:16.14-alpine3.22@sha256:786dab398303b8ce7cb76b407bb21ef2e4dfbbbd4c6abcf3d29b3130467ffdbc`
- `docker.io/library/redis:7.4.9-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99`
- `docker.io/searxng/searxng:2026.7.2-67973783d@sha256:33aa33278be6c0be379b95f7c91cd455c18141295291c2e5a396454761df7bbb`
- `docker.io/library/debian:bookworm-20260623-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df`

The updater considers only the bounded version series documented in its resolver and preserves custom pin groups. A tag without a digest, including `latest`, is not a managed default.

## Managed Technitium portable releases

Technitium uses the private pin group `technitium_discovery_version`, `technitium_portable_sha256`, and `technitium_artifact_path`. The historical `discovery` variable name is retained for values-repo compatibility, but the pin now controls the runtime installation. The managed default is version `15.2.0` with its reviewed SHA-256.

`just update` lists stable GitHub releases, requires `published_at`, and chooses the newest release satisfying an exact 168-hour hold even when a newer release is still held. It reads the checksum from the official versioned `.sha256` URL, resolves the release tag commit, re-resolves all metadata before writing, and leaves any custom or partial operator pin group unchanged.

During apply, the role checks for `values/artifacts/technitium/<version>/DnsServerPortable.tar.gz` when the optional cache root is configured. If the file is absent, it downloads the official versioned archive. In either case it verifies the private SHA-256, rejects unsafe archive paths or an unexpected layout, stages a versioned release, and only stops `dns.service` for activation. `/etc/dns` remains outside application releases. The previous application and a pre-activation state snapshot are retained; a failed service, UI, or DNS health check restores both before reporting failure. The installed-version marker is written only after health checks pass, so the first managed conversion stages the pinned archive even when an upstream-installed service already exists.

The versioned archive is preferable to the mutable unversioned URL, but upstream does not state that it is immutable. Its published checksum is unsigned and served from the same origin. The reviewed private SHA-256—and an optional privately retained archive—is therefore the durable integrity boundary. Do not rerun the upstream installer as an update mechanism.

## Managed Hermes Agent wheels

Hermes uses package version `0.18.0`, release tag `v2026.7.1`, commit `7c1a029553d87c43ecff8a3821336bc95872213b`, and official PyPI wheel SHA-256 `bf75c02d59f7c464cd0d85026fb7ee2e6bb15f003beccab3442b572f1ae1fd37`. `infra/ansible/roles/hermes/files/requirements-0.18.0.lock` contains the complete 79-package dashboard and messaging lock generated for Debian 13 amd64, CPython 3.13. Installation requires hashes and binary wheels and has no source-build or unlocked fallback.

The default `official_pypi` source applies a strict 168-hour hold to stable upstream releases. `just update` derives the package version from the release's wheel Sigstore asset name, verifies the official universal wheel and SHA-256 in PyPI JSON, checks PyPI trusted-publishing provenance for `NousResearch/hermes-agent` and `upload_to_pypi.yml`, resolves the tag commit, and re-resolves before writing. Version, tag, commit, and wheel hash advance together only when a matching tracked lock already exists.

The optional `custom_github_release` source discovers operator-selected fork tags shaped as `homelab-v<package-version>.<revision>`. Operator-owned fork releases have no release-age delay after successful publication. Discovery still enforces canonical GitHub release URLs, non-rollback selection, exact tag commit, manifest and downloaded-wheel SHA-256, bounded wheel metadata parsing, and dependency metadata parity with the official wheel. It generates checksum-specific full and dependencies-only locks under private `values/artifacts/hermes/` and switches the private inventory pin group only after both locks are durable. The fork release and GitHub account are the trust boundary; no unsupported provenance claim is made.

Apply stages a checksum-specific venv under `/usr/local/lib/hermes-agent/releases`. Official mode downloads the complete official wheelhouse. Custom mode downloads only hash-locked dependencies from PyPI, verifies the custom wheel before pip sees it, and then installs the full environment offline. Both paths run `pip check`, preserve the previous release, atomically switch `/usr/local/lib/hermes-agent/venv`, and require gateway and dashboard health. Failed activation restores and verifies the prior gateway and dashboard runtime.

Hermes state is not part of an application release. `HERMES_HOME` remains `/home/<runtime-user>/.hermes`, so installation and rollback do not move or replace memory, configuration, credentials, or other runtime state. Application rollback does not reverse state-schema changes; any such fork change requires a separate compatibility and restore review. Do not use `hermes update`, rerun the upstream installer, use a GitHub source archive, or execute downloaded scripts as an update path.

## Managed Caddy builds

`just update` checks Caddy and xcaddy releases, the Cloudflare DNS module's semantic version tags, and the official Go download manifest. Caddy source pins use the normal release hold; Cloudflare and Go tags use a strict 168-hour hold. Go version and architecture checksums advance atomically. Ansible builds the requested Caddy binary before replacing `/usr/bin/caddy`, verifies the embedded Caddy, Cloudflare module, and Go versions, and restarts Caddy only after a successful build.

## Managed Tailscale packages

Tailscale uses `tailscale_client_version` from private inventory. `just update` advances the pin from the stable upstream GitHub release after the normal release hold. Ansible installs that exact version from Tailscale's signed Debian 13 repository, refuses implicit downgrades, and verifies the installed version, service state, and client status. The optional Tailscale service remains disabled unless selected by operator settings.

## Debian security updates

Every managed Debian service host installs `unattended-upgrades` with a security-only origin policy. Package indexes and security upgrades run daily. Automatic reboots are disabled, so kernel or runtime updates that require a restart remain visible for a separately reviewed maintenance action. Non-security distribution upgrades are not automatic.

# Web-fetch gateway

The gateway is deployed at `https://fetch.ilude.com`.

`web_fetch_onramp` is an Ansible-only workload on the existing onramp host. It uses
rootless Podman, an authenticated HTTPS gateway, an internal browser and SQLite
route statistics. Retrieval is sequential: direct HTTP, Trawl or public Jina.
Explicit backend selection is strict. Paywall/archive retrieval is excluded.

The browser installs egress restrictions only in its own network namespace and
then removes NET_ADMIN. Private/reserved IPv4 and new IPv6 are denied. An aborted
request retains its browser lease until idle is observed, or quarantines capacity.
Neither host/router rules nor other workloads are changed.

## Images and configuration

Build the package's `Dockerfile` and `Dockerfile.trawl` using ordinary Podman builds
as the deploy user. Their `NODE_IMAGE` and `TRAWL_IMAGE` build arguments must match
managed digest pins. Record the resulting local `sha256:` image IDs in BWS inventory
as `web_fetch_gateway_image` and `web_fetch_browser_image`. No archive export,
manifest-release identifier, publication playbook or new registry is required.

The role verifies installed image/base identities and the ordinary 168-hour upstream
hold before runtime mutations. SearXNG remains the only 24-hour exception. The tested
Trawl base is eligible on 2026-09-11T01:27:47Z. Building an image does not waive this hold.

BWS owns upstream pins (`web_fetch_node_image`, `web_fetch_trawl_image`), site/DNS
configuration and selector enablement. `WEB_FETCH_GATEWAY_CLIENT` holds the HTTPS
URL and bearer token. Default Pi resolves this exact record lazily through BWS and keeps the token only
in process memory. Environment URL/token values remain explicit overrides. No
additional Pi launcher is provided. Keep credentials and real inventory out of
public files.

When configuration, eligibility and rollout authorization are satisfied:

```bash
scripts/apply-service.sh web_fetch_onramp
```

The role checks gateway/browser health, separate namespaces and anonymous request
rejection before publishing the Caddy route. Gateway/browser resource limits are
768 MiB/one CPU and 2 GiB/two CPUs. Verify current host headroom before rollout.
`just update web_fetch_onramp` discovers only its Node 24/Trawl 1.x upstream pins;
rebuild locally before selecting new application image IDs.

## State, fallback and checks

Before replacing a healthy deployment, use `scripts/service-state.sh backup
web_fetch_onramp`. It quiesces only the new user service and snapshots configuration
and SQLite consistently. Restore a matching checksummed archive with the existing
`restore web_fetch_onramp <archive>` command when needed; retain prior image IDs and
matching BWS settings. Reload Caddy if its fragment was restored. Shared Caddy must
not be stopped as part of this service's backup.

Pi can return to standalone fetching by unsetting its gateway environment settings
and relaunching normally. Private/local access, public Jina fallback and one final
annotation-only Luna review remain available. Private content also reaches Luna's
configured provider.

Package checks: `pnpm run typecheck`, `pnpm test`, `pnpm run build` from
`services/web-fetch-gateway/`. Real HTTPS, direct/Trawl retrieval and Pi/Luna use are verified. Unit and
disposable-fixture checks alone are not deployment proof.

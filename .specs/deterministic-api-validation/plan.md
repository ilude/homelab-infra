---
created: 2026-08-13
status: complete
owners:
  - onclave
  - homelab-infra
---

# Plan: Simple Deterministic API Validation

## Outcome

Deployment validation uses standard HTTPS requests and explicit response checks. It does not start Pi or Claude, invoke models, simulate sessions, sleep, poll, retry, or depend on prior test data.

Menos is not a separate deployment. Its content API is part of the unified Onclave HTTPS service, so Onclave and former Menos routes are validated in one request sequence.

## Design

- Keep existing Ansible startup, revision, health, readiness, TLS-route, and broker-isolation checks as the deployment authority.
- Add one small standalone Python script only for signed Onclave requests, because Ansible `uri` does not implement the existing RFC 9421 Ed25519 contract.
- Validate SearXNG directly with Ansible `uri`; do not add a validator framework or SearXNG client.
- The signed Onclave check and SearXNG search-handler check run once. Existing startup retries remain only on the readiness and TLS-route checks they already govern.
- Use HTTPS with normal certificate verification, redirects disabled, inherited proxy settings disabled, and fixed request timeouts used only as failure bounds.
- Use the established controller key at `~/.ssh/id_ed25519`. Do not add a new key-selection setting or search for alternative keys.
- Do not print URLs, hosts, key IDs, signatures, response bodies, inventory, or credentials.

## Churn Controls

- One signed-check script, not a reusable validation framework or profile system.
- One owner per assertion: existing Ansible tasks own health/readiness/revision; the script owns signed Onclave reads; SearXNG role tasks own SearXNG.
- No new dependency, public command, environment setting, endpoint abstraction, fixture service, or compatibility layer.
- No source-inspection tests that enforce implementation wording.
- Do not rerun a successful gate unless relevant inputs changed or a failure identifies a new hypothesis.
- Do not expand cleanup beyond the named runner, runbook, references, scratch files, and old plan criteria.

## Work

- [x] **1. Remove the invalid acceptance machinery.** In `C:/Projects/Personal/onclave`, delete:
  - `scripts/onclave-v2-acceptance.ts`
  - `docs/extensions/onclave-comms/v2-manual-acceptance.md`

  Remove active references to those files from `README.md`, `docs/extensions/onclave-comms/v2-status.md`, and `docs/extensions/onclave-comms/v2-implementation-plan.md`. Preserve deterministic service, broker, signature, route, delivery, and Pi adapter unit tests. Do not modify or remove the separate `extensions/onclave-comms` subsystem.

  Delete only these ignored investigation files:
  - `C:/Users/mglenn/.dotfiles/onclave/.tmp/run-bws-acceptance.ts`
  - `C:/Users/mglenn/.dotfiles/onclave/.tmp/debug-onclave-v2-acceptance.ts`
  - `C:/Users/mglenn/.dotfiles/.tmp/migrate-onclave-api-to-bws.py`

  Update `.specs/onclave-https-agent-transport/plan.md` so its deployment acceptance ends at direct API, revision, broker, readiness, and network-isolation checks. Remove Pi sessions, simulated agents, `/yt`, circuit probes, restart timing, and redelivery timing from that plan.

- [x] **2. Add one signed Onclave API check.** Add `scripts/check-onclave-api.py` in `homelab-infra`. It accepts the HTTPS base URL and signing-key path, performs no discovery, and makes exactly these requests:
  1. Signed `GET /api/v1/auth/whoami` -> 200; `key_id` equals the fingerprint derived from the supplied key.
  2. Signed `POST /api/v1/agents/rpc` with `{"op":"list_agents"}` -> 200; `ok == true`; `agents` is an array.
  3. Signed `GET /api/v1/content?limit=1` -> 200; integer `total`; array `items`; `limit == 1`; integer `offset`.
  4. Signed `POST /api/v1/search` with `{"query":"deployment validation","limit":1}` -> 200; echoed query matches; `results` is an array; integer `total == len(results)`. Zero results are valid.

  These checks prove the deployed signing identity, agent RPC route, PostgreSQL-backed content reads, Ollama embedding request, and PostgreSQL vector search without creating application state. Health, readiness, revision, and broker connection remain in the existing role checks and are not repeated.

  Add `tests/test_check_onclave_api.py` using `unittest` and mocked HTTP calls. Cover one fixed RFC 9421 signing vector, URL/redirect/proxy rejection, the four response contracts, and redacted failure output. Do not add source-inspection tests, subprocess servers, sleeps, retries, profile abstractions, or generic validation frameworks.

- [x] **3. Replace weak SearXNG checks with standard endpoint checks.** In `infra/ansible/roles/searxng_onramp`:
  - enable `json` in the managed `search.formats` list;
  - replace the loopback root-page startup check with `GET /healthz` -> 200 and body `OK`, retaining its existing startup retry boundary;
  - replace the HTTPS root-page startup check with `GET /config` and assert the configured instance name, `safe_search == 1`, a non-empty version, and non-empty `engines` and `categories` arrays, retaining its existing startup retry boundary;
  - after startup succeeds, call `GET /search?format=json` without `q` once and assert 400 JSON with `error == "No query"`.

  The missing-query request validates the JSON search handler without calling external engines. External result count, order, quality, and engine availability are not deployment gates.

- [x] **4. Wire the signed check into the existing Onclave role.** After the current Onclave startup and HTTPS checks pass, run `scripts/check-onclave-api.py` once on the Ansible controller with `delegate_to: localhost`, `become: false`, and `no_log: true`. Pass the inventory-derived HTTPS URL and the fixed controller path `~/.ssh/id_ed25519`; the script expands that exact path and does not search for alternatives. Use an Ansible `block`/`rescue`: keep command details suppressed and emit only `signed Onclave API validation failed` from the rescue. Do not add a public `just` recipe, environment knob, retry, second apply, or client workflow.

## Verification

### Onclave cleanup

- Run `just check` once after all Onclave cleanup edits.
- Pass: checks succeed and `git grep` finds no active reference to either deleted file.

### Homelab implementation

- `scripts/python.sh -m unittest tests.test_check_onclave_api`
- Focused `tests.test_ansible_safety` cases for the two roles.
- Focused Ansible syntax and lint checks for `onclave-onramp.yml` and `searxng-onramp.yml` through existing container tooling.
- One approved targeted deployment of `onclave_onramp` and one of `searxng_onramp`; each new check runs once.
- Exactly one final `just validate` after implementation and live checks finish.

## Acceptance

- Added deployment checks are read-only and create no registry records, queues, content, objects, or jobs.
- The signed validator and post-startup SearXNG search check have no Pi, Claude, `/yt`, circuit-probe, model, session, AMQP-client, sleep, poll, or retry dependency. Existing bounded startup retries remain unchanged.
- Onclave validation proves the deployed signing identity, agent RPC route, content read path, embedding path, and vector-search path.
- Existing Onclave role checks continue to prove revision, readiness, broker connection, TLS routing, and RabbitMQ isolation.
- SearXNG validation proves liveness, TLS routing, managed configuration, and its JSON search handler without external-engine dependence.

## Result

- Onclave cleanup passed `just check`; active references to the deleted acceptance files are gone.
- Focused Python, role safety, Ansible syntax, and Ansible lint checks passed.
- Targeted Onclave and SearXNG deployments passed with the new checks.
- Final `just validate` passed.

## Non-goals

- Live agent delivery, lease expiry, redelivery, dead-lettering, delegation, replies, or budgets. Existing deterministic component and broker integration tests own these contracts.
- Pi, Claude, `/yt`, circuit-probe, or cached-backfill operation.
- Performance, monitoring, or external SearXNG result quality.

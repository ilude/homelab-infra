---
created: 2026-08-13
updated: 2026-08-13
status: in_progress
owners:
  - onclave
  - homelab-infra
  - dotfiles
---

# Plan: Move Onclave Agent Transport to Signed HTTPS

## Outcome

Pi agents use the existing Onclave HTTPS listener as their only remote transport, authenticated with the existing RFC 9421 Ed25519 signature contract. RabbitMQ remains an internal Compose dependency with no host, LAN, DNS, firewall, SSH-tunnel, or client-facing surface.

## Current State and Safety Boundary

The live unified Onclave service is healthy at the deployed pin. RabbitMQ binds only to host loopback, LAN access to TCP 5672 is blocked, and inbound UFW rules are removed. A temporary workstation SSH tunnel (loopback 5672 -> host loopback 5672) keeps the current AMQP adapter working; it is containment and is removed in task 3.

Live target: the unified Onclave deployment on `onramp_host` via `scripts/apply-service.sh onclave_onramp`. Stop if the signed HTTPS API rejects the existing operator identity or `/health`/`/ready` regress. Rollback: restore the previous immutable image pin; never re-expose 5672/15672. This change mutates no PostgreSQL/S3/RabbitMQ data; no data inventory re-verification is required.

## Design Decisions (resolved now, not during implementation)

- **Four HTTPS operations only**, added to the existing vault route table as non-public routes:
  1. `POST /api/v1/agents/rpc` -- body is an existing `RpcRequest`; handled by the existing `parseRpcRequest` + `handleRpcRequest` unchanged (register, heartbeat, unregister, list_agents, conversation_status, record_exchange).
  2. `POST /api/v1/agents/messages` -- body is a complete `Envelope`; validated by `parseEnvelope` and published to the existing agents exchange.
  3. `GET /api/v1/agents/messages/next?agent_id=&wait_ms=` -- bounded long poll (cap ~25s) returning at most one envelope plus a `delivery_id`, or 204.
  4. `POST /api/v1/agents/messages/{delivery_id}` -- body `{"disposition":"ack"|"reject"}`.
- **Delivery ownership stays in RabbitMQ.** The core consumes each agent queue with manual acks and keeps an in-memory `delivery_id -> broker delivery tag` map with a timeout. Timeout -> `nack(requeue=true)`; client reject -> `nack(requeue=false)` (existing DLX policy); core/channel exit -> broker requeues automatically. No new durable lease store. Existing adapter dedup (`SeenIds`) remains the duplicate boundary.
- **No protocol version bump, no envelope changes.** Extend `isAgentCard` to accept `transport: "https"` alongside `"amqp"`; everything else in `packages/envelope` is reused as-is.
- **Signing identity**: the adapter signs with the operator's existing `~/.ssh/id_ed25519` (already in the server's `authorized_keys`), loaded via `node:crypto` `createPrivateKey` (OpenSSH format, unencrypted), key id = SHA256 fingerprint, matching the Python `signing.py` contract. Encrypted or missing keys fail with a clear error. Verify this parse works as the first implementation step; if Node cannot parse the key, decide between PKCS8 conversion guidance and a small parser before continuing.
- **Key-to-agent binding** is one check: registration records the verified key id; later `heartbeat`/`unregister`/`messages/next`/disposition calls for that `agent_id` must present the same key id. No richer identity model.
- **Excluded**: the `extensions/onclave-comms` WSS/hub stack stays untouched and must not be revived as a transport; no new listener, bearer tokens, compatibility AMQP client path, or second deployment.

## Execution Plan

- [x] **1. Add the HTTPS agent routes and convert the Pi adapter (`C:/Projects/Personal/onclave`).** Server: implement the four routes above in `services/core/src/vault/{http.ts,routes.ts}` (or a small `agent-routes.ts`), bridging to the existing broker channel in `services/core/src/service.ts`; reuse `handleRpcRequest`, `parseEnvelope`, registry, budgets, DLX, and audit unchanged. Adapter: replace the transport layer of `extensions/onclave-pi` (connection.ts, rpc-client.ts, BWS URL loading, `amqplib`) with a signed HTTPS client (RPC call, publish, long-poll loop, disposition) while keeping `delivery.ts`, correlation, policy, framing, tools, footer status, and `agent_end` reply logic unchanged; config becomes `ONCLAVE_API_BASE` (env or `--onclave-url` flag repointed to the API base). Remove the `rabbitmq` host `ports` block from `deploy/app/onclave/compose.yaml`. Acceptance: unsigned/stale/wrong-key requests and cross-agent key reuse fail closed; a signed adapter registers, lists agents, sends request/inform/delegation envelopes, receives and acks them, correlated replies arrive, an unacked delivery redelivers after timeout, reject dead-letters; adapter has no `amqplib` dependency. Verification: focused Vitest for the four routes and the adapter transport, one in-process two-adapter integration test, `pnpm typecheck`, `pnpm test`, `python scripts/public-safety.py`, `just check`, smoke test; commit and push; CI publishes the image.

- [x] **2. Deploy (`C:/Projects/Personal/homelab-infra`, after task 1 publishes).** Drop the role's RabbitMQ host-port override logic in `infra/ansible/roles/onclave_onramp` (the app definition no longer publishes ports), assert in `tests/test_ansible_safety.py` that the rendered definition maps no host ports for 5672/15672, update pins via `.tmp/bump-onclave-pins.py <sha> <digest>`, then run `scripts/apply-service.sh onclave_onramp`. Acceptance: apply succeeds; `/health` shows the new sha with broker connected; `/ready` green; host has no listener on 5672/15672 on any address and no UFW rules for them; LAN TCP probes to both ports fail. Verification: focused role test, ansible-lint, syntax check, `git diff --check`, direct host listener/firewall checks; commit and push.

- [ ] **3. Cut Pi over and remove containment (`C:/Users/mglenn/.dotfiles`, after task 2).** Update the Onclave submodule pin to the task-1 commit; set `ONCLAVE_API_BASE`; delete `ONCLAVE_AMQP_ENDPOINT`/`ONCLAVE_AMQP_URL` from `.env`, BWS RabbitMQ credential resolution from bootstrap/`scripts/pi-doctor`, and AMQP references from the loader, affected tests, and `pi/README.md`; stop the SSH tunnel process and delete its PID/known-hosts scratch artifacts. Leave unrelated dotfiles changes unstaged. Acceptance: a fresh Pi session shows Onclave connected with no local 5672 listener and no ssh tunnel process; two live Pi sessions see each other via `onclave_agents` and complete a send/reply and one delegation round trip; restarting one session during an outstanding delivery redelivers without loss; `/yt` and circuit probe still pass. Verification: adapter/setup/bootstrap focused tests, `make check-pi-extensions`, live two-agent check, `git diff --check`, scoped commit; then exactly one final `just validate` in `homelab-infra`.

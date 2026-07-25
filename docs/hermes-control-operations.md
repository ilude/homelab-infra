# Hermes Control Operations

Hermes Control is an optional companion stack on the existing Hermes guest. It is never a separate infrastructure control plane.

## Preconditions

Set `hermes_control_enabled: true` only in private inventory after setting a reviewed immutable `HERMES_CONTROL_SOURCE_REF`, a read-only source URL, a private Control hostname, and independently generated API and bridge tokens in `values/.env`. The API is loopback-only; Caddy is the only HTTPS exposure path.

## Five-state verification

After a reviewed `just plan` and explicitly approved `just apply`, verify without printing tokens:

1. `hermes-gateway`, `hermes-control-bridge`, and `hermes-control-api` are active.
2. The Control extension is installed and enabled for the configured Hermes runtime user.
3. Gateway plugin loading is confirmed with `HERMES_PLUGINS_DEBUG=1` and a tool-list check.
4. The bridge accepts an authenticated Unix-socket request.
5. The API `/health` and authenticated `/diagnostics` checks succeed locally and through the private HTTPS hostname.

Also confirm the existing `homelab-infra-operator` remains enabled. Control-task approval does not bypass the operator plugin’s saved-plan, destructive/stateful, redaction, or explicit-apply safeguards.

## Rotation and rollback

Rotate API and bridge tokens independently in private values, then apply through the normal reviewed workflow. For a source rollback, change only `HERMES_CONTROL_SOURCE_REF` to the previously reviewed immutable commit, run a new plan, and apply only after approval. Do not use floating branches, `git pull`, or manual guest changes.

If the API or bridge fails, inspect redacted service status/journal output, correct the reviewed configuration or pin, then rerun the normal workflow. Do not expose port 8787, bypass Caddy, or copy secret environment files into diagnostics.

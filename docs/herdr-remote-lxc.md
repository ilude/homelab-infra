# Herdr remote LXC contract

This document defines the public-safe contract for running Herdr in a Debian 13 Proxmox LXC and using it to reach a rootless Podman workload through Docker SSH transport. It is an operator boundary, not a live deployment record.

## Ownership and operator boundary

- `homelab-infra` owns the LXC, SSH hardening, Herdr and Pi installation, and the onramp relay boundary.
- BWS owns the service selection, hostnames, addresses, operator login public keys, source CIDRs, and runtime configuration families.
- The ignored `values/` repository does not store Herdr site configuration, rendered tfvars, inventory, DNS records, SSH keys, or OpenTofu state.
- Public examples use `herdr.example.internal` and `192.0.2.0/24` only.

The LXC is unprivileged with nesting disabled. It has a non-root operator with a persistent home. Password SSH and root SSH are disabled, and the host firewall allows only the reviewed private source CIDRs. Routine access is direct SSH to Herdr:

```text
ssh herdr@herdr.example.internal
```

This is the operator login boundary. Proxmox host SSH and `pct exec` are reserved for lifecycle readiness, bootstrap, recovery, and host-boundary work. They are not the normal operator path.

## Herdr release, Pi, and integration

The pinned official binary is fetched from:

```text
https://github.com/herdrdev/herdr/releases/download/v0.8.2/herdr-linux-x86_64
```

Its required SHA256 is:

```text
976150a14d490c94b243ea2e1a7eb2dfb67f12e36b182db90936f6728e6aecf4
```

The binary is verified before activation. No mutable installer or unverified download is an acceptable substitute.

Pi `0.84.1` is installed inside the Herdr LXC as the non-root Herdr operator with pnpm only. The official integration is bundled with Herdr and is also installed inside the LXC as that operator:

```bash
export PI_CODING_AGENT_DIR="$HOME/.pi/agent"
pnpm add --global @earendil-works/pi-coding-agent@0.84.1
herdr integration install pi
```

The extension is installed at:

```text
PI_CODING_AGENT_DIR/extensions/herdr-agent-state.ts
```

The workstation does not install Pi or the Herdr integration for this contract. Herdr does not receive a Bitwarden access key, OAuth material, or another controller credential.

## Remote Docker transport

The operator uses the Herdr-local Docker CLI context and SSH alias `herdr-onramp`:

```bash
docker context create herdr-onramp --docker "host=ssh://herdr-onramp"
docker --context herdr-onramp version
```

Both names are explicit contract values. The Herdr SSH config resolves the alias to the approved onramp host and accepts only the verified host keys. Docker sends exactly:

```text
docker system dial-stdio
```

The onramp deploy account has a separate restricted public-key entry. That entry forces the root-owned relay, rejects every other command, disables shell and forwarding capabilities, and connects standard input/output to the rootless Podman compatibility socket:

```sh
if [ "${SSH_ORIGINAL_COMMAND-}" != "docker system dial-stdio" ]; then
    exit 1
fi

exec /usr/bin/socat STDIO "UNIX-CONNECT:/run/user/<uid>/podman/podman.sock"
```

The flow is:

1. The Herdr operator selects the `herdr-onramp` context.
2. Herdr SSH resolves the `herdr-onramp` alias with strict host-key checking.
3. Docker sends the fixed stdio command to the onramp deploy account.
4. The forced root-owned relay rejects any other command.
5. `socat` connects the stream to the rootless Podman Unix socket.
6. Rootless Podman serves the Docker-compatible protocol without a TCP listener or Docker daemon.

Do not replace this stream with a TCP API, a broad shell key, a privileged container, or LXC nesting.

## Key and trust flow

- BWS supplies the operator login public keys. They are installed only on the non-root Herdr account.
- Herdr generates a separate ed25519 transport key pair in the operator's persistent home.
- The transport private key remains only in the Herdr LXC. It is not stored in BWS, copied to the workstation, copied to the controller, or copied to onramp.
- Ansible passes only the generated public half to the onramp role, which writes a separate forced-command `authorized_keys` file for the onramp deploy account.
- Herdr stores the persistent transport private key at `~/.ssh/id_ed25519_herdr_onramp`.
- Herdr stores the persistent known_hosts file at `~/.ssh/known_hosts.herdr-onramp` and the SSH config at `~/.ssh/config`.
- The Herdr known_hosts file is built only from the verified onramp host keys. The controller's return-handoff known_hosts file is ephemeral and is not the Herdr trust store.
- `ssh-keyscan`, ambient global known_hosts files, changed host keys, and private-key logging are not acceptable trust or recovery paths.

The transport key is not an operator shell credential. It cannot obtain an interactive shell, agent forwarding, X11 forwarding, TCP forwarding, or a second command. The onramp deploy account remains a separate host-management boundary.

## Persistent state and hardening

The Herdr home persists across LXC restarts and package updates. The binary is installed separately from that home. Herdr remains:

- Debian 13 and x86_64.
- Unprivileged with no nesting.
- Non-root for normal operation.
- Key-only for SSH, with password authentication and root login disabled.
- Restricted to explicit private source CIDRs.
- Strict about host-key verification.

The first deployment is a new service and has no replacement backup requirement. Later changes to an existing Herdr home, transport key, or onramp key set require a current recovery copy and reviewed rollback boundary. Recovery copies remain in an approved private location and never in tracked files.

## Explicit exclusions

This contract does not include:

- A TCP Docker or Podman API.
- A Herdr-managed Docker daemon.
- A Bitwarden Secrets Manager access key on Herdr or the managed host.
- OAuth token acquisition, browser login, refresh, or callback handling.
- A privileged or nested LXC.
- A change to `searxng_onramp`.
- A second site-configuration source under `scaffold/` or `values/`.

## Operator smoke sequence

After a reviewed deployment, check:

1. Direct SSH to Herdr succeeds as the non-root operator with strict host-key checking.
2. `herdr --version` and the installed binary match the pinned release and SHA256.
3. The Herdr home and transport private key have the expected owner and mode and survive a restart.
4. Pi `0.84.1`, pnpm, the integration, and the exact extension path are present inside Herdr.
5. The `herdr-onramp` context reaches rootless Podman.
6. A non-exact forced command and an interactive shell are rejected.
7. The Podman socket is Unix-only, no Docker daemon or TCP API is present, and the LXC remains unprivileged with no nesting.
8. No `searxng_onramp` setting changed.

Keep output redacted. Do not record real hostnames, addresses, public keys, tokens, or credentials in tracked documentation or plan evidence.

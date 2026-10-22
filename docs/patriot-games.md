# Games on an existing Docker host

`patriot_games` deploys Broccoli Project Zomboid, Dozzle and itzg RCON Web Admin
onto an existing Docker VM. It does not provision a VM or use `onramp_host`.
Application deployment currently belongs here; a future application platform can
consume the same service configuration without moving host ownership.

Add `patriot_games` to `HOMELAB_SETTINGS.services`. In the BWS
`HOMELAB_ANSIBLE_INVENTORY` family, merge this separate inventory group and its
variables (public examples only):

```yaml
all:
  children:
    patriot_docker:
      hosts:
        patriot_docker_vm:
          ansible_host: docker.example.internal
          ansible_user: operator
      vars:
        zomboid_server_branch: "" # Explicit Steam default public; unstable or legacy41 are alternatives.
        zomboid_image: indifferentbroccoli/projectzomboid-server-docker:latest@sha256:REPLACE_WITH_DIGEST
        zomboid_web_image: itzg/rcon:latest@sha256:REPLACE_WITH_DIGEST
        patriot_dozzle_image: amir20/dozzle:latest@sha256:REPLACE_WITH_DIGEST
        patriot_games_legacy_tls_site: "*.old.example.internal"
        patriot_dozzle_server_name: logs.example.internal
        zomboid_admin_server_name: game-admin.example.internal
```

The host must already have Docker Compose 2.30+ (raw env-file support), Python 3,
passwordless sudo, the configured external Docker network, and the existing Caddy
container and file. Defaults are in the role. No Docker/OS reinstall or old-stack
Compose invocation occurs. The source Caddyfile remains authoritative for old
routes. A candidate containing only the new managed block is validated inside the
existing Caddy container, then written **in place** to preserve the single-file
bind mount's inode, followed by graceful reload. Caddy is not restarted. The new
sites use the BWS `HOMELAB_ENV.CF_DNS_API_TOKEN` for DNS-01 and keep the rendered
Caddyfile private (0600). Caddy 2.10.2 overrides per-site DNS providers when a
global `acme_dns` directive is present. The helper therefore moves the existing
exact `acme_dns cloudflare {$CF_DNS_API_TOKEN}` directive into an explicit `tls`
block in `patriot_games_legacy_tls_site`, the existing legacy wildcard site. Its
original token placeholder, email and routes remain unchanged; only the new sites
use the BWS token. Subsequent deployments leave the already-scoped legacy block
unchanged. This requires an operator-approved shared Caddy configuration change
before first rollout, not a shared credential replacement or Caddy restart.

Store unique generated credentials as standalone BWS runtime keys:

- `ZOMBOID_ADMIN_PASSWORD`: game administrator password.
- `ZOMBOID_JOIN_PASSWORD`: required nonempty player join password, separate from
  player-account, administrator and RCON passwords.
- `ZOMBOID_RCON_PASSWORD`: internal RCON credential.
- `ZOMBOID_WEB_PASSWORD`: RCON Web Admin initial administrator password.
- `PATRIOT_DOZZLE_USERS`: single-line JSON representation of Dozzle's `users.yml`,
  with a bcrypt password hash from Dozzle's supported `generate` command or bcrypt.
  JSON is accepted as YAML and avoids multiline Docker runtime-env values. The
  plaintext Dozzle password can be retained in BWS separately for operator retrieval.

Secrets are loaded through the scoped `patriot_games` runtime profile, never from
tracked inventory or `values/`. Game/web credentials must be single-line.
The join and RCON passwords are rendered into the complete managed server `.ini`.
A password change follows the same save/stop/render/start path as other server
configuration changes. Secret contents and comparison output are hidden. The
container has no supported environment variable for the player join password.
RCON Web Admin's credentials initialize its persisted database; changing its BWS password
later does not necessarily reset an existing database user. Use its account UI for
normal changes and keep BWS synchronized.

Deploy only this service:

```bash
bash scripts/apply-service.sh patriot_games
```

Use the existing targeted Technitium DNS playbook when adding its two LAN DNS A
records to `HOMELAB_DNS_RECORDS`. No router forwarding is managed here. UDP 16261
and 16262 are the only published game ports. RCON TCP 27015 stays on the dedicated
game network. Both web interfaces stay internal to Docker behind HTTPS Caddy.
For a player-facing hostname, use a public DNS-only A record pointing to the
router's public IPv4 address and a LAN A override in `HOMELAB_DNS_RECORDS` pointing
to the Docker host. Cloudflare's normal HTTP proxy does not carry the game UDP
traffic. A public A record set this way is static; update it if the WAN address
changes. Players use the hostname with game port 16261; TXT-based port discovery
is not configured.
RCON Web Admin uses `wss://game-admin.example.internal/ws`, routed to its separate
4327 websocket listener; its UI is routed to 4326. Its generic console is not a
Zomboid-specific panel. Verify an authenticated command against the live game
before claiming compatibility.

Dozzle uses simple authentication with actions and shell disabled. It mounts the
Docker socket to read host-wide logs. The read-only socket mount is **not** an API
write-access boundary; Dozzle and its authenticated users remain trusted.

Game files and world/config data are separate mounts under `/srv/patriot-games`.
Defaults are 8 GiB maximum JVM heap and 16 players, with no mods. The Steam branch
must be explicit; an empty string does not send a beta flag. `UPDATE_ON_START`
defaults false to avoid changing game versions on routine restarts; first launch
still installs missing game files. To update the game, deliberately enable that
setting for a targeted deployment, then disable it again. Image references are
BWS digest pins; this service has no managed `just update` discovery support yet.

## Optional Playit relay

To add the Playit agent, set `patriot_playit_image` in the BWS inventory group to
a digest-pinned `ghcr.io/playit-cloud/playit-agent:<tag>@sha256:<digest>` reference
and store its agent key as `PATRIOT_PLAYIT_SECRET_KEY` in BWS. The runtime key
is optional for deployments without Playit; enabling the image requires it.
Ansible renders a private `playit.env` without logging credentials.

The agent runs persistently with host networking, matching the upstream Docker
instructions. Configure its provider-side Zomboid/UDP tunnels to reach
`127.0.0.1:16261` and `127.0.0.1:16262`, the game ports already published on
the host. Players use the public address and ports allocated by Playit. An agent
connection does not by itself create tunnels or prove game connectivity. This
does not require a world reset or game restart, change router forwarding, or
disable direct connections. Host networking is not a restricted network boundary;
the agent is a trusted host-network service.

## Complete managed game configuration

The role's version-controlled `server.ini.j2`, `SandboxVars.lua.j2` and
`spawnregions.lua.j2` are the complete configuration authority, based on the
captured deployed baseline, not fresh game defaults. Edit these templates for
future gameplay changes. Remove the retired `patriot_games_world_settings`
inventory mapping when migrating; there is no per-option override mechanism.
All existing spawn choices are retained. The only gameplay changes from the
captured baseline are `MapRemotePlayerVisibility=4` (everyone),
`PlayerSafehouse=true` and `SafehouseAllowRespawn=true`. `AdminSafehouse=false`,
`TrashDeleteAll=false`, all safehouse protection/access/claim rules, and
`MinutesPerPage=0.5` remain unchanged. The baseline also retains the global
skill multiplier of 2 with its global toggle enabled.

Set `patriot_games_server_identity` in the same BWS inventory group. Every key
below must be explicit, including empty optional strings. For an existing server,
copy the values from its actual mounted `.ini`; never generate new identifiers.
This public example is for a new world only, not migration values:

```yaml
patriot_games_server_identity:
  ResetID: 123456789
  ServerPlayerID: "987654321"
  Seed: "example-new-world-seed"
  PublicName: "Private co-op"
  PublicDescription: ""
  ServerWelcomeMessage: "Welcome to our private co-op server."
  DiscordToken: ""
  DiscordChatChannel: ""
  DiscordLogChannel: ""
  DiscordCommandChannel: ""
  WebhookAddress: ""
  server_browser_announced_ip: ""
  BadWordListFile: ""
  GoodWordListFile: ""
```

Keep `patriot_games_server_name` unchanged to retain the existing world and
accounts. The existing `patriot_games_max_players` variable feeds both `.ini`
and `MAX_PLAYERS`; RCON password and the fixed game/RCON ports likewise match
Broccoli's startup environment. Upstream `scripts/start.sh` rewrites those
`.ini` fields on each start, so they must remain aligned with `zomboid.env.j2`.
It does not manage the join password or the rest of the gameplay configuration.

Before initial startup the role creates the owned `server-data/Server` directory
and renders all three files, so first launch does not rely on generated gameplay
defaults. On existing servers it compares configuration first, ignoring generated
comments and whitespace outside Lua strings (and equivalent Lua numeric
formatting). An actual option change stops only Zomboid, allows normal save/quit,
then replaces the complete configuration before Compose starts it again. Comment
rewrites alone do not cause repeated restarts. Runtime/admin edits are not a
second authority and are replaced on the next deployment when they differ.
A regular deployment never deletes a world or resets characters. World
regeneration is a separate, explicitly authorized operation: stop the game,
apply settings, remove only `server-data/Saves/Multiplayer/<SERVER_NAME>`, and
start through the targeted playbook. Keep `server-data/Server/` configuration
and `server-data/db/` account credentials intact. These settings do not require
mods, and starter kits apply only to newly created characters.

SIGTERM in Broccoli's entrypoint invokes RCON `save` followed by `quit`, falling
back to SIGTERM if RCON fails. The configurable grace defaults to 120 seconds for
saving before Docker can force termination. This does not guarantee save success;
verify save/quit behavior when maintaining a populated world. This deployment adds
no backup automation and does not change existing host containers or their restart
policies.

# Remote workstation access

Public-safe operator guidance for Herdr over SSH and Windows PowerShell remoting. This is not an inventory or a deployment script. Workstation setup and reusable launchers belong in the dotfiles repository; homelab-infra owns this access runbook.

## Inventory and credentials

Use a local SSH alias such as `workstation` in commands. Resolve actual destinations from authorized local SSH configuration or the owning BWS configuration family. BWS owns managed live inventory and runtime secrets; do not create a second inventory in `values/`. That private repository remains for excluded backups, artifacts, dumps, and mutable service state.

Keep real usernames, hostnames, domains, SSIDs, addresses, key fingerprints, certificate thumbprints, and credential files out of tracked examples. Private keys remain on their owning client. Never ask the operator to paste a password into chat.

## Herdr: prefer native remote attachment

From the client machine:

```powershell
herdr --remote workstation
```

This uses normal OpenSSH authentication and local SSH configuration, including the selected identity key. Verify SSH access and host trust before diagnosing Herdr. Do not disable host-key verification.

Native remote mode draws the UI locally while the remote server owns panes and agents. It supports local desktop integration such as image clipboard transfer. In contrast, `ssh -t workstation herdr` runs the entire TUI remotely and depends on the SSH terminal rendering path. In the observed Windows connection, that plain-SSH path rendered conspicuously bright tool backgrounds; native remote attachment worked. The exact color failure was not isolated.

Herdr 0.9.5 native remote mode can discover the active managed Windows release even when the SSH shell cannot resolve `herdr` on PATH. Do not hardcode a versioned release path as the normal launcher. A local and remote version difference alone is not permission to stop or replace a running server. Decline a replacement prompt unless that interruption is explicitly authorized.

### New Windows Terminal tab from inside Herdr

A child terminal can inherit the current Herdr context and reject attachment as nested. Clear that context only in the new process, not in the active agent's shell:

```powershell
$client = (Get-Command herdr -CommandType Application | Select-Object -First 1).Source
$command = 'Get-ChildItem Env:HERDR* | ForEach-Object { Remove-Item -LiteralPath (''Env:'' + $_.Name) }; & ''' + $client.Replace("'", "''") + ''' --remote workstation'
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
wt.exe -w 0 new-tab --title 'Remote Herdr' pwsh.exe -NoExit -EncodedCommand $encoded
```

Replace `workstation` with the authorized SSH alias. This starts a separate local client, not another server inside the current pane. If SSH exits and leaves a local prompt, a subsequent bare `herdr` command is local; it does not reconnect remotely.

Reference: [Herdr 0.9.5 remote attachment documentation](https://github.com/herdrdev/herdr/blob/v0.9.5/docs/next/website/src/content/docs/persistence-remote.mdx).

## PowerShell remoting is a separate transport

WinRM credentials and firewall rules do not enable SSH or authenticate Herdr. For Windows domain members, prefer hostname-based Kerberos where available. Local-account remoting can use an explicit `PSCredential` under the machine's existing authentication policy.

For an operator-approved saved credential on Windows:

```powershell
# Run interactively on the connecting client. Enter a password, not a Hello PIN.
$credential = Get-Credential
$credential | Export-Clixml "$env:USERPROFILE\.workstation-winrm.credential.xml"

# Later, on that same client under the same Windows user:
$credential = Import-Clixml "$env:USERPROFILE\.workstation-winrm.credential.xml"
Invoke-Command -ComputerName workstation.example.internal -Credential $credential -ScriptBlock {
    hostname
    whoami
}
```

Windows DPAPI protects the exported password for that Windows user on that client machine. This is an encrypted password credential, not public-key authentication. Processes running as that user can use it. Keep the file outside repositories and do not print its contents. A credential in an interactive shell variable is not automatically available to a separate agent tool process.

## Network-access intent

The intended policy permits trusted home/work access and authorized Tailscale access, including while the physical connection is public Wi-Fi. Direct public-network WinRM access should remain blocked.

- Inspect existing effective firewall rules and listeners before changing them. Preserve work-managed Group Policy rules.
- Mark only a confirmed trusted home connection Private. A Domain/Private allow rule also allows other connections classified Private; it is not a strict home/work allowlist.
- Scope a Tailscale exception to the Tailscale interface, not all Public interfaces. Tailnet identity and ACLs still determine eligible peers. Devices in different tailnets need an authorized sharing or routing arrangement to test this path.
- Account for both IPv4 and IPv6 and every WinRM listener. Besides 5985/5986, compatibility listeners can expose WinRM on 80/443. Do not block all web traffic or remove managed listeners as a shortcut.
- App-container firewall rules can have package filters even when their program and port fields show `Any`. Inspect the full filters before interpreting them as unrestricted access.

These are operational constraints, not proof that a particular host is configured correctly. A firewall allow rule alone does not establish reachability or authentication.

## Observed verification boundary

During the Windows workstation session that motivated this runbook:

- Native Herdr remote attachment with an existing Ed25519 SSH identity succeeded, confirmed by the operator.
- Authenticated WinRM commands to a peer succeeded using a locally saved credential.
- Reverse LAN `Test-WSMan` to the workstation responded. This did not verify authenticated inbound command execution.
- Tailscale connectivity to that workstation was not established from the peer; the machines were on different tailnets, and the peer also reported an unhealthy Tailscale state.
- Work-network access and direct public-Wi-Fi blocking, including compatibility listeners, were not tested.

Do not promote these partial checks into a claim of complete remote-access or firewall acceptance. Future checks should target the requested path without changing unrelated services.

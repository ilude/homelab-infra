# Herdr remote context

This role installs a strict SSH configuration and a persistent known_hosts file
whose keys come only from the verified onramp VM handoff. It then creates the
Docker CLI context at `ssh://herdr-onramp`; Docker invokes the fixed
`docker system dial-stdio` command accepted by the onramp relay.

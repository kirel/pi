# Bare-metal Hermes

This role manages the runtime envelope around Daniel's trusted bare-metal
Hermes on the Hetzner VPS. The personal `config.yaml`, direct MCP entries, and
1Password-backed secrets remain user-managed.

Managed here:

- initial Hermes bootstrap and read-only update checks
- managed `.env` block and user systemd integration
- dashboard and Tailscale Serve exposure
- host Caddy custom binary with the Regfish DNS provider
- `*.hermes.kirelabs.org` service publishing through `hermes-service`
- the shared Ansible-owned `caddy-proxy` skill

Deploy only this runtime envelope:

```bash
uv run ansible-playbook setup.yml --tags hermes-baremetal --limit ubuntu-8gb-fsn1-1
```

Hermes upgrades are deliberately not performed by the role. Check and update
interactively over SSH so backups and migrations remain visible:

```bash
hermes update --check
hermes update --backup
```

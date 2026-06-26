# Hermes Docker

This role runs one isolated Hermes Docker agent per configured agent name. With `hermes_docker_agent_caddy_enabled: true`, each agent also gets a Caddy reverse proxy in the same Tailscale network namespace.

## Per-agent HTTPS service domains

Each agent Caddy owns a wildcard site:

```text
*.{{ agent }}.kirelabs.org
```

The managed dashboard route is:

```text
https://dashboard.{{ agent }}.kirelabs.org -> 127.0.0.1:9119
```

Agents can publish additional local HTTP services by writing Caddy include snippets into their mounted include directory. The generated `caddy-proxy` skill documents the exact format for the agent.

## Manual DNS setup required

Ansible does **not** currently create the DNS records for these per-agent wildcard domains. They must be created manually wherever clients resolve `kirelabs.org` for Tailnet-only services.

Create wildcard DNS records pointing at the corresponding Tailscale node IPs:

```text
*.multipurpose.kirelabs.org  -> Tailscale IP of hermes-multipurpose
*.marian.kirelabs.org        -> Tailscale IP of hermes-marian
*.anna.kirelabs.org          -> Tailscale IP of hermes-anna
*.sabine.kirelabs.org        -> Tailscale IP of hermes-sabine
```

The target IPs are the Tailscale IPs of the per-agent sidecar nodes, not the Hetzner host IP. You can find them with one of:

```bash
tailscale status | grep hermes-
# or in the Tailscale admin console: Machines -> hermes-<agent>
```

Because Caddy uses DNS-01 via Regfish, these hostnames do not need to be publicly reachable. They only need to resolve for the users/devices that should access them.

## Container DNS and egress firewall

`hermes_docker_dns_servers` is the single resolver list for both Docker Compose `dns:` entries and DNS egress allow-rules in `hermes-docker-firewall.sh.j2`.

Current default priority:

1. `{{ nameserver_pi_ip }}` — local Pi-hole for LAN records and ad-blocking
2. `{{ tailscale_dns_ip }}` — Tailscale/MagicDNS resolver
3. `1.1.1.1` — public internet DNS fallback

If the public fallback is used, local `.lan`/Tailnet-only names and Pi-hole ad-blocking are not available for that query, but normal internet DNS can still resolve.

## DNS-01 certificates

Each `caddy-hermes-<agent>` container receives `REGFISH_TOKEN` via a root-only env file and uses:

```caddyfile
tls {
    dns regfish {env.REGFISH_TOKEN}
}
```

This lets Caddy issue certificates for the wildcard site without opening ports on the public VPS interface.

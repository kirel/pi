# Hermes Docker

This role runs one isolated Hermes Docker agent per configured agent name. With `hermes_docker_agent_caddy_enabled: true`, each agent also gets a Caddy reverse proxy in the same Tailscale network namespace.

## Python runtime

Keep the image's PATH and `/opt/hermes/bin/hermes` launcher intact. The launcher
drops root Docker exec calls to the Hermes user. The derived image only prepends
the persistent Python-tool and npm bin directories; do not override PATH in the generated `.env`.
Supervisor is a Debian package using `/usr/bin/python3`, separate from the
image-owned `/opt/hermes/.venv`. Do not install application packages into that
environment with pip or uv. Independent projects may keep their own venvs.
Login shells can reset PATH through `/etc/profile`; scripts requiring the image's
packages should use `/opt/hermes/.venv/bin/python` explicitly. A bare `python` in
the terminal tool is not proof of which interpreter the gateway uses.

The derived image includes `uv` and `uvx`. Agents can install Python CLIs with
`uv tool install <package>` and run temporary tools with `uvx <package>`.
Installed CLIs live under `/opt/data/.local` and remain available in login shells
and after container recreation. Use `uv init`, `uv add <package>` and `uv run`
inside a project under `/opt/data` for application dependencies, or create a
project venv with `uv venv .venv` and install with `uv pip install --python
.venv/bin/python <package>`. Do not target `/opt/hermes/.venv`.
Global npm installs already use the persistent `/opt/data/npm-global` prefix.

Hermes PM can select a complete dependency generation under `/opt/data/installs`.
It replaces the image's package selection, rather than adding to it. The v0.21.6
Docker image omits `enabled-features.json`, so this Dockerfile uses the upstream
inventory writer to record the extras actually shipped. An existing upstream
inventory is preserved. Remove this build step when the pinned image supplies it.

On 2026-10-11, Marian, Anna and Multipurpose were returned to the image runtime
while stopped; their plugin dependencies were already present in the image.
Their former PM install directories and the previous deployment files are held
under `/opt/hermes-agents/.python-native-20261011` on the data volume. Restore PM
directories only with the affected container stopped and after checking for new
plugin/dependency changes. All six Docker agents received the PATH/Supervisor fix.

## Self-service tools in Docker

Each agent owns a separate Homebrew installation mounted at
`/home/linuxbrew/.linuxbrew` from `<base_dir>/<agent>/brew`. Ansible bootstraps
Homebrew only when absent, as the agent UID; it does not update existing installs.
The common image supplies build prerequisites and uv, while agents install native
CLIs with `brew install`, Python tools with `uv tool install`, and JavaScript tools
with npm. No sudo or runtime apt permission is granted.

Brew bins are appended to PATH, including login shells, preserving the Hermes
launcher and runtime precedence. Auto-update and install-time cleanup are disabled;
`brew update` and targeted `brew upgrade <formula>` are explicit maintenance.
The Brew directory must be included in backups alongside `data`. Container
replacement preserves tools, but base OS changes may require a targeted reinstall.
A Brewfile records requested packages, not exact versions or installed data.

For existing deployments, roll out only image, tool mounts, bootstrap and skill with
`uv run ansible-playbook setup.yml --tags hermes-tools --limit hetzner,ailab_ubuntus`.
Check agent activity before running; image/mount changes recreate the containers.
The regular `hermes-docker` role deployment includes these tasks as well.

The read-only `docker-hermes` skill is mounted in every agent's native skills
folder. It documents installation, project environments, persistent paths and
runtime troubleshooting. It refers app publishing to the existing Caddy skill.

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
*.nele.kirelabs.org          -> Tailscale IP of hermes-nele
*.anna.kirelabs.org          -> Tailscale IP of hermes-anna
*.sabine.kirelabs.org        -> Tailscale IP of hermes-sabine
```

The target IPs are the Tailscale IPs of the per-agent sidecar nodes, not the Hetzner host IP. You can find them with one of:

```bash
tailscale status | grep hermes-
# or in the Tailscale admin console: Machines -> hermes-<agent>
```

### Tailscale health and recovery

Each Tailscale sidecar has a bounded Docker healthcheck. When
`hermes_docker_watchdog_enabled` is true, a host systemd timer also checks the
host daemon and unhealthy sidecars. It restarts `tailscaled.service` when the
host CLI is unresponsive, or stops and starts the complete affected agent stack
when a sidecar is unhealthy. Recoveries have a cooldown to avoid restart loops.

```bash
systemctl status hermes-docker-watchdog.timer
journalctl -u hermes-docker-watchdog.service
docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' ts-hermes-marian
```

The role pins the Tailscale container version instead of relying on a cached
`latest` tag. Container `json-file` logs are also size-limited.

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

## Shared publishing interface

The Ansible-owned `caddy-proxy` skill is shared with the bare-metal Hermes. It
uses the runtime adapter installed as `hermes-service`:

```bash
hermes-service info
hermes-service publish demo 3456
hermes-service publish-static report /opt/data/report
hermes-service list
hermes-service remove demo
```

Docker routes are written into the existing per-agent Caddy include directory
and loaded through the sidecar's local admin API. The agent never receives the
Regfish credential.

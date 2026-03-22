# CLAUDE.md

This file provides guidance to Gemini CLI (and other agents) when working with this repository.

This is an **Ansible-based homelab infrastructure** managing multiple servers and Docker containers.

## ⚠️ IMPORTANT: Deployment Requirements

When adding or modifying services in `group_vars/all/services.yml`, you **MUST** redeploy Caddy and Pi-hole to update proxy rules and DNS:

```bash
# 1. Deploy Caddy (reverse proxy + TLS)
uv run ansible-playbook setup.yml --tags caddy --limit homelab

# 2. Deploy Pi-hole (DNS + DHCP)
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab
```

## Service Inventory (Source of Truth)

All proxied services are defined in:
*   **`group_vars/all/services.yml`**: The central catalog. Each service defines its `target` (host.lan), `http_port`, and `domain` (*.kirelabs.org).

### Service Groups
Services are categorized by the `group` tag in `services.yml`, which is primarily used to organize the **Homepage dashboard UI**:
*   **AI**: LLM tools, Inference, Vision, MCP Gateways
*   **Smart Home**: Home Assistant, Zigbee2MQTT, Frigate
*   **Media**: Jellyfin, Music Assistant, Immich
*   **Monitoring**: Uptime Kuma, Glances, Portainer, Langfuse
*   **Productivity**: n8n, Wallabag, Readeck, Linkding
*   **Network**: Pi-hole, Proxmox, DHCP UI

## LLM Service Architecture

This section contains technical constraints not found in the YAML configs.

### LiteLLM Proxy (homelab-nuc)
*   **API:** `https://litellm.kirelabs.org`
*   **Admin UI:** `https://litellm-ui.kirelabs.org`
*   **Troubleshooting:** If `/health/readiness` fails with "Not connected to the query engine", run `docker restart litellm-proxy-container` to trigger Prisma migrations.

### LLM Inference (ailab-ubuntu)
*   **Ollama:** `http://ailab-ubuntu.lan:11434`
*   **LlamaSwap:** `http://ailab-ubuntu.lan:8080` (managed by LiteLLM)
*   **Context Limits (RTX 3090 24GB):**
    *   **LlamaSwap:** Success up to 92,375 tokens (~22.4GB VRAM).
    *   **Ollama (Qwen3-VL):** 128,256 tokens (100% GPU optimized, ~25GB VRAM).

## How Local DNS & SSL Works

The homelab uses a dual-layer DNS/Proxy approach:

1.  **Hosts:** Every host in `inventory` gets a `<hostname>.lan` A-record via Pi-hole.
2.  **Services:** Every service in `services.yml` gets a `<domain>` CNAME pointing to its `target` host.
3.  **Reverse Proxy:** Caddy on `homelab-nuc` (and other hosts) terminates TLS for `*.kirelabs.org` using **proper Let's Encrypt certificates** (via DNS-01 challenge with Regfish).

**Flow Example:**
`service.kirelabs.org` (CNAME) → `homelab-nuc.lan` (Host) → `Caddy` (Port 443) → `Container` (Port XXXX).

## Common Operations

### Targeted Deployment
```bash
# By Tag
uv run ansible-playbook setup.yml --tags caddy,pihole --limit homelab

# By Role (LLM example)
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus
```

### Diagnostics
```bash
# Check container status
ssh root@homelab-nuc.lan "docker ps"

# Check logs
ssh root@homelab-nuc.lan "docker logs -f <container_name>"

# Test service health
curl -I https://<service>.kirelabs.org/health
```

## Inventory Reference
*   `nameserver-pi` (192.168.50.4): SSH `pi`
*   `homelab-nuc` (192.168.50.5): SSH `root`
*   `ailab-ubuntu` (192.168.50.10): SSH `daniel`
*   `ailab-proxmox` (192.168.50.9): SSH `root`

# AGENTS.md

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
*   **AI**: Open WebUI, LiteLLM, Phoenix, LlamaSwap, ComfyUI, Wan2GP, Speaches, MCP services
*   **Smart Home**: Home Assistant, Zigbee2MQTT, Node-RED, TeslaMate
*   **Media**: Jellyfin, Music Assistant, Immich, Navidrome
*   **Monitoring**: Uptime Kuma, Glances, Dockhand, ChangeDetection, PruneMate
*   **Productivity**: n8n, Readeck, Linkding
*   **Network**: Pi-hole, DHCP lease UI

## LLM Service Architecture

This section contains technical constraints not found in the YAML configs.

### LiteLLM Proxy (homelab-nuc)
*   **API:** `https://litellm.kirelabs.org`
*   **Admin UI:** `https://litellm.kirelabs.org`
*   **Troubleshooting:** If `/health/readiness` fails with "Not connected to the query engine", run `docker restart litellm-proxy-container` to trigger Prisma migrations.

### MCP Server Setup

**Default rule:** MCP servers used by agents/LiteLLM belong in **LiteLLM's MCP config**, not in `group_vars/all/services.yml` and not as new standalone containers.

*   **Primary MCP catalog:** `litellm_mcp_servers` in `roles/llm_tools/defaults/main.yml`.
    *   `roles/llm_tools/templates/litellm_config.yaml.j2` renders LiteLLM's `mcp_servers:` from this catalog.
    *   `roles/llm_tools/templates/Dockerfile.litellm.j2` derives npm and uv preinstall commands from catalog entries with `install.manager: npm` or `install.manager: uv`.
    *   `roles/llm_tools/tasks/main.yml` derives `LITELLM_MCP_STDIO_EXTRA_COMMANDS` from stdio entries whose direct `command` is not in LiteLLM's default allowlist.
    *   Add stdio servers here with `transport`, direct `command`, optional `args`, `env`, `access_groups`, and optional `install` metadata. Prefer direct installed binaries over `npx`/`uvx` so package downloads do not happen during LiteLLM tool discovery.
    *   Add remote HTTP/SSE MCP servers here with `url`, auth settings, and `access_groups`.
    *   Example: `n8n` is intentionally configured here as a stdio server for LiteLLM. Do **not** create a separate `n8n-mcp` container/service just to make it available to agents.
*   **Standalone HTTP MCP containers:** only add these when something outside LiteLLM must connect directly over the network/Tailnet (for example a specific app that requires its own HTTP MCP endpoint). In that case:
    *   Deploy the container in the owning role or `roles/llm_tools/tasks/main.yml` as appropriate.
    *   Add a `group_vars/all/services.yml` entry only if it needs Caddy/DNS exposure.
    *   Then redeploy Caddy and Pi-hole per the deployment requirements above.
    *   Existing example: `google-workspace-mcp` is a standalone streamable HTTP MCP service because clients connect to it directly.
*   **Deployment after MCP changes:** run `uv run ansible-playbook setup.yml --tags llm-tools --limit homelab` for LiteLLM MCP config/image changes. Only run Caddy/Pi-hole deployment if `services.yml` changed.
*   **Verification:** query `https://litellm.kirelabs.org/mcp/` with a valid LiteLLM bearer token and `Accept: application/json, text/event-stream`, or inspect `docker logs litellm-proxy-container` for MCP discovery errors such as stdio allowlist failures or tool-list timeouts.

### LLM Inference (ailab-ubuntu)
*   **LlamaSwap:** `http://ailab-ubuntu.lan:9292` (managed by LiteLLM)
*   **Monitoring:** Use LlamaSwap's built-in log endpoints to inspect upstream model servers:
    *   `curl http://ailab-ubuntu.lan:9292/logs` for recent buffered logs
    *   `curl -Ns http://ailab-ubuntu.lan:9292/logs/stream` for combined live logs
    *   `curl -Ns http://ailab-ubuntu.lan:9292/logs/stream/proxy` for llama-swap proxy logs
    *   `curl -Ns http://ailab-ubuntu.lan:9292/logs/stream/upstream` for logs from loaded upstream model processes
    *   `curl -Ns http://ailab-ubuntu.lan:9292/logs/stream/<model_id>` for one specific model
    *   `curl http://ailab-ubuntu.lan:9292/running` to list currently running models
*   **GPUs (3 active GPUs):**
    *   **GPU 0 (RTX 3090, 24GB):** Running LLM inference (Tensor Parallel) + Speaches STT (Whisper).
    *   **GPU 1 (RTX 3090, 24GB):** Running LLM inference (Tensor Parallel) + Embeddings (`qwen3-embedding`) + Immich ML.
    *   **GPU 2 (RTX 5060 Ti eGPU, 16GB):** Running cloud gaming (Wolf), ComfyUI, and Wan2GP.
*   **VRAM Allocation Constraints:**
    *   `llama.cpp`'s `--fit` auto-sizing **does not work** under Tensor Parallelism (`-sm tensor`).
    *   To prevent Out of Memory (OOM) issues, LLM context sizes (`llama_ctx_size_qwen35_3090` and `llama_ctx_size_qwen27_3090`) must be explicitly set in `group_vars/all/llms.yml`. We preserve ~3.0 GB of headroom on GPU 0 and ~4.5 GB on GPU 1.

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
*   `nameserver-pi` (192.168.50.4): SSH `daniel`
*   `homelab-nuc` (192.168.50.5): SSH `root`
*   `ailab-ubuntu` (192.168.50.10): SSH `daniel` (Bare Metal, migrated from Proxmox VM)

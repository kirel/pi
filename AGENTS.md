# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is an **Ansible-based homelab infrastructure** that manages multiple servers and Docker containers across a home network (192.168.50.0/24). It orchestrates services like Home Assistant, Pi-hole DNS, Caddy reverse proxy, AI/ML tools, and media services.

## ⚠️ IMPORTANT: Service Discovery Requirements

When adding or modifying services in `group_vars/all/services.yml`, you **MUST** redeploy both Caddy and Pi-hole:

```bash
# 1. Deploy Caddy (reverse proxy + TLS)
uv run ansible-playbook setup.yml --tags caddy --limit homelab

# 2. Deploy Pi-hole (DNS + DHCP)
uv run ansible-playbook setup.yml --tags pihole --limit nameserver
```

**Why both?**
- **Caddy** regenerates reverse proxy configurations and TLS certificates
- **Pi-hole** updates DNS records and creates CNAME entries for services

**Order matters:** Deploy Caddy first, then Pi-hole.

**Example workflow when adding a service:**
1. Add service definition to `group_vars/all/services.yml`
2. Deploy the service itself (e.g., `llm-inference`)
3. Deploy Caddy
4. Deploy Pi-hole
5. Test the new `.lan` domain

## LLM Service Architecture

### LlamaSwap Context Limits (RTX 3090 24GB VRAM)

**Tested Maximum Context Sizes:**
- ✅ 80,000-92,375: SUCCESS (22-22.4GB VRAM)
- ✗ 92,500+: FAILED (OOM)

**Final Configuration:**
- **Context:** 92,375 tokens (93% VRAM utilization)
- **Config:** `roles/llm_inference/templates/llamaswap_config.yaml.j2`
- **Command:** `--ctx-size 92375 --flash-attn auto --n-gpu-layers 99`

The homelab runs LLM (Large Language Model) services across multiple hosts with distinct roles:

### LLM-Tools (homelab-nuc, port 192.168.50.5)

**Role:** Orchestration, proxy, and UI
**Tags:** `llm`, `llm-tools`
**Ansible role:** `llm_tools` (see `/home/daniel/code/pi/roles/llm_tools/`)

**Services deployed:**
- **LiteLLM Proxy** - HTTP 4000 (via port 3123 on homelab-nuc)
  - Central API gateway for all LLM models
  - Supports OpenAI SDK, Anthropic, Google, local models
  - Database persistence (PostgreSQL on port 5433)
  - Redis cache (port 6380)
  - Admin UI: https://litellm-ui.lan

- **Open WebUI** - HTTP 3123
  - Chat interface for interacting with LLMs
  - Connects to Ollama via LiteLLM proxy
  - Web UI: https://open-webui.lan

- **MCP-Proxy** - HTTP 8009
  - Model Context Protocol proxy
  - Enables LLMs to interact with external tools/data sources

- **Google Workspace MCP** - HTTP 8014
  - Provides LLM access to Google services
  - Gmail, Calendar, Drive, etc.

### LLM-Observability (homelab-nuc, port 192.168.50.5)

**Role:** Monitoring and observability for LLM systems
**Tags:** `llm`, `llm-observability`
**Ansible role:** `llm_observability` (see `/home/daniel/code/pi/roles/llm_observability/`)

**Services deployed:**
- **Langfuse** - HTTP 3003
  - LLM tracing, analytics, and monitoring
  - Web UI: https://langfuse.lan

### LLM-Inference (ailab-ubuntu, port 192.168.50.10)

**Role:** Local model execution with GPU acceleration
**Tags:** `llm`, `llm-inference`
**Ansible role:** `llm_inference` (see `/home/daniel/code/pi/roles/llm_inference/`)

**Services deployed:**
- **Ollama** - HTTP 11434 (http://ailab-ubuntu.lan:11434)
  - Local LLM inference engine
  - Runs qwen3-vl:8b-thinking-q8_0 model
  - 128K context window, fully GPU-accelerated
  - Accessible via homelab-nuc's LiteLLM proxy

- **ComfyUI** - HTTP 8188 (http://ailab-ubuntu.lan:8188)
  - Node-based UI for stable diffusion
  - GPU-accelerated image generation
  - Web UI: https://comfyui.lan

### Service Dependencies

```
Open WebUI (homelab-nuc) → LiteLLM Proxy (homelab-nuc) → Ollama (ailab-ubuntu)
                                  ↓
                            MCP-Proxy + Google Workspace MCP
                                  ↓
                           Langfuse (homelab-nuc) [observability]
```

### Deployment Commands

```bash
# Deploy all LLM tools to homelab-nuc
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab

# Deploy all LLM inference services to ailab-ubuntu
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus

# Deploy observability (Langfuse)
uv run ansible-playbook setup.yml --tags llm-observability --limit homelab

# Deploy everything LLM-related
uv run ansible-playbook setup.yml --tags llm --limit homelab,ailab_ubuntus
```

### Service Verification

```bash
# Check homelab-nuc LLM services
ssh root@homelab-nuc.lan "docker ps | grep -E 'litellm|open-webui|mcp-proxy'"

# Check ailab-ubuntu inference services
ssh daniel@ailab-ubuntu.lan "docker ps | grep -E 'ollama|comfyui'"

# Test LiteLLM proxy
curl -H "Authorization: Bearer \$LITELLM_MASTER_KEY" http://homelab-nuc.lan:4000/v1/models

# Test Ollama directly
curl http://ailab-ubuntu.lan:11434/api/tags
```

## Architecture Overview

### Infrastructure Topology

**Physical Servers:**
- `nameserver-pi` (192.168.50.4): Pi-hole DNS/DHCP server (Raspberry Pi)
- `homelab-nuc` (192.168.50.5): Main Docker host (Intel NUC) - runs ~30 services
- `ailab-ubuntu` (192.168.50.10): AI/ML server with GPU support

### Core Components

**DNS/DHCP Layer:**
- Pi-hole on `nameserver-pi` provides DNS and DHCP for entire network
- Automatically creates local DNS entries for all inventory hosts (see `roles/pihole/tasks/main.yml:53-65`)
- Secondary Pi-hole runs on `homelab-nuc` for redundancy

**Reverse Proxy:**
- Caddy container on `homelab-nuc` terminates TLS for all services
- Uses internal CA certificate (`caddy_folder/root.crt`) - must be trusted on client devices
- Automatically proxies services defined in `group_vars/all/services.yml`
- Template in `roles/caddy/templates/Caddyfile.j2` generates configuration dynamically

**Service Inventory:**
- `group_vars/all/services.yml` defines all proxied services
- Each service has: `target`, `http_port`, `domain`, `group` (category)
- Services are grouped into: Smart Home, Media, Monitoring, Productivity, AI, Network, Family, NAS, Config

## Common Development Commands

### Testing & Validation
```bash
# Syntax check all playbooks
uv run ansible-playbook setup.yml --syntax-check

# Dry-run with diff (SAFE - no changes applied)
uv run ansible-playbook setup.yml --check --diff

# Test on single host
uv run ansible-playbook setup.yml --check --diff --limit homelab

# Validate specific role
uv run ansible-playbook setup.yml --tags caddy --syntax-check
```

### Deployment Patterns

**Full deployment (all hosts):**
```bash
uv run ansible-playbook setup.yml
```

**Targeted deployment:**
```bash
# Specific host group
uv run ansible-playbook setup.yml --limit homelab
uv run ansible-playbook setup.yml --limit ailab_ubuntus

# Specific service(s) via tags
uv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver
uv run ansible-playbook setup.yml --tags ha  # Home Assistant stack
uv run ansible-playbook setup.yml --tags llm,llm-inference  # AI tools
uv run ansible-playbook setup.yml --tags docker  # Update Docker only
uv run ansible-playbook setup.yml --tags satellite-audio
```

**Service-specific updates:**
```bash
# Force rebuild single service
uv run ansible-playbook setup.yml --tags homepage --limit homelab --extra-vars="force_rebuild=true"

# Update DNS/DHCP only
uv run ansible-playbook setup.yml --tags pihole --limit nameserver

# Update reverse proxy only
uv run ansible-playbook setup.yml --tags caddy --limit homelab
```

### Troubleshooting Commands

**Container management:**
```bash
# Check all containers
ssh root@homelab-nuc.lan "docker ps"

# View logs
ssh root@homelab-nuc.lan "docker logs -f caddy"
ssh root@homelab-nuc.lan "docker logs -f home-assistant"

# Restart specific container
ssh root@homelab-nuc.lan "docker restart caddy"
ssh root@homelab-nuc.lan "docker compose -f /path/to/compose.yml up -d"

# Check resource usage
ssh root@homelab-nuc.lan "docker stats --no-stream"
```

**System diagnostics:**
```bash
# Ansible inventory
cat inventory

# Check DNS resolution
ssh root@homelab-nuc.lan dig ailab-proxmox.lan

# Check Pi-hole status
ssh pi@nameserver-pi.lan "sudo docker ps | grep pihole"
```

### Secrets Management
```bash
# Edit encrypted secrets
uv run ansible-vault edit group_vars/all/secrets.yml

# Run with vault password file
ansible-playbook setup.yml --vault-password-file ~/.vault_pass
```

## Key Code Patterns

### Service Definition Pattern

Most services follow this pattern in `group_vars/all/services.yml`:

```yaml
service_name:
  name: Display Name
  target: hostname.lan  # Resolved by Pi-hole DNS
  http_port: port_number
  domain: custom.domain.lan  # Optional: overrides default pattern
  group: Category  # Smart Home, Media, Monitoring, etc.
  icon: icon_name.png  # Optional: for dashboard
  nodocker: true  # Optional: not a Docker container
  wol: "{{ mac_address }}"  # Optional: Wake-on-LAN
  tls_skip: true  # Optional: bypass TLS for internal services
  try: 360s  # Optional: load balancer retry duration
```

### Docker Compose Pattern

Most roles use `community.docker.docker_compose_v2` with:

```yaml
community.docker.docker_compose_v2:
  project_name: service_name
  state: present
  definition:
    services:
      service_name:
        image: repo/image:tag
        container_name: container_name
        network_mode: host  # Common pattern for performance
        volumes:
          - config_folder:/config
        restart: unless-stopped
        environment:
          TZ: "{{ system_timezone }}"
          PUID: "{{ uid }}"  # Always match file ownership
          PGID: "{{ uid }}"
```

### DNS Integration Pattern

Services that need DNS resolution should configure DNS explicitly:

```yaml
dns:
  - "{{ nameserver_pi_ip }}"   # Primary: Pi-hole
  - "{{ homelab_nuc_ip }}"     # Fallback: host DNS
```

See `roles/caddy/tasks/main.yml:66-68`, `roles/homepage/tasks/main.yml:42-44` for examples.

### Role Structure

Every role follows Ansible best practices:

```
roles/role_name/
├── tasks/main.yml       # Main tasks (REQUIRED)
├── handlers/main.yml    # Handlers for notifies
├── defaults/main.yml    # Default variables (lowest priority)
├── vars/main.yml        # Role-specific variables (high priority)
├── templates/           # Jinja2 templates
└── README.md           # Role documentation
```

## Variable Hierarchy

**Priority (high to low):**
1. `host_vars/hostname/` - Host-specific overrides
2. `group_vars/group_name/` - Group-specific configuration
3. `group_vars/all/` - Global defaults (200+ services in `services.yml`)
4. `roles/role_name/vars/main.yml` - Role internals
5. `roles/role_name/defaults/main.yml` - Fallback values

**Key variable files:**
- `config.yml`: Network config, ports, IP addresses
- `services.yml`: Service inventory (~40 services)
- `dhcp.yml`: Static DHCP leases for all devices
- `secrets.yml`: Encrypted secrets (use ansible-vault)
- `satellites.yml`: Audio satellite configuration

## Critical Files to Understand

1. **`setup.yml`**: Main orchestration playbook - defines host groups and roles
2. **`inventory`**: Host definitions with IPs and SSH users
3. **`group_vars/all/services.yml`**: Service catalog - all proxied services
4. **`group_vars/all/config.yml`**: Network topology and port definitions
5. **`roles/caddy/templates/Caddyfile.j2`**: Dynamic reverse proxy config generator
6. **`roles/pihole/tasks/main.yml:53-65`**: Automatic DNS entry creation from inventory

## Development Workflow

**When modifying the codebase:**

1. **Plan changes** - Identify which host groups and roles are affected
2. **Test syntax** - Run `--syntax-check` first
3. **Dry run** - Use `--check --diff` to see what would change
4. **Limit scope** - Test on specific host with `--limit`
5. **Apply tags** - Use `--tags` to run only necessary roles
6. **Verify** - Check `docker ps`, logs, and service health

**Example workflow:**
```bash
# Step 1: Test syntax
uv run ansible-playbook setup.yml --syntax-check

# Step 2: Dry run on test host
uv run ansible-playbook setup.yml --check --diff --limit homelab

# Step 3: Apply to test host
uv run ansible-playbook setup.yml --limit homelab

# Step 4: Verify
ssh root@homelab-nuc.lan "docker ps | grep <service>"

# Step 5: Roll out to all hosts
uv run ansible-playbook setup.yml
```

## Network Architecture

**Default network:** 192.168.50.0/24
**Router:** 192.168.50.1
**DNS Servers:** 192.168.50.4 (Pi-hole primary), 192.168.50.5 (Pi-hole backup)

**Local DNS (.lan domains):**
All hosts in the Ansible inventory automatically get a `.lan` DNS entry:
- `homelab-nuc.lan` → 192.168.50.5
- `nameserver-pi.lan` → 192.168.50.4
- `ailab-ubuntu.lan` → 192.168.50.10
- etc.

**Port assignments:**
- 80, 443: Caddy reverse proxy (TLS termination)
- 8123: Home Assistant
- 3000-3002: Homepage dashboard, Uptime Kuma, WUD
- 8000-8999: Various apps (Wallabag, Readeck, Linkding, etc.)
- 9002: Portainer

All external access goes through Caddy which proxies to backend services. Internal services use `*.lan` hostnames resolved by Pi-hole (see "How Local DNS Works" below).

## How Local DNS Works

The homelab uses Pi-hole as both DNS and DHCP server to provide automatic local DNS resolution:

### Automatic DNS Entry Creation

1. **Inventory Hosts**: All hosts in the Ansible `inventory` automatically get a `.lan` DNS entry (e.g., `homelab-nuc.lan` → 192.168.50.5)

2. **Service Discovery**: All Docker services defined in `group_vars/all/services.yml` are automatically configured in Pi-hole with CNAME records pointing to the reverse proxy (e.g., `home-assistant.lan` → `homelab-nuc.lan`)

3. **Static DHCP**: Over 65 devices have static DHCP reservations managed in `group_vars/all/dhcp.yml` (Shelly devices, laptops, phones, etc.)

### DNS Flow Example

When you visit `home-assistant.lan`:
1. Client DNS query → Pi-hole (192.168.50.4)
2. Pi-hole checks: Is `home-assistant.lan` in the inventory? → No
3. Pi-hole checks: Is it a service in services.yml? → Yes
4. Pi-hole returns: `home-assistant.lan` → `homelab-nuc.lan` (CNAME)
5. Client connects to `homelab-nuc.lan:443`
6. Caddy terminates TLS and proxies to `home-assistant:8123`
7. Response flows back through Caddy → TLS → Client

### Configuration Files

- **`inventory`**: Defines all hosts and their IPs/SSH users
- **`group_vars/all/services.yml`**: All Docker services and their reverse proxy configuration
- **`group_vars/all/dhcp.yml`**: Static DHCP reservations for 65+ devices
- **`group_vars/all/dns.yml`**: Additional manual DNS entries
- **`group_vars/all/config.yml`**: Network settings and IP ranges
- **`roles/pihole/tasks/main.yml`**: Pi-hole deployment and DNS/DHCP configuration logic

### Benefits

✅ **Zero manual DNS management** - Just add a host to inventory or service to services.yml
✅ **Service discovery** - All services accessible via `*.lan` domains
✅ **Predictable IPs** - Static DHCP ensures consistent addressing
✅ **Centralized management** - One Ansible playbook controls DNS, DHCP, and services
✅ **Automatic certificates** - Caddy gets certificates for all `*.lan` domains

## Dependencies

**Ansible Galaxy roles:**
- `geerlingguy.docker`: Docker installation
- `geerlingguy.pip`: Python package management

**Python dependencies** (managed via `uv`):
- `pyyaml`: YAML parsing
- `docker`: Docker API client

Install with: `uv pip sync && uv run ansible-galaxy install --force-with-deps -r requirements.yml`

## Security Notes

- **Never commit secrets** - Use `group_vars/all/secrets.yml` with ansible-vault
- **Internal CA** - Trust `caddy_folder/root.crt` on all client devices
- **SSH keys** - Public keys configured in Pi imager for initial bootstrap
- **Network isolation** - Services communicate via Docker networks and reverse proxy
- **TLS everywhere** - Caddy provides internal TLS with self-signed certs
- **SSH Users** - Always use the SSH users specified in the `inventory` file for each host. See the "Inventory" section below for the complete list.

## Inventory

The `inventory` file defines all hosts and their SSH users. **When connecting via SSH, always use the username specified in the inventory file for that host.**

**Note:** All hosts in the inventory automatically get a `.lan` DNS entry via Pi-hole. For example, `homelab-nuc` becomes `homelab-nuc.lan`.

**Host Inventory:**
- `nameserver-pi` (192.168.50.4): SSH user = `pi`
- `homelab-nuc` (192.168.50.5): SSH user = `root`
- `ailab-proxmox` (192.168.50.9): SSH user = `root`
- `ailab-ubuntu` (192.168.50.10): SSH user = `daniel`

**Example SSH Commands:**
```bash
# Nameserver (Pi-hole)
ssh pi@nameserver-pi.lan
# or: ssh pi@192.168.50.4

# Homelab NUC
ssh root@homelab-nuc.lan
# or: ssh root@192.168.50.5

# AI Lab Ubuntu
ssh daniel@ailab-ubuntu.lan
# or: ssh daniel@192.168.50.10
```

## Service Categories

**Smart Home:** Home Assistant, Zigbee2MQTT, Frigate, Node-RED
**Media:** Jellyfin, Music Assistant, Navidrome
**Monitoring:** Glances, Uptime Kuma, Portainer, What's Up Docker
**Productivity:** n8n, Wallabag, Readeck, Linkding
**AI:** Open WebUI, Ollama, ComfyUI, Langfuse, Google Workspace MCP, Wyoming OpenAI
**Network:** Pi-hole, DNSMasq Leases UI, Proxmox
**Family:** TeddyCloud, Baby Buddy
**Photos:** Immich (photo/video management with ML processing)

## Tag Reference

Common tags for `--tags` flag:
- `caddy`, `pihole`, `homepage`, `ha`, `media`, `monitoring`
- `docker`, `basic`, `glances`, `portainer`
- `llm`, `llm-tools`, `llm-inference`, `llm-observability`
- `satellite-audio`,
- `wallabag`, `readeck`, `linkding`, `n8n`
- `gpu`, `comfyui`
- `netplan`, `network`
- `immich`, `immich-ml`, `changedetection`
- `wyoming_openai`, `ssh_keys`

## Environment-Specific Access

**Important:** Always use the SSH usernames specified in the `inventory` file. See the "Inventory" section above for the complete list.

**Common SSH Connections:**
- **Homelab server** (homelab-nuc): `ssh root@homelab-nuc.lan` - Ubuntu-based Docker host running ~30 services
- **Nameserver** (nameserver-pi): `ssh pi@nameserver-pi.lan` - Pi-hole DNS/DHCP server
- **AI Lab Ubuntu** (ailab-ubuntu): `ssh daniel@ailab-ubuntu.lan` - AI/ML server with GPU support
- **Proxmox** (ailab-proxmox): `ssh root@ailab-proxmox.lan` - Virtualization host

**Note:** The `.lan` domains are automatically created by Pi-hole's local DNS. You can also use IP addresses (e.g., `ssh root@192.168.50.5`) if DNS is not available.

## Common Operations

**Update specific service:**
```bash
# Pull latest and restart
uv run ansible-playbook setup.yml --tags <service-tag> --limit homelab

# Force rebuild
uv run ansible-playbook setup.yml --tags <service-tag> --limit homelab --extra-vars="force_rebuild=true"
```

**View logs:**
```bash
# Container logs
ssh root@homelab-nuc.lan "docker logs -f <container-name>"

# System logs
ssh <host> "journalctl -u <service> -f"

# All Docker logs
ssh root@homelab-nuc.lan "docker compose -f /path/to/compose.yml logs -f"
```

**Health checks:**
```bash
ssh root@homelab-nuc.lan "docker ps"
ssh root@homelab-nuc.lan "docker logs -f home-assistant"
ssh root@homelab-nuc.lan "docker logs -f caddy"
ssh root@homelab-nuc.lan "docker stats --no-stream"
```

## Setup Commands (Quick Reference)

### Install Dependencies
```bash
uv pip sync
uv run ansible-galaxy install --force-with-deps -r requirements.yml
```

### Run Playbooks
```bash
# Full setup
uv run ansible-playbook setup.yml

# Targeted deployment
uv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver
uv run ansible-playbook setup.yml --tags ha  # Home Assistant
uv run ansible-playbook setup.yml --tags llm,llm-inference  # AI tools
uv run ansible-playbook setup.yml --limit mic_satellites -t satellite-audio

# Update specific hosts
uv run ansible-playbook setup.yml --limit ailab
uv run ansible-playbook setup.yml --limit virtualhere

# Pi preparation
uv run ansible-playbook prep_pi.yml

# Troubleshooting
uv run ansible-playbook fix_hass_bluetooth.yml
uv run ansible-playbook cleanup.yml
```

## Ollama Context Limits

### Tested on ailab-ubuntu (RTX 3090 24GB VRAM)

**qwen3-vl:8b-thinking-q8_0 model:**
- **Maximum context for 100% GPU: 128,256 tokens**
- Context ≥128,320: degrades to ~10%/90% CPU/GPU split (use system RAM)
- Model size: ~9.8 GB
- At 128,256 context: ~25 GB VRAM usage

**How to set context via API:**
```bash
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-vl:8b-thinking-q8_0","options":{"num_ctx":128256},"prompt":"test","stream":false}'
```

**How to verify (check for 100% GPU and correct context):**
```bash
docker exec ollama ollama ps
```

Expected output for optimal configuration:
```
NAME                         ID              SIZE     PROCESSOR    CONTEXT    UNTIL
qwen3-vl:8b-thinking-q8_0    9e9bbfc77186    25 GB    100% GPU     128256     Forever
```

Verify:
- **PROCESSOR** column shows `100% GPU` (not CPU or mixed)
- **CONTEXT** column shows `128256` (matches your configuration)
- **SIZE** column shows `25 GB` (expected for q8_0 at 128K context)

If context is lower than 128256, the model is using the default or has been reset.

**Context vs. VRAM usage:**
- 8K context: 15 GB model size
- 16K context: 16 GB model size
- 32K context: 17 GB model size
- 64K context: 20 GB model size
- 96K context: 22 GB model size
- 128K context: 25 GB model size

**Note:** Modelfile `PARAMETER num_ctx` is ignored for Qwen3-VL models due to [GitHub bug #12855](https://github.com/ollama/ollama/issues/12855). Must use API options.

## LiteLLM Configuration

### Current Setup (Updated)

**Primary Model:** `home`
- **Model:** qwen3-vl:8b-thinking-q8_0 (via ollama_chat)
- **Context:** 128,256 tokens (100% GPU optimized)
- **Keepalive:** -1 (infinite)
- **Features:** Function calling, Vision support

**Fallback Model:** `home-remote`
- **Model:** anthropic/claude-3-5-haiku-20241022
- **Used when:** Local model is unavailable
- **API Key:** Requires ANTHROPIC_API_KEY

**Configuration File:** `/home/daniel/code/pi/roles/llm_tools/templates/litellm_config.yaml.j2`

**Usage:**
```bash
# Via OpenAI SDK
export OPENAI_API_KEY="sk-litellm-key"
export OPENAI_BASE_URL="http://litellm-proxy:4000"

# Use the home model
curl -X POST http://litellm-proxy:4000/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "home",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**Router Fallback:** When `home` fails, automatically falls back to `home-remote`

**Environment Variables Needed:**
- `ANTHROPIC_API_KEY` - For remote fallback model
- `LITELLM_MASTER_KEY` - For proxy authentication
- `OPENROUTER_API_KEY` - For wildcard model access (optional)

**Deploy Changes:**
```bash
# Update LiteLLM on ailab server
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab-ubuntu
```

**Verify Running:**
```bash
# Check LiteLLM proxy
ssh root@homelab-nuc.lan "docker ps | grep litellm"

# Test model directly (if running on homelab-nuc)
curl -X POST http://homelab-nuc.lan:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# Test model on ailab-ubuntu
curl -X POST http://ailab-ubuntu.lan:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## New Services Added (Recent Updates)

### Wyoming OpenAI (homelab-nuc, port 192.168.50.5)

**Role:** TTS/STT bridge for Home Assistant voice integration
**Tags:** `wyoming`, `wyoming_openai`
**Ansible role:** `wyoming_openai` (see `/home/daniel/code/pi/roles/wyoming_openai/`)

**Services deployed:**
- **SPEACHES (Whisper STT)** - Port 8000
  - OpenAI Whisper speech-to-text service
  - Uses int8_float32 compute type for GPU acceleration
  - Caches models in HuggingFace format

- **Chatterbox-TTS** - Port 4123
  - High-quality text-to-speech synthesis
  - **Streaming enabled**: Raw & SSE audio streaming
  - Intelligent text chunking for responsive playback
  - Configurable voice parameters (exaggeration, CFG weight, temperature)
  - GPU-accelerated with memory monitoring

- **Wyoming OpenAI Gateway** - Port 10300
  - Unified TTS/STT service for Home Assistant
  - Integrates SPEACHES and Chatterbox via Wyoming protocol
  - **Streaming enabled**: Full-duplex streaming for STT and TTS
  - Configurable languages and voices

**GPU Requirements:** All three services run on NVIDIA GPU with full GPU passthrough

**Streaming Configuration (Updated):**
```yaml
wyoming_openai:
  environment:
    # Enable streaming for STT
    STT_STREAMING_MODELS: "Systran/faster-distil-whisper-large-v3"

    # Enable streaming for TTS
    TTS_STREAMING_MODELS: "tts-1-hd"
    TTS_STREAMING_MIN_WORDS: 3
    TTS_STREAMING_MAX_CHARS: 280
```

**What this enables:**
- **STT Streaming**: Partial transcriptions as you speak (via SPEACHES + Whisper)
- **TTS Streaming**: Progressive audio playback with ~0.5s latency (via Chatterbox-TTS)
- **Real-time voice interaction** with Home Assistant Assist
- **Wyoming protocol**: Event-based streaming (audio-chunk, transcript-chunk)

**Deployment & Testing:**
```bash
# Deploy Wyoming OpenAI stack
uv run ansible-playbook setup.yml --tags wyoming_openai --limit homelab

# Check service health
ssh root@homelab-nuc.lan "docker ps | grep wyoming"

# Test streaming STT
curl -N http://homelab-nuc.lan:10300/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=Systran/faster-distil-whisper-large-v3"

# Test streaming TTS
curl -N http://homelab-nuc.lan:10300/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1-hd",
    "input": "This is a streaming test with multiple sentences.",
    "stream": true
  }' --output test_audio.wav
```

**Home Assistant Integration:**
1. Go to Settings → Voice Assistants
2. Create new voice assistant pipeline
3. Select Wyoming OpenAI for both STT and TTS
4. Configure: Host `homelab-nuc.lan`, Port `10300`
5. Test with "Turn on the kitchen light" command

**Performance Benefits:**
- STT: Hear transcription while speaking
- TTS: Audio starts playing in ~0.5 seconds instead of >5 seconds
- Full-duplex: Bidirectional streaming throughout the pipeline

### Immich - Photo/Video Management (homelab-nuc + ailab-ubuntu)

**Role:** Self-hosted Google Photos alternative with ML
**Tags:** `immich`, `immich-ml`
**Ansible roles:**
- `immich` (homelab-nuc) - Main application
- `immich_ml` (ailab-ubuntu) - Machine learning processing

**Architecture:**
- **homelab-nuc (192.168.50.5):** Main Immich server with PostgreSQL database
- **ailab-ubuntu (192.168.50.10):** Dedicated ML server for image/video processing

**Storage:**
- **ZFS datasets** with optimized compression and record sizes
- Library: `{{ zfs_pool_name }}/immich/library` (compression=lz4, recordsize=128K)
- Database: `{{ zfs_pool_name }}/immich/postgres` (compression=lz4, recordsize=16K)

**Services:**
- **Immich Server** - Main API and web UI
- **Immich ML Worker** - GPU-accelerated processing on ailab-ubuntu
- **PostgreSQL** - Metadata storage with optimized settings

**Deployment:**
```bash
# Deploy both parts (main server + ML worker)
uv run ansible-playbook setup.yml --tags immich,immich-ml --limit homelab,ailab_ubuntus

# Check ZFS datasets
ssh root@homelab-nuc.lan "zfs list {{ zfs_pool_name }}/immich"
```

**Prerequisites:**
- ZFS pool must exist and be accessible
- GPU server (ailab-ubuntu) available for ML processing

### ChangeDetection (homelab-nuc)

**Role:** Website change monitoring and alerting
**Tags:** `changedetection`
**Ansible role:** `changedetection` (see `/home/daniel/code/pi/roles/changedetection/`)

**Service deployed:**
- **ChangeDetection.io** - Monitor websites for changes
  - Detect text, visual, and source code changes
  - Send notifications when changes detected
  - Supports multiple trigger methods

**Deployment:**
```bash
# Deploy changedetection
uv run ansible-playbook setup.yml --tags changedetection --limit homelab

# Access via reverse proxy
# Web UI: https://changedetection.lan
```

### SSH Keys Automation

**Role:** Automated SSH key generation and distribution
**Tags:** `ssh_keys`
**Ansible role:** `ssh_keys` (see `/home/daniel/code/pi/roles/ssh_keys/`)

**Features:**
- Generates 4096-bit RSA key pairs
- Distributes public keys to all inventory hosts
- Automatically configures authorized_keys
- Sets proper permissions (600 on authorized_keys)
- Provides summary of successful/failed deployments

**Configuration:**
- **Source host:** Defined by `source_host` variable
- **Source user:** Defined by `source_user` variable
- **Target users:** Uses `ansible_user` from inventory for each host

**Deployment:**
```bash
# Run standalone SSH key distribution
uv run ansible-playbook distribute_ssh_key.yml

# Or run as part of setup
uv run ansible-playbook setup.yml --tags ssh_keys
```

**Output includes:**
- Public key for manual verification
- List of successfully configured hosts
- List of failed/unreachable hosts

## Code Style (Quick Reference)

**YAML:**
- Use 2 spaces for indentation (no tabs)
- Always use safe YAML operators: `|` for multiline strings, `>` for folded scalars
- Use descriptive variable names in snake_case
- Keep tasks within 80-120 character line length when possible
- Use hyphen-prefixed lists (`- name: task`)

**Ansible best practices:**
- Use `become: yes` for privileged operations
- Use `become_user` when specific user privileges needed
- Always specify `state` parameter explicitly for service/container tasks
- Use tags for grouping related tasks
- Use `block:` for grouped error handling
- Prefer `command` module over shell when possible for idempotency
- Always use `creates` or `removes` flags with command modules when applicable

**Variable naming:**
- Configuration variables: `snake_case`
- Docker image names: use full repository:tag format
- Container names: hyphenated, descriptive (e.g., `home-assistant`)
- Network names: descriptive with environment prefix (e.g., `homelab-backend`)
- Volume names: persistent, descriptive (e.g., `homeassistant-config`)

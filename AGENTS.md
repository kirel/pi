# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is an **Ansible-based homelab infrastructure** that manages multiple servers and Docker containers across a home network (192.168.50.0/24). It orchestrates services like Home Assistant, Pi-hole DNS, Caddy reverse proxy, AI/ML tools, and media services.

## Architecture Overview

### Infrastructure Topology

**Physical Servers:**
- `nameserver-pi` (192.168.50.4): Pi-hole DNS/DHCP server (Raspberry Pi)
- `homelab-nuc` (192.168.50.5): Main Docker host (Intel NUC) - runs ~30 services
- `ailab-ubuntu` (192.168.50.10): AI/ML server with GPU support
- `micpi` (192.168.50.7): Audio satellites for Alexa integration

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
uv run ansible-playbook setup.yml --limit ailab-ubuntus

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
ssh nuc "docker ps"

# View logs
ssh nuc "docker logs -f caddy"
ssh nuc "docker logs -f home-assistant"

# Restart specific container
ssh nuc "docker restart caddy"
ssh root@homelab-nuc.lan "docker compose -f /path/to/compose.yml up -d"

# Check resource usage
ssh nuc "docker stats --no-stream"
```

**System diagnostics:**
```bash
# Ansible inventory
cat inventory

# Check DNS resolution
ssh homelab-nuc.lan dig ailab-proxmox.lan

# Check Pi-hole status
ssh pi@192.168.50.4 "sudo docker ps | grep pihole"
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
ssh nuc "docker ps | grep <service>"

# Step 5: Roll out to all hosts
uv run ansible-playbook setup.yml
```

## Network Architecture

**Default network:** 192.168.50.0/24
**Router:** 192.168.50.1
**DNS Servers:** 192.168.50.4 (Pi-hole primary), 192.168.50.5 (Pi-hole backup)

**Port assignments:**
- 80, 443: Caddy reverse proxy (TLS termination)
- 8123: Home Assistant
- 3000-3002: Homepage dashboard, Uptime Kuma, WUD
- 8000-8999: Various apps (Wallabag, Readeck, Linkding, etc.)
- 9002: Portainer

All external access goes through Caddy which proxies to backend services. Internal services use `*.lan` hostnames resolved by Pi-hole.

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

## Service Categories

**Smart Home:** Home Assistant, Zigbee2MQTT, Frigate, Node-RED
**Media:** Jellyfin, Music Assistant, Navidrome
**Monitoring:** Glances, Uptime Kuma, Portainer, What's Up Docker
**Productivity:** n8n, Wallabag, Readeck, Linkding
**AI:** Open WebUI, Ollama, ComfyUI, Langfuse, Google Workspace MCP
**Network:** Pi-hole, DNSMasq Leases UI, Proxmox
**Family:** TeddyCloud, Baby Buddy

## Tag Reference

Common tags for `--tags` flag:
- `caddy`, `pihole`, `homepage`, `ha`, `media`, `monitoring`
- `docker`, `basic`, `glances`, `portainer`
- `llm`, `llm-tools`, `llm-inference`, `llm-observability`
- `satellite-audio`, `wyoming`
- `wallabag`, `readeck`, `linkding`, `n8n`
- `gpu`, `comfyui`
- `netplan`, `network`

## Environment-Specific Access

**Homelab server:**
- SSH: `ssh nuc@homelab-nuc.lan` or `ssh root@192.168.50.5`
- Ubuntu-based Docker host running ~30 services

**Pi-hole servers:**
- Primary: `ssh pi@192.168.50.4`
- Backup on homelab: `ssh nuc`

**Satellite devices:**
- Audio satellites for Alexa integration: `ssh micpi`

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
ssh nuc "docker logs -f <container-name>"

# System logs
ssh <host> "journalctl -u <service> -f"

# All Docker logs
ssh nuc "docker compose -f /path/to/compose.yml logs -f"
```

**Health checks:**
```bash
ssh nuc "docker ps"
ssh nuc "docker logs -f home-assistant"
ssh nuc "docker logs -f caddy"
ssh nuc "docker stats --no-stream"
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
uv run ansible-playbook setup.yml --limit mic-satellites -t satellite-audio

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

**How to verify (check for 100% GPU):**
```bash
docker exec ollama ollama ps
# Look for "100% GPU" in PROCESSOR column
```

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
ssh ailab "docker ps | grep litellm"

# Test model directly
curl -X POST http://ailab-ubuntu:4000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

### Code Style (Quick Reference)

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

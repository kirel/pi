# AGENTS.md

Guidance for AI agents working in this **Ansible-based homelab infrastructure**.

## Core Concepts

- **Services:** `group_vars/all/services.yml` is the source of truth for proxied services (`target`, `http_port`, `domain`, `group`).
- **MCP:** `litellm_mcp_servers` in `roles/llm_tools/defaults/main.yml` is the source of truth. LiteLLM config, Dockerfile npm/uv preinstalls, and stdio allowlist are rendered from it.
- **DNS/SSL:** Pi-hole creates host A-records and service CNAMEs; Caddy terminates `*.kirelabs.org` TLS via Regfish DNS-01.

## Deployments

```bash
# Full deploy
uv run ansible-playbook setup.yml

# Services/DNS/proxy after group_vars/all/services.yml changes
uv run ansible-playbook setup.yml --tags caddy --limit homelab
uv run ansible-playbook setup.yml --tags pihole --limit nameserver,homelab

# LiteLLM / MCP config and image changes
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab

# LLM inference changes
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus
```

**Rules:**
- After editing `services.yml`, redeploy **Caddy + Pi-hole**.
- After editing `litellm_mcp_servers`, deploy **llm-tools only** unless a service entry also changed.

## MCP Setup

Add agent/LiteLLM MCP servers only in `litellm_mcp_servers`:

```yaml
my_server:
  transport: stdio
  command: my-mcp-binary        # direct installed binary; avoid npx/uvx at runtime
  env:
    API_KEY: "{{ my_secret }}"
  access_groups: ["private"]
  install:                      # optional preinstall in LiteLLM image
    manager: npm                # or: uv
    package: my-mcp-package     # npm
    # args: ["my-mcp-package"] # uv tool install args
```

- **stdio:** use direct binaries. `install.manager: npm|uv` preinstalls them in the LiteLLM image; non-default commands are auto-added to `LITELLM_MCP_STDIO_EXTRA_COMMANDS`.
- **remote HTTP/SSE:** use `url` plus auth fields (`auth_type`, `auth_value`, `static_headers`, etc.).
- **Do not** add standalone containers or `services.yml` entries for MCP servers only used by LiteLLM. Exception: direct network clients need an HTTP endpoint (example: `google-workspace-mcp`).
- Verify via `https://litellm.kirelabs.org/mcp/` with a valid LiteLLM bearer token and `Accept: application/json, text/event-stream`, or inspect `docker logs litellm-proxy-container` for MCP allowlist/discovery errors.

## LLM Notes

- **LiteLLM:** `https://litellm.kirelabs.org`; if `/health/readiness` says `Not connected to the query engine`, run `docker restart litellm-proxy-container` to trigger Prisma migrations.
- **LlamaSwap:** `http://ailab-ubuntu.lan:9292`; useful endpoints: `/logs`, `/logs/stream`, `/running`.
- **GPUs:** GPU0+GPU1 (RTX 3090) run LLM inference plus embedding/STT/TTS. GPU2 (RTX 5060 Ti eGPU) is reserved for Wolf/ComfyUI/Wan2GP and gaming; do not use it for LLM inference or LLM benchmarks.
- **VRAM constraint:** `llama.cpp --fit` does not work with `-sm tensor`; set explicit context sizes in `group_vars/all/llms.yml` and preserve headroom (~3GB GPU0, ~4.5GB GPU1).
- **Qwen3.6 27B tuning:** keep tensor split, three slots, batch 2048, and micro-batch 512 unless a new simultaneous-load benchmark justifies a change. Micro-batch 1024 was only ~2.8% faster while using ~0.9GiB more VRAM per 3090; layer split and a separate single-slot profile were worse. See `docs/qwen36-27b-prompt-processing-benchmark-2026-07-11.md`.
- **Prompt cache:** keep Think/NoThink as request variants of the same running Qwen backend. A separate LlamaSwap profile starts another `llama-server` process and discards the GPU and host prompt caches on profile switches. `preserve_thinking: true` plus stable message/tool serialization keeps the reusable prefix across turns and Think/NoThink switches.

## DNS Flow

`service.kirelabs.org` → Pi-hole CNAME to `target` host → host A-record (`*.lan`) → Caddy on `homelab-nuc` → container port.

## Quick Diagnostics

```bash
ssh root@homelab-nuc.lan "docker ps"
ssh root@homelab-nuc.lan "docker logs -f <container_name>"
curl -I https://<service>.kirelabs.org/health
ssh root@homelab-nuc.lan "docker logs litellm-proxy-container 2>&1 | grep -Ei 'mcp|allowlist|timeout'"
```

## Inventory

| Host | IP | SSH User | Role |
| --- | --- | --- | --- |
| `homelab-nuc` | `192.168.50.5` | `root` | Docker services, LiteLLM, Caddy |
| `nameserver-pi` | `192.168.50.4` | `daniel` | Pi-hole DNS/DHCP |
| `ailab-ubuntu` | `192.168.50.10` | `daniel` | Bare-metal GPU inference |

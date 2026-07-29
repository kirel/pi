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

## Hermes Agents

### Bare-Metal Main Hermes

- **Identity:** Daniel's main Hermes agent is a manually installed bare-metal instance on the Hetzner host `ubuntu-8gb-fsn1-1` (`100.82.91.51`), running as user `daniel`. Its state and primary configuration live under `/home/daniel/.hermes`; do not confuse it with any `hermes-*` Docker container.
- **Management boundary:** The installation and main `config.yaml` are currently manual; a future Ansible migration is planned but is a separate task. For now, Ansible manages only selected integration points, including the environment block in `/home/daniel/.hermes/.env`, dashboard metadata, and the LiteLLM virtual-key policy. Do not replace or broadly template `config.yaml`, remove manual MCP entries, or redeploy the Docker Hermes role when changing this agent.
- **Chat providers:** The primary model is `gpt-5.6-terra` through `openai-codex`, with direct Z.AI/GLM and MiniMax fallbacks. LiteLLM is not its primary chat provider.
- **LiteLLM use:** LiteLLM provides `home-asr`, `home-tts`, and the central MCP gateway. The existing LiteLLM key alias is `hermes`; its encrypted value and declarative permissions are managed through `litellm_managed_virtual_keys` in `group_vars/all/hermes_mcp.yml`.
- **MCP access:** This is the trusted full-capability agent. It receives `web`, `maps`, `home_admin`, `shopping`, `photos`, `notes`, `workflow_admin`, `code`, and `media_generation`. `home_admin` already includes Home Assistant control, so do not also grant `home_control`.
- **Todoist:** Even this full-capability agent uses the seven-tool shopping allowlist from `hermes_mcp_tool_profiles.shopping.todoist`; broad system access does not require loading the other Todoist project-management tools.
- **Wan2GP:** `media_generation` belongs only to this bare-metal agent for now. Wan2GP tools exchange local file paths, and this host has the matching `hermes-wangp-ssh-key` access needed to move files into and out of the Wan2GP workspace. Do not grant the group to Docker agents until file transport is redesigned.
- **Direct MCP:** Craft is configured directly in the manual Hermes config and does not pass through LiteLLM. Preserve it when inspecting or changing the agent.
- **Skills and secrets:** The agent loads personal skills from `~/.agents/skills` and resolves runtime secrets through its existing 1Password integration. Never print or copy values from `/home/daniel/.hermes/.env`, `config.yaml`, process environments, or LiteLLM-rendered configs.
- **Deployment:** Changes to its LiteLLM MCP catalog or managed virtual-key permissions use `uv run ansible-playbook setup.yml --tags llm-tools --limit homelab`. Changes to the manual Hermes runtime require an explicit, separately scoped request and live verification on `100.82.91.51`.

## LLM Notes

- **LiteLLM:** `https://litellm.kirelabs.org`; if `/health/readiness` says `Not connected to the query engine`, run `docker restart litellm-proxy-container` to trigger Prisma migrations.
- **LlamaSwap:** `http://ailab-ubuntu.lan:9292`; useful endpoints: `/logs`, `/logs/stream`, `/running`.
- **GPUs:** GPU0+GPU1 (RTX 3090) run LLM inference plus embedding/STT/TTS. GPU2 (RTX 5060 Ti eGPU) is reserved for Wolf/ComfyUI/Wan2GP and gaming; do not use it for LLM inference or LLM benchmarks.
- **VRAM constraint:** `llama.cpp --fit` does not work with `-sm tensor`; set explicit context sizes in `group_vars/all/llms.yml` and preserve headroom (~3GB GPU0, ~4.5GB GPU1).
- **Qwen3.6 27B tuning:** keep tensor split, three slots, batch 2048, and micro-batch 512 unless a new simultaneous-load benchmark justifies a change. Micro-batch 1024 was only ~2.8% faster while using ~0.9GiB more VRAM per 3090; layer split and a separate single-slot profile were worse. See `docs/qwen36-27b-prompt-processing-benchmark-2026-07-11.md`.
- **Gemma 4:** 26B uses the shared 376832-token pool; dense 31B must use its explicit 131072-token pool to preserve 3090 headroom with embedding/TTS resident. Current Unsloth GGUFs use `--reasoning on` and MTP draft max 4. When Unsloth replaces embedded chat templates, remove the affected Hugging Face repo cache before re-requesting the model; a container restart alone may retain the old GGUF.
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

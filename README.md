# README

This is my homelab config. The repo is called `pi` because it started as a single pi. It's now:

- `nameserver-pi` (192.168.50.4) — Pi-hole: DHCP, DNS, ad-blocking
- `homelab-nuc` (192.168.50.5) — Intel NUC running Ubuntu as a Docker host (all services are containers, inc. a Pi-hole backup)
- `ailab-proxmox` (192.168.50.9) — Proxmox hypervisor
- `ailab-ubuntu` (192.168.50.10) — GPU server (RTX 3090) for LLM inference and image generation

## Bootstrap the Pi

1. Download the pi imager at https://www.raspberrypi.com/software/
2. Select Pi OS Lite 64 bit
3. Set hostname to pihole.local
4. Activate SSH, and paste your public key into the SSH key field
5. Set language settings to Berlin timezone and us keyboard
6. Write the image
7. Eject and reinsert the memory card

```bash
uv run ansible-playbook prep_pi.yml
```

## Setup

### Basic Setup

```bash
# Install dependencies using uv
uv pip sync
# Install Ansible Galaxy roles
uv run ansible-galaxy install --force-with-deps -r requirements.yml
```

### Everything

```bash
uv run ansible-playbook setup.yml
```

### DNS, Proxy, Dashboard

```bash
uv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver
```

### Home Assistant

```bash
uv run ansible-playbook setup.yml --tags ha
uv run ansible-playbook setup.yml --limit mic_satellites -t satellite-audio
uv run ansible-playbook setup.yml --limit mic_satellites -t wyoming --start-at-task="Start wyoming stack"
```

### AI Lab

```bash
# LLM tools (Open WebUI, LiteLLM, etc.) on homelab-nuc
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab

# LLM inference (LlamaSwap) on ailab-ubuntu
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus

# Observability (Langfuse)
uv run ansible-playbook setup.yml --tags llm-observability --limit homelab

# Everything LLM-related
uv run ansible-playbook setup.yml --tags llm --limit homelab,ailab_ubuntus
```

### LlamaSwap (llama.cpp)

LlamaSwap runs on `ailab-ubuntu` with GPU acceleration (RTX 3090 24GB).

- **Model:** Qwen3-VL-8B-Instruct-GGUF Q8_K_XL from Unsloth
- **Context Size:** 92,375 tokens max (92,500+ causes OOM)
- **WebUI:** https://llama-swap.kirelabs.org/ui

### Benchmarking

Compare end-to-end latency (TTFT) and throughput (TPS) across models:

```bash
LITELLM_MASTER_KEY=<your-key> uv run --with openai python3 todo/scripts/llm_benchmark.py
```

## LLM Service Architecture

```
Open WebUI → LiteLLM Proxy → LlamaSwap (ailab-ubuntu)
                  ↓
           MCP-Proxy + Google Workspace MCP
                  ↓
           Langfuse [observability]
```

| Service | URL | Host |
| :--- | :--- | :--- |
| Open WebUI | https://open-webui.kirelabs.org | homelab-nuc |
| LiteLLM Admin | https://litellm-ui.kirelabs.org | homelab-nuc |
| Langfuse | https://langfuse.kirelabs.org | homelab-nuc |
| LlamaSwap | https://llama-swap.kirelabs.org | ailab-ubuntu |
| ComfyUI | https://comfyui.kirelabs.org | ailab-ubuntu |

## Secrets

```bash
uv run ansible-vault edit group_vars/all/secrets.yml
```

## Manual router setup

1. Turn DHCP off. Pi-hole and pihole-homelab take over.

## Troubleshooting

### Fix bluetooth

```bash
uv run ansible-playbook fix_hass_bluetooth.yml
```

### Ring-MQTT token expired

```bash
ssh root@homelab-nuc.lan
HOST_PATH=/home/nuc/config/ring-mqtt/
docker run -it --rm --mount type=bind,source=$HOST_PATH,target=/data --entrypoint /app/ring-mqtt/init-ring-mqtt.js tsightler/ring-mqtt
docker restart ring-mqtt
```
